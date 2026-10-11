# tests/test_fusion.py
import pytest

from consultqa.models import Chunk, Hit
from consultqa.retrieve.fusion import dedupe_by_text, rrf_fuse


def _hit(cid, text=None):
    return Hit(Chunk(cid, "d", 0, (), text or cid), 1.0, "cosine", "dense")


def test_rrf_hand_computed_order():
    # a: 1/61; b: 1/62 + 1/61; c: 1/62
    out = rrf_fuse([[_hit("a"), _hit("b")], [_hit("b"), _hit("c")]], k=10, rrf_k=60)
    assert [h.chunk.chunk_id for h in out] == ["b", "a", "c"]
    assert out[0].score == pytest.approx(1 / 62 + 1 / 61)


def test_rrf_counts_a_repeated_chunk_once_per_channel():
    out = rrf_fuse([[_hit("a"), _hit("a")]], k=10, rrf_k=60)
    assert len(out) == 1 and out[0].score == pytest.approx(1 / 61)


def test_dedupe_by_text_keeps_the_first():
    out = dedupe_by_text([_hit("a", "same"), _hit("b", "same"), _hit("c", "other")])
    assert [h.chunk.chunk_id for h in out] == ["a", "c"]
