"""Sparse retrieval: in-process Turkish BM25 over the chunks of one collection."""

from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from consultqa.config import BM25_PREFIX_LEN
from consultqa.models import Chunk, Hit
from consultqa.text import tokenize_tr

# With fewer chunks than this, the BM25 IDF of every term is zero or negative, so BM25 cannot
# rank them. Such collections are ranked by the number of distinct query tokens they share.
BM25_MIN_CHUNKS = 3


class SparseChannel:
    """Ranks chunks by BM25 over Turkish prefix-stemmed tokens.

    Collections of fewer than ``BM25_MIN_CHUNKS`` chunks are ranked by shared query tokens.
    """

    def __init__(self, chunks: Sequence[Chunk], *, prefix: int | None = BM25_PREFIX_LEN) -> None:
        self._chunks = list(chunks)
        self._prefix = prefix
        self._corpus = [tokenize_tr(chunk.text, prefix) for chunk in self._chunks]
        # BM25Okapi divides by the vocabulary size, so it cannot be built when no chunk has a token.
        use_bm25 = len(self._chunks) >= BM25_MIN_CHUNKS and any(self._corpus)
        self._index = BM25Okapi(self._corpus) if use_bm25 else None

    def search(self, query: str, k: int) -> list[Hit]:
        """Return up to ``k`` chunks with a positive score, best first."""
        if not any(self._corpus):
            return []
        terms = tokenize_tr(query, self._prefix)
        if not terms:
            return []
        if self._index is None:
            return self._search_shared_tokens(terms, k)
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

    def _search_shared_tokens(self, terms: list[str], k: int) -> list[Hit]:
        """Rank chunks by the number of distinct query tokens they contain, if at least one."""
        query_tokens = set(terms)
        overlaps = [len(query_tokens & set(tokens)) for tokens in self._corpus]
        ranked = sorted((i for i, n in enumerate(overlaps) if n > 0), key=lambda i: -overlaps[i])
        return [
            Hit(
                chunk=self._chunks[i],
                score=float(overlaps[i]),
                score_type="overlap",
                channel="sparse",
            )
            for i in ranked[:k]
        ]
