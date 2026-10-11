"""Sparse retrieval: in-process Turkish BM25 over the chunks of one collection."""

from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from docrag.config import BM25_PREFIX_LEN
from docrag.models import Chunk, Hit
from docrag.text import tokenize_tr


class SparseChannel:
    """Ranks chunks by BM25 over Turkish prefix-stemmed tokens."""

    def __init__(self, chunks: Sequence[Chunk], *, prefix: int | None = BM25_PREFIX_LEN) -> None:
        self._chunks = list(chunks)
        self._prefix = prefix
        corpus = [tokenize_tr(chunk.text, prefix) for chunk in self._chunks]
        # BM25Okapi divides by the vocabulary size, so it cannot be built when no chunk has a token.
        self._index = BM25Okapi(corpus) if any(corpus) else None

    def search(self, query: str, k: int) -> list[Hit]:
        """Return up to ``k`` chunks with a positive BM25 score, best first."""
        if self._index is None:
            return []
        terms = tokenize_tr(query, self._prefix)
        if not terms:
            return []
        scores = self._index.get_scores(terms)
        ranked = sorted(
            (i for i in range(len(self._chunks)) if scores[i] > 0),
            key=lambda i: -scores[i],
        )
        return [
            Hit(
                chunk=self._chunks[i],
                score=float(scores[i]),
                score_type="bm25",
                channel="sparse",
            )
            for i in ranked[:k]
        ]
