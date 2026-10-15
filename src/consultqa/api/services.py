"""Service container: the components the API uses, built once per process.

``build_services`` picks the stub or the real components from ``Settings.backend``. Retrieval
state of a collection (dense channel, in-process BM25, one ``Retriever`` per preset, and the
evidence graph for the presets that expand through it) is built on first use and dropped by
``Services.invalidate`` after an ingestion or a deletion.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Protocol

from consultqa.api.jobs import JobRunner
from consultqa.baseline.paper_adapter import PaperMethod
from consultqa.config import PipelineConfig, Settings
from consultqa.generate.citations import parse_answer
from consultqa.generate.extractive import ExtractiveReader
from consultqa.generate.llm_client import LLMClient, LLMUnavailable
from consultqa.generate.prompt import build_messages
from consultqa.graph.build import EvidenceGraph, build_graph
from consultqa.ingest.chunk import count_words
from consultqa.ingest.parse import Parser, get_parser
from consultqa.models import Chunk, Hit
from consultqa.retrieve.context import build_context
from consultqa.retrieve.dense import (
    ENCODER_SPECS,
    DenseBackend,
    DenseChannel,
    Encoder,
    NumpyDenseBackend,
    SentenceEncoder,
)
from consultqa.retrieve.pipeline import RetrievalResult, Retriever, TraceEntry
from consultqa.retrieve.rerank import Scorer, load_cross_encoder
from consultqa.retrieve.sparse import SparseChannel
from consultqa.store.originals import OriginalFiles
from consultqa.store.qdrant_dense import QdrantDenseBackend
from consultqa.store.sqlite_store import SqliteStore
from consultqa.stub import HashEncoder, StubLLM, StubReader, StubScorer

logger = logging.getLogger(__name__)

PAPER_PRESET = "paper"
DEFAULT_PRESET = "L2"
DB_FILENAME = "consultqa.sqlite3"
QDRANT_COLLECTION_PREFIX = "consultqa_"
INTERRUPTED_ERROR = "interrupted"


class Reader(Protocol):
    """Extractive reader: the answer span of a context, with its score."""

    def answer_span(self, question: str, context: str) -> tuple[str, float]: ...


class ChatModel(Protocol):
    """Chat client: the reply to a list of chat messages."""

    def chat(self, messages: list[dict[str, str]]) -> str: ...


class CollectionBusy(Exception):
    """A job of the collection has not finished, so the collection cannot be deleted yet."""


class CollectionMissing(Exception):
    """The collection does not exist, for instance because it was deleted meanwhile."""


class LLMFailed(Exception):
    """The LLM reader could not answer. The retrieval trace is still valid and is returned."""

    def __init__(self, trace: list[TraceEntry]) -> None:
        super().__init__("llm_unavailable")
        self.trace = trace


@dataclass(frozen=True)
class Answer:
    """One answer. ``text`` is None when there is none. ``cited`` holds ``(number, chunk)``.
    ``related`` holds the top retrieved chunks, one per page (see ``related_chunks``)."""

    text: str | None
    cited: list[tuple[int, Chunk]]
    trace: list[TraceEntry]
    related: list[Chunk] = field(default_factory=list)


def related_chunks(hits: Sequence[Hit], limit: int = 5) -> list[Chunk]:
    """The first chunk of each distinct ``(doc_id, page)`` in rank order, at most ``limit``.

    Chunks without a page are distinct by their id, since a page-less document has no pages to
    group by.
    """
    seen: set[tuple[str, int | str]] = set()
    related: list[Chunk] = []
    for hit in hits:
        chunk = hit.chunk
        group = chunk.page if chunk.page is not None else chunk.chunk_id
        key = (chunk.doc_id, group)
        if key in seen:
            continue
        seen.add(key)
        related.append(chunk)
        if len(related) == limit:
            break
    return related


class CollectionIndex:
    """Retrieval state of one collection, built from its stored chunks and reused.

    The evidence graph is built from the chunks the first time a preset that expands through it
    asks for it. Presets without the graph never build it.
    """

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        dense: DenseChannel,
        sparse: SparseChannel,
        scorer: Scorer | None,
    ) -> None:
        self.chunks = list(chunks)
        self.chunks_by_doc: dict[str, list[Chunk]] = {}
        for chunk in self.chunks:
            self.chunks_by_doc.setdefault(chunk.doc_id, []).append(chunk)
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in self.chunks}
        self._dense = dense
        self._sparse = sparse
        self._graph: EvidenceGraph | None = None
        self._graph_lock = threading.Lock()
        self._scorer = scorer
        self._retrievers: dict[str, Retriever] = {}
        self._paper: PaperMethod | None = None
        self._documents: dict[str, CollectionIndex] = {}
        self._documents_lock = threading.Lock()

    def for_document(self, doc_id: str) -> "CollectionIndex":
        """The retrieval state of one document, as if the collection held only that document.

        Built on first use and reused; it is dropped together with this index. Raises ``KeyError``
        when the collection has no chunks of ``doc_id``.
        """
        with self._documents_lock:
            index = self._documents.get(doc_id)
            if index is None:
                doc_chunks = self.chunks_by_doc[doc_id]
                index = CollectionIndex(
                    doc_chunks,
                    dense=self._dense.restricted({c.chunk_id: c for c in doc_chunks}),
                    sparse=SparseChannel(doc_chunks, per_document_fold=True),
                    scorer=self._scorer,
                )
                self._documents[doc_id] = index
            return index

    def graph(self) -> EvidenceGraph:
        """The evidence graph of the chunks, built on first use and then reused."""
        with self._graph_lock:
            if self._graph is None:
                self._graph = build_graph(self.chunks)
            return self._graph

    def retriever(self, cfg: PipelineConfig) -> Retriever:
        """The retriever of one preset, built on first use."""
        retriever = self._retrievers.get(cfg.name)
        if retriever is None:
            retriever = Retriever(
                cfg,
                self.chunks,
                dense=self._dense,
                sparse=self._sparse,
                graph=self.graph() if cfg.use_graph else None,
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
    forget_dense: Callable[[str], None]
    originals: OriginalFiles
    # The real backend leaves ``scorer`` and ``reader`` unset and gives these builders instead; the
    # loader thread calls them after the encoder, so the port opens before the models are in memory.
    load_scorer: Callable[[], Scorer] | None = None
    load_reader: Callable[[], Reader] | None = None
    # The real backend gives the parser's warm-up, which the loader calls after ``ready`` is set.
    # The stub backend loads no model, so it has none.
    warm_parser: Callable[[], None] | None = None
    _indexes: dict[str, CollectionIndex] = field(default_factory=dict, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    # Held by the steps that add a job to a collection and by its deletion, so that the two never
    # interleave: a job cannot be added to a collection that is being deleted, and vice versa.
    collections_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _dim: int | None = field(default=None, init=False, repr=False)

    def invalidate(self, cid: str) -> None:
        """Drop the retrieval state of a collection; the next question rebuilds it."""
        with self._lock:
            self._indexes.pop(cid, None)

    def delete_collection(self, cid: str) -> bool:
        """Delete a collection with its documents, chunks, graph, jobs, vectors and original files.

        Returns False when there is no such collection. Raises ``CollectionBusy`` while one of its
        jobs has not finished, and then removes nothing. The vectors go before the rows, so a vector
        store that is down leaves the collection whole for a later attempt. The original files go
        after the rows, one at a time: a file that cannot be removed is logged and the rest are
        still removed, and the deletion still returns True.
        """
        try:
            with self.collections_lock, self._lock:
                if self.store.get_collection(cid) is None:
                    return False
                if self.store.has_active_jobs(cid):
                    raise CollectionBusy(cid)
                doc_ids = [doc["id"] for doc in self.store.list_documents(cid)]
                try:
                    self.dense(cid).drop()
                    self.store.delete_collection(cid)
                    for doc_id in doc_ids:
                        try:
                            self.originals.delete(doc_id)
                        except OSError:
                            logger.warning("could not remove the original of document %s", doc_id)
                finally:
                    self.forget_dense(cid)
        finally:
            # Outside the index lock, which invalidate takes; runs on every outcome.
            self.invalidate(cid)
        return True

    def embedding_dimension(self) -> int:
        """The length of the encoder's vectors, read once from the encoder without encoding text."""
        if self._dim is None:
            self._dim = int(self.encoder.get_sentence_embedding_dimension())
        return self._dim

    def dense(self, cid: str) -> DenseBackend:
        """The dense store of one collection, sized by the encoder's dimension."""
        return self.make_dense(cid, self.embedding_dimension())

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
        # Checked under the index lock, which a deletion also holds: a deleted collection must not
        # get a vector store back, since creating one would recreate its Qdrant collection.
        if self.store.get_collection(cid) is None:
            raise CollectionMissing(cid)
        chunks = self.store.list_chunks(cid)
        dense = DenseChannel({c.chunk_id: c for c in chunks}, self.encoder, self.dense(cid))
        return CollectionIndex(
            chunks,
            dense=dense,
            sparse=SparseChannel(chunks, per_document_fold=True),
            scorer=self.scorer,
        )

    def search(
        self,
        cid: str,
        cfg: PipelineConfig,
        query: str,
        k: int,
        doc_id: str | None = None,
    ) -> list[TraceEntry]:
        """The best ``k`` entries of the final ranking: the rerank stage if the preset reranks,
        otherwise the pool. With ``doc_id`` the search covers that document only."""
        result = self._scope(cid, doc_id).retriever(cfg).retrieve(query)
        final_stage = "rerank" if cfg.use_reranker else "pool"
        return [entry for entry in result.trace if entry.stage == final_stage][:k]

    def ask(
        self,
        cid: str,
        cfg: PipelineConfig,
        question: str,
        k: int | None,
        doc_id: str | None = None,
    ) -> Answer:
        """Answer ``question`` with the pipeline of a preset.

        An extractive preset gives the reader the best-ranked passage alone, with no neighbours.
        An LLM preset gives the reader ``k`` passages (the preset's ``final_k`` by default) and
        cites what the reply cites. With ``doc_id`` the question covers that document only.
        Raises ``LLMFailed`` if the LLM endpoint fails.
        """
        index = self._scope(cid, doc_id)
        result = index.retriever(cfg).retrieve(question)
        if not result.hits:
            return Answer(None, [], result.trace)
        if cfg.reader == "llm":
            answer = self._ask_llm(index, cfg, question, result, k)
        else:
            answer = self._ask_extractive(index, cfg, question, result)
        return replace(answer, related=related_chunks(result.hits))

    def _scope(self, cid: str, doc_id: str | None) -> CollectionIndex:
        """The collection's index, or the index of one document of it. Raises ``KeyError`` for a
        document the collection does not hold."""
        index = self.index(cid)
        return index if doc_id is None else index.for_document(doc_id)

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

    def ask_paper(self, cid: str, question: str, doc_id: str | None = None) -> Answer:
        """Answer with the published method: its best passage is cited as [1].

        The published method exposes ranked chunk ids without scores, so the trace is empty and
        ``related`` is empty too.
        """
        index = self._scope(cid, doc_id)
        paper = index.paper()
        ranked = paper.ranked_chunk_ids(question)
        text = paper.answer(question).strip()
        if not ranked or not text:
            return Answer(None, [], [])
        return Answer(text, [(1, index.chunk(ranked[0]))], [])


