"""Service container: the components the API uses, built once per process.

``build_services`` picks the stub or the real components from ``Settings.backend``. Retrieval
state of a collection (dense channel, in-process BM25, evidence graph and one ``Retriever`` per
preset) is built on first use and dropped by ``Services.invalidate`` after an ingestion or a
deletion.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from docrag.api.jobs import JobRunner
from docrag.baseline.paper_adapter import PaperMethod
from docrag.config import PipelineConfig, Settings
from docrag.generate.citations import parse_answer
from docrag.generate.extractive import ExtractiveReader
from docrag.generate.llm_client import LLMClient, LLMUnavailable
from docrag.generate.prompt import build_messages
from docrag.graph.build import EvidenceGraph, build_graph
from docrag.ingest.chunk import count_words
from docrag.ingest.parse import Parser, get_parser
from docrag.models import Chunk
from docrag.retrieve.context import build_context
from docrag.retrieve.dense import (
    ENCODER_SPECS,
    DenseBackend,
    DenseChannel,
    Encoder,
    NumpyDenseBackend,
    SentenceEncoder,
)
from docrag.retrieve.pipeline import RetrievalResult, Retriever, TraceEntry
from docrag.retrieve.rerank import Scorer, load_cross_encoder
from docrag.retrieve.sparse import SparseChannel
from docrag.store.qdrant_dense import QdrantDenseBackend
from docrag.store.sqlite_store import SqliteStore
from docrag.stub import HashEncoder, StubLLM, StubReader, StubScorer

logger = logging.getLogger(__name__)

PAPER_PRESET = "paper"
DEFAULT_PRESET = "L2"
DB_FILENAME = "docrag.sqlite3"
QDRANT_COLLECTION_PREFIX = "docrag_"


class Reader(Protocol):
    """Extractive reader: the answer span of a context, with its score."""

    def answer_span(self, question: str, context: str) -> tuple[str, float]: ...


class ChatModel(Protocol):
    """Chat client: the reply to a list of chat messages."""

    def chat(self, messages: list[dict[str, str]]) -> str: ...


class LLMFailed(Exception):
    """The LLM reader could not answer. The retrieval trace is still valid and is returned."""

    def __init__(self, trace: list[TraceEntry]) -> None:
        super().__init__("llm_unavailable")
        self.trace = trace


@dataclass(frozen=True)
class Answer:
    """One answer. ``text`` is None when there is none. ``cited`` holds ``(number, chunk)``."""

    text: str | None
    cited: list[tuple[int, Chunk]]
    trace: list[TraceEntry]


class CollectionIndex:
    """Retrieval state of one collection, built from its stored chunks and reused."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        dense: DenseChannel,
        sparse: SparseChannel,
        graph: EvidenceGraph,
        scorer: Scorer | None,
    ) -> None:
        self.chunks = list(chunks)
        self.chunks_by_doc: dict[str, list[Chunk]] = {}
        for chunk in self.chunks:
            self.chunks_by_doc.setdefault(chunk.doc_id, []).append(chunk)
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self._dense = dense
        self._sparse = sparse
        self._graph = graph
        self._scorer = scorer
        self._retrievers: dict[str, Retriever] = {}
        self._paper: PaperMethod | None = None

    def retriever(self, cfg: PipelineConfig) -> Retriever:
        """The retriever of one preset, built on first use."""
        retriever = self._retrievers.get(cfg.name)
        if retriever is None:
            retriever = Retriever(
                cfg,
                self.chunks,
                dense=self._dense,
                sparse=self._sparse,
                graph=self._graph,
                scorer=self._scorer,
            )
            self._retrievers[cfg.name] = retriever
        return retriever

    def chunk(self, chunk_id: str) -> Chunk:
        return self._chunks_by_id[chunk_id]

    def paper(self) -> PaperMethod:
        """The published method over this collection, built on first use."""
        if self._paper is None:
            self._paper = PaperMethod(self.chunks)
        return self._paper


