# tests/test_rerank.py
import pytest

from consultqa.models import Chunk, Hit
from consultqa.retrieve.rerank import rerank


def _hits(texts):
    return [Hit(Chunk(f"d#{i}", "d", i, (), t), 0.0, "rrf", "rrf") for i, t in enumerate(texts)]


def test_scorer_orders_the_pool():
    seen = {}

    def scorer(query, texts):
        seen["texts"] = list(texts)
        return [float(len(t)) for t in texts]  # longer is better

    out = rerank("q", _hits(["aa", "a", "aaaa"]), scorer, depth=3, k=3)
    assert [h.chunk.text for h in out] == ["aaaa", "aa", "a"]
    assert [h.channel for h in out] == ["rerank"] * 3


def test_depth_limits_what_is_scored():
    seen = {}

    def scorer(query, texts):
        seen["n"] = len(texts)
        return [0.0] * len(texts)

    rerank("q", _hits(["a", "b", "c"]), scorer, depth=2, k=2)
    assert seen["n"] == 2


def test_wrong_score_count_raises():
    with pytest.raises(ValueError):
        rerank("q", _hits(["a", "b"]), lambda q, t: [1.0], depth=2, k=2)