def build_services(settings: Settings, *, jobs: JobRunner | None = None) -> Services:
    """Build the services for ``settings.backend``.

    ``stub`` loads no model. ``real`` needs ``CONSULTQA_QDRANT_URL`` and loads the pinned encoder,
    reranker and extractive reader, and an LLM client when ``CONSULTQA_LLM_BASE_URL`` is set.
    """
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    store = SqliteStore(settings.state_dir / DB_FILENAME)
    # Jobs still open at startup belonged to a process that has stopped; they cannot finish.
    interrupted = store.fail_unfinished_jobs(INTERRUPTED_ERROR)
    if interrupted:
        logger.warning("marked %d unfinished ingestion job(s) as interrupted", interrupted)
    parser = get_parser(
        settings.parser,
        max_pages=settings.max_pages,
        artifacts_path=settings.docling_artifacts,
    )

    scorer: Scorer | None = None
    reader: Reader | None = None
    load_scorer: Callable[[], Scorer] | None = None
    load_reader: Callable[[], Reader] | None = None
    warm_parser: Callable[[], None] | None = None
    if settings.backend == "stub":
        encoder: Encoder = HashEncoder(64)
        dense_stores = _DenseStores(lambda cid, dim: NumpyDenseBackend())
        scorer = StubScorer()
        reader = StubReader()
        llm: ChatModel | None = StubLLM()
        count_tokens = count_words
    elif settings.backend == "real":
        if not settings.qdrant_url:
            raise ValueError("CONSULTQA_QDRANT_URL is required")
        url = settings.qdrant_url
        sentence_encoder = SentenceEncoder(ENCODER_SPECS["bge-m3"])
        encoder = sentence_encoder
        dense_stores = _DenseStores(
            lambda cid, dim: QdrantDenseBackend(url, QDRANT_COLLECTION_PREFIX + cid, dim)
        )
        load_scorer = load_cross_encoder
        load_reader = ExtractiveReader
        warm_parser = parser.warm_up
        llm = _llm_client(settings)
        count_tokens = sentence_encoder.count_tokens
    else:
        raise ValueError(f"unknown backend: {settings.backend!r}")

    return Services(
        settings=settings,
        store=store,
        encoder=encoder,
        make_dense=dense_stores,
        parser=parser,
        scorer=scorer,
        reader=reader,
        llm=llm,
        paper_enabled=settings.enable_paper_baseline,
        jobs=JobRunner() if jobs is None else jobs,
        ready=threading.Event(),
        count_tokens=count_tokens,
        forget_dense=dense_stores.forget,
        originals=OriginalFiles(settings.state_dir / "files"),
        load_scorer=load_scorer,
        load_reader=load_reader,
        warm_parser=warm_parser,
    )


