"""Retrieval pipeline: hybrid seeds, optional graph expansion and reranking, with a stage trace."""

from collections.abc import Sequence
from dataclasses import dataclass

from docrag.config import PipelineConfig
from docrag.graph.build import EvidenceGraph
from docrag.graph.expand import expand
from docrag.graph.terms import extract_terms
from docrag.models import Chunk, Hit
from docrag.retrieve.dense import DenseChannel
from docrag.retrieve.fusion import dedupe_by_text, rrf_fuse
from docrag.retrieve.rerank import Scorer, rerank
from docrag.retrieve.sparse import SparseChannel


@dataclass(frozen=True)
class TraceEntry:
    """One ranked chunk as it left one stage of the pipeline."""

    stage: str
    chunk_id: str
    rank: int
    score: float
    score_type: str
    channel: str


@dataclass(frozen=True)
class RetrievalResult:
    """The ranked pool of one query and the trace of every stage that ran."""

    hits: list[Hit]
    trace: list[TraceEntry]


def _trace(stage: str, hits: Sequence[Hit]) -> list[TraceEntry]:
    """Return one entry per hit, with 1-based ranks in the order given."""
    return [
        TraceEntry(stage, hit.chunk.chunk_id, rank, hit.score, hit.score_type, hit.channel)
        for rank, hit in enumerate(hits, start=1)
    ]


class Retriever:
    """Runs the stages that a ``PipelineConfig`` enables, for one collection."""

    def __init__(
        self,
        cfg: PipelineConfig,
        chunks: Sequence[Chunk],
        *,
        dense: DenseChannel | None = None,
        sparse: SparseChannel | None = None,
        graph: EvidenceGraph | None = None,
        scorer: Scorer | None = None,
    ) -> None:
        if cfg.use_sparse and sparse is None:
            raise ValueError("use_sparse is set but no sparse channel was given")
        if cfg.use_graph and graph is None:
            raise ValueError("use_graph is set but no graph was given")
        if cfg.use_reranker and scorer is None:
            raise ValueError("use_reranker is set but no scorer was given")
        self._cfg = cfg
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self._dense = dense
        self._sparse = sparse
        self._graph = graph
        self._scorer = scorer

    def retrieve(self, query: str) -> RetrievalResult:
        """Return the ranked pool for ``query``, or an empty result for a blank query."""
        if not query.strip():
            return RetrievalResult(hits=[], trace=[])

        cfg = self._cfg
        trace: list[TraceEntry] = []

        channel_lists: list[list[Hit]] = []
        if self._dense is not None:
            dense_hits = self._dense.search(query, cfg.seed_k)
            trace += _trace("dense", dense_hits)
            channel_lists.append(dense_hits)
        if cfg.use_sparse:
            sparse_hits = self._sparse.search(query, cfg.seed_k)
            trace += _trace("sparse", sparse_hits)
            channel_lists.append(sparse_hits)

        seeds = rrf_fuse(channel_lists, k=cfg.seed_k, rrf_k=cfg.rrf_k)
        trace += _trace("seed-rrf", seeds)

        if cfg.use_graph:
            graph_hits = expand(
                self._graph,
                {hit.chunk.chunk_id: hit.score for hit in seeds},
                extract_terms(query),
                self._chunks_by_id,
                restart=cfg.graph_restart,
                k=cfg.graph_k,
            )
            trace += _trace("graph", graph_hits)
            pool_src = rrf_fuse([seeds, graph_hits], k=cfg.seed_k + cfg.graph_k, rrf_k=cfg.rrf_k)
        else:
            pool_src = seeds

        pool = dedupe_by_text(pool_src)
        trace += _trace("pool", pool)

        if cfg.use_reranker:
            ranked = rerank(query, pool, self._scorer, depth=cfg.pool_k, k=cfg.pool_k)
            trace += _trace("rerank", ranked)
        else:
            ranked = pool[: cfg.pool_k]

        return RetrievalResult(hits=ranked, trace=trace)
