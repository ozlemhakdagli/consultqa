"""Tests for dense, sparse and hybrid retrieval.

A deterministic bag-of-words encoder replaces the sentence-transformer model,
so no embedding model is downloaded.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hybrid_qa.data_loader import Passage  # noqa: E402
from hybrid_qa.retrieval import DenseRetriever, HybridRetriever  # noqa: E402


class BagOfWordsEncoder:
    """Encodes texts as word-count vectors over a fixed vocabulary."""

    def __init__(self, texts: list[str]) -> None:
        words = sorted({w for t in texts for w in t.lower().split()})
        self._vocab = {w: i for i, w in enumerate(words)}

    def encode(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), len(self._vocab)), dtype=np.float32)
        for row, text in enumerate(texts):
            for word in text.lower().split():
                if word in self._vocab:
                    vectors[row, self._vocab[word]] += 1.0
        return vectors


def make_passages() -> list[Passage]:
    return [
        Passage("d1", "u1", "1.0", "Batarya ömrü iyileştirildi"),
        Passage("d2", "u2", "1.1", "Kamera yazılımı güncellendi ve fotoğraf kalitesi arttı"),
        Passage("d3", "u3", "1.2", "Bluetooth bağlantı sorunları giderildi"),
        Passage("d4", "u4", "1.3", "Harita uygulamasına yeni dil desteği eklendi"),
        # Same text as d1 but a different document: exercises deduplication.
        Passage("d5", "u5", "1.0", "Batarya ömrü iyileştirildi"),
    ]


@pytest.fixture
def passages() -> list[Passage]:
    return make_passages()


@pytest.fixture
def encoder(passages: list[Passage]) -> BagOfWordsEncoder:
    return BagOfWordsEncoder([p.text for p in passages] + ["bluetooth kamera harita"])


def test_dense_top_hit_for_exact_passage_text(passages, encoder):
    dense = DenseRetriever(passages, encoder=encoder)
    target = passages[1]

    hits = dense.search(target.text, k=3)

    assert hits[0].passage == target
    assert hits[0].score == pytest.approx(0.0, abs=1e-5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_bm25_top_hit_for_keyword_query(passages):
    pytest.importorskip("rank_bm25")
    from hybrid_qa.retrieval import BM25Retriever

    sparse = BM25Retriever(passages)

    hits = sparse.search("bluetooth", k=3)

    assert hits[0].passage == passages[2]
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_hybrid_dedupes_and_caps_at_top_k(passages, encoder):
    pytest.importorskip("rank_bm25")
    from hybrid_qa.retrieval import BM25Retriever

    dense = DenseRetriever(passages, encoder=encoder)
    sparse = BM25Retriever(passages)
    hybrid = HybridRetriever(dense, sparse, top_k=3)

    # "batarya" matches d1 and d5, which share the same text.
    result = hybrid.search("batarya ömrü")

    assert len(result) == 3
    texts = [p.text for p in result]
    assert len(set(texts)) == len(texts)


def test_hybrid_orders_dense_hits_before_sparse_hits(passages, encoder):
    pytest.importorskip("rank_bm25")
    from hybrid_qa.retrieval import BM25Retriever

    dense = DenseRetriever(passages, encoder=encoder)
    sparse = BM25Retriever(passages)
    hybrid = HybridRetriever(dense, sparse, top_k=len(passages))
    query = "harita bluetooth"

    # Expected: all dense hits in order, then sparse hits not already seen.
    expected: list[Passage] = []
    seen: set[str] = set()
    for hit in dense.search(query) + sparse.search(query):
        if hit.passage.text not in seen:
            seen.add(hit.passage.text)
            expected.append(hit.passage)

    result = hybrid.search(query)

    assert result == expected
    assert result[0] == dense.search(query)[0].passage


def test_dense_loads_sentence_transformer_at_pinned_revision(monkeypatch):
    import sys
    import types

    from hybrid_qa.config import EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION

    calls = []

    class _FakeST:
        def __init__(self, name, **kwargs):
            calls.append((name, kwargs))

        def encode(self, texts):
            return np.ones((len(texts), 4), dtype=np.float32)

    monkeypatch.setitem(
        sys.modules, "sentence_transformers", types.SimpleNamespace(SentenceTransformer=_FakeST)
    )
    passages = [Passage(doc_id="d", update_id="1", version="1", description="metin")]
    DenseRetriever(passages)

    assert calls == [(EMBEDDING_MODEL, {"revision": EMBEDDING_MODEL_REVISION})]
    assert EMBEDDING_MODEL_REVISION == "17997f24dca0df1a4fed68894fb0e1e133e60482"