def load_in_background(services: Services) -> threading.Thread:
    """Load the models in a daemon thread; ``services.ready`` is set once all of them are loaded.

    A failed load is logged and leaves ``ready`` unset, so ``/api/ready`` keeps answering 503.
    """
    thread = threading.Thread(target=_load, args=(services,), name="consultqa-loader", daemon=True)
    thread.start()
    return thread


def _load(services: Services) -> None:
    """Load the encoder, then the reranker, then the reader, and only then set ``ready``.

    The steps run one after another: loading two models in parallel crashed ("meta tensor"). After
    ``ready`` is set, the parser is warmed, so readiness does not wait for Docling.
    """
    try:
        services.embedding_dimension()  # loads the sentence model
        if services.load_scorer is not None:
            services.scorer = services.load_scorer()
        if services.load_reader is not None:
            services.reader = services.load_reader()
    except Exception:
        logger.exception("model loading failed; /api/ready stays unavailable")
        return
    services.ready.set()
    _warm_parser(services)


def _warm_parser(services: Services) -> None:
    """Warm the parser's PDF pipeline. A failure is logged and the first PDF loads it instead."""
    if services.warm_parser is None:
        return
    try:
        services.warm_parser()
    except Exception:
        logger.exception("Docling warm-up failed; the first PDF will load the pipeline")


class _DenseStores:
    """One dense store per collection: built by ``factory`` on first use, shared afterwards, and
    dropped from the cache by ``forget`` when its collection is deleted."""

    def __init__(self, factory: Callable[[str, int], DenseBackend]) -> None:
        self._factory = factory
        self._stores: dict[str, DenseBackend] = {}
        self._lock = threading.Lock()

    def __call__(self, cid: str, dim: int) -> DenseBackend:
        with self._lock:
            if cid not in self._stores:
                self._stores[cid] = self._factory(cid, dim)
            return self._stores[cid]

    def forget(self, cid: str) -> None:
        with self._lock:
            self._stores.pop(cid, None)


def _llm_client(settings: Settings) -> LLMClient | None:
    if not settings.llm_base_url:
        return None
    if not settings.llm_model:
        raise ValueError("CONSULTQA_LLM_MODEL is required when CONSULTQA_LLM_BASE_URL is set")
    return LLMClient(settings.llm_base_url, settings.llm_model, api_key=settings.llm_api_key)
