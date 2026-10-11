# tests/test_retrieval_pipeline.py
import pytest

from consultqa.config import PRESETS
from consultqa.graph.build import build_graph
from consultqa.models import Chunk, Hit
from consultqa.retrieve.pipeline import Retriever


class FakeChannel:
    def __init__(self, hits):
        self.hits = hits
        self.calls = 0

    def search(self, query, k):
        self.calls += 1
        return self.hits[:k]


def _chunk(cid, text=None):
    return Chunk(cid, "d", 0, (), text or cid)


def _hit(cid, channel):
    return Hit(_chunk(cid), 1.0, "cosine", channel)


def test_blank_query_calls_no_channel():
    dense = FakeChannel([_hit("a", "dense")])
    sparse = FakeChannel([])
    retriever = Retriever(PRESETS["L2"], [_chunk("a")], dense=dense, sparse=sparse)
    result = retriever.retrieve("   ")
    assert result.hits == []
    assert result.trace == []
    assert dense.calls == 0
    assert sparse.calls == 0


# [R2] A punctuation-only question reaches the dense channel only.
def test_punctuation_query_still_returns_dense_candidates():
    dense = FakeChannel([_hit("a", "dense")])
    retriever = Retriever(PRESETS["L2"], [_chunk("a")], dense=dense, sparse=FakeChannel([]))
    result = retriever.retrieve("?!")
    assert [h.chunk.chunk_id for h in result.hits] == ["a"]


def test_l2_is_rrf_of_dense_and_sparse():
    dense = FakeChannel([_hit("a", "dense"), _hit("b", "dense")])
    sparse = FakeChannel([_hit("b", "sparse"), _hit("c", "sparse")])
    chunks = [_chunk(x) for x in "abc"]
    result = Retriever(PRESETS["L2"], chunks, dense=dense, sparse=sparse).retrieve("q")
    assert [h.chunk.chunk_id for h in result.hits] == ["b", "a", "c"]


def test_missing_graph_is_reported():
    with pytest.raises(ValueError, match="graph"):
        Retriever(
            PRESETS["L5"],
            [_chunk("a")],
            dense=FakeChannel([]),
            sparse=FakeChannel([]),
        )


def test_graph_reaches_a_chunk_the_seeds_miss():
    chunks = [
        Chunk("d#0", "d", 0, (), "Stok modülü"),
        Chunk("d#1", "d", 1, (), "Stok raporu"),
    ]
    graph = build_graph(chunks)
    dense = FakeChannel([_hit("d#0", "dense")])
    retriever = Retriever(
        PRESETS["L5"],
        chunks,
        dense=dense,
        sparse=FakeChannel([]),
        graph=graph,
        scorer=lambda q, t: [0.0] * len(t),
    )
    ids = [h.chunk.chunk_id for h in retriever.retrieve("stok").hits]
    assert "d#1" in ids