@dataclass
class Services:
    """Everything the routes use. ``make_dense(collection_id, dim)`` gives a collection's store."""

    settings: Settings
    store: SqliteStore
    encoder: Encoder
    make_dense: Callable[[str, int], DenseBackend]
    parser: Parser
    scorer: Scorer | None
    reader: Reader | None
    llm: ChatModel | None
    paper_enabled: bool
    jobs: JobRunner
    ready: threading.Event
    count_tokens: Callable[[str], int]
    _indexes: dict[str, CollectionIndex] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def invalidate(self, cid: str) -> None:
        """Drop the retrieval state of a collection; the next question rebuilds it."""
        with self._lock:
            self._indexes.pop(cid, None)

    def dense(self, cid: str) -> DenseBackend:
        """The dense store of one collection."""
        dim = int(self.encoder.encode_query("dimension").shape[0])
        return self.make_dense(cid, dim)

    def index(self, cid: str) -> CollectionIndex:
        """The retrieval state of a collection. Holding the lock while building keeps an
        invalidation that follows an ingestion from being overtaken by a stale build."""
        with self._lock:
            index = self._indexes.get(cid)
            if index is None:
                index = self._build_index(cid)
                self._indexes[cid] = index
            return index

    def _build_index(self, cid: str) -> CollectionIndex:
        chunks = self.store.list_chunks(cid)
        raw_graph = self.store.load_graph(cid)
        if raw_graph is None:
            graph = build_graph(chunks)
            self.store.save_graph(cid, graph.to_bytes())
        else:
            graph = EvidenceGraph.from_bytes(raw_graph)
        dense = DenseChannel({c.chunk_id: c for c in chunks}, self.encoder, self.dense(cid))
        return CollectionIndex(
            chunks,
            dense=dense,
            sparse=SparseChannel(chunks),
            graph=graph,
            scorer=self.scorer,
        )

    def search(self, cid: str, cfg: PipelineConfig, query: str, k: int) -> list[TraceEntry]:
        """The best ``k`` entries of the final ranking: the rerank stage if the preset reranks,
        otherwise the pool."""
        result = self.index(cid).retriever(cfg).retrieve(query)
        final_stage = "rerank" if cfg.use_reranker else "pool"
        return [entry for entry in result.trace if entry.stage == final_stage][:k]

    def ask(self, cid: str, cfg: PipelineConfig, question: str, k: int | None) -> Answer:
        """Answer ``question`` with the pipeline of a preset.

        An extractive preset gives the reader the best-ranked passage alone, with no neighbours.
        An LLM preset gives the reader ``k`` passages (the preset's ``final_k`` by default) and
        cites what the reply cites. Raises ``LLMFailed`` if the LLM endpoint fails.
        """
        index = self.index(cid)
        result = index.retriever(cfg).retrieve(question)
        if not result.hits:
            return Answer(None, [], result.trace)
        if cfg.reader == "llm":
            return self._ask_llm(index, cfg, question, result, k)
        return self._ask_extractive(index, cfg, question, result)

    def _ask_extractive(
        self, index: CollectionIndex, cfg: PipelineConfig, question: str, result: RetrievalResult
    ) -> Answer:
        if self.reader is None:
            raise RuntimeError("no extractive reader is configured")
        top = build_context(
            result.hits[:1],
            index.chunks_by_doc,
            use_header=cfg.use_context,
            neighbours=0,
            max_passages=1,
        )[0]
        answer, _score = self.reader.answer_span(question, top.text)
        if not answer:
            return Answer(None, [], result.trace)
        return Answer(answer, [(1, top.chunk)], result.trace)

    def _ask_llm(
        self,
        index: CollectionIndex,
        cfg: PipelineConfig,
        question: str,
        result: RetrievalResult,
        k: int | None,
    ) -> Answer:
        if self.llm is None:
            raise LLMFailed(result.trace)
        passages = build_context(
            result.hits,
            index.chunks_by_doc,
            use_header=cfg.use_context,
            neighbours=cfg.neighbours,
            max_passages=cfg.final_k if k is None else k,
        )
        try:
            raw = self.llm.chat(build_messages(question, passages))
        except LLMUnavailable as exc:
            raise LLMFailed(result.trace) from exc
        parsed = parse_answer(raw, len(passages))
        if parsed.text is None:
            return Answer(None, [], result.trace)
        # Passage numbers run from 1, so passage n is at index n - 1.
        cited = [(number, passages[number - 1].chunk) for number in parsed.citations]
        return Answer(parsed.text, cited, result.trace)

    def ask_paper(self, cid: str, question: str) -> Answer:
        """Answer with the published method: its best passage is cited as [1].

        The published method exposes ranked chunk ids without scores, so the trace is empty.
        """
        index = self.index(cid)
        paper = index.paper()
        ranked = paper.ranked_chunk_ids(question)
        text = paper.answer(question).strip()
        if not ranked or not text:
            return Answer(None, [], [])
        return Answer(text, [(1, index.chunk(ranked[0]))], [])


def build_services(settings: Settings, *, jobs: JobRunner | None = None) -> Services:
    """Build the services for ``settings.backend``.

    ``stub`` loads no model. ``real`` needs ``DOCRAG_QDRANT_URL`` and loads the pinned encoder,
    reranker and extractive reader, and an LLM client when ``DOCRAG_LLM_BASE_URL`` is set.
    """
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(settings.state_dir / DB_FILENAME)
    parser = get_parser(settings.parser, max_pages=settings.max_pages)

    if settings.backend == "stub":
        encoder: Encoder = HashEncoder(64)
        make_dense = _one_store_per_collection(lambda cid, dim: NumpyDenseBackend())
        scorer: Scorer | None = StubScorer()
        reader: Reader | None = StubReader()
        llm: ChatModel | None = StubLLM()
        count_tokens = count_words
    elif settings.backend == "real":
        if not settings.qdrant_url:
            raise ValueError("DOCRAG_QDRANT_URL is required")
        url = settings.qdrant_url
        sentence_encoder = SentenceEncoder(ENCODER_SPECS["bge-m3"])
        encoder = sentence_encoder
        make_dense = _one_store_per_collection(
            lambda cid, dim: QdrantDenseBackend(url, QDRANT_COLLECTION_PREFIX + cid, dim)
        )
        scorer = load_cross_encoder()
        reader = ExtractiveReader()
        llm = _llm_client(settings)
        count_tokens = sentence_encoder.count_tokens
    else:
        raise ValueError(f"unknown backend: {settings.backend!r}")

    return Services(
        settings=settings,
        store=store,
        encoder=encoder,
        make_dense=make_dense,
        parser=parser,
        scorer=scorer,
        reader=reader,
        llm=llm,
        paper_enabled=settings.enable_paper_baseline,
        jobs=JobRunner() if jobs is None else jobs,
        ready=threading.Event(),
        count_tokens=count_tokens,
    )


def load_in_background(services: Services) -> threading.Thread:
    """Load the models in a daemon thread and set ``services.ready`` once they answer.

    A failed load is logged and leaves ``ready`` unset, so ``/api/ready`` keeps answering 503.
    """
    thread = threading.Thread(target=_load, args=(services,), name="docrag-loader", daemon=True)
    thread.start()
    return thread


def _load(services: Services) -> None:
    try:
        # The first call loads the sentence model; for the stub it costs nothing.
        services.encoder.encode_query("docrag")
    except Exception:
        logger.exception("model loading failed; /api/ready stays unavailable")
        return
    services.ready.set()


def _one_store_per_collection(
    factory: Callable[[str, int], DenseBackend],
) -> Callable[[str, int], DenseBackend]:
    """Wrap a dense-store factory so that every collection gets one shared store."""
    stores: dict[str, DenseBackend] = {}
    lock = threading.Lock()

    def make(cid: str, dim: int) -> DenseBackend:
        with lock:
            if cid not in stores:
                stores[cid] = factory(cid, dim)
            return stores[cid]

    return make


def _llm_client(settings: Settings) -> LLMClient | None:
    if not settings.llm_base_url:
        return None
    if not settings.llm_model:
        raise ValueError("DOCRAG_LLM_MODEL is required when DOCRAG_LLM_BASE_URL is set")
    return LLMClient(settings.llm_base_url, settings.llm_model, api_key=settings.llm_api_key)
