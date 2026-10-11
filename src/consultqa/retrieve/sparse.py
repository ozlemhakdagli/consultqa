"""Sparse retrieval: in-process BM25 over the chunks of one collection.

Turkish casefolding by default. With the per-document fold on, a document without Turkish
letters is lowercased with the default rule instead, so English capital letters match.
"""

from collections.abc import Sequence

from rank_bm25 import BM25Okapi

from consultqa.config import BM25_PREFIX_LEN
from consultqa.models import Chunk, Hit
from consultqa.text import casefold_neutral, document_folds, tokenize, tokenize_tr

# With fewer chunks than this, the BM25 IDF of every term is zero or negative, so BM25 cannot
# rank them. Such collections are ranked by the number of distinct query tokens they share.
BM25_MIN_CHUNKS = 3


class SparseChannel:
    """Ranks chunks by BM25 over prefix-stemmed tokens.

    Collections of fewer than ``BM25_MIN_CHUNKS`` chunks are ranked by shared query tokens.

    With ``per_document_fold`` off (the default, used by the evaluation), every chunk and every
    question is folded with the Turkish rule. With it on, each document is folded by its own
    language (see ``document_folds``), and a question is also matched under the default rule
    when the library holds a document without Turkish letters.
    """

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        prefix: int | None = BM25_PREFIX_LEN,
        per_document_fold: bool = False,
    ) -> None:
        self._chunks = list(chunks)
        self._prefix = prefix
        if per_document_fold:
            folds = document_folds(self._chunks)
            self._corpus = [
                tokenize(chunk.text, prefix, fold=folds[chunk.doc_id]) for chunk in self._chunks
            ]
            self._has_neutral = any(fold is casefold_neutral for fold in folds.values())
        else:
            self._corpus = [tokenize_tr(chunk.text, prefix) for chunk in self._chunks]
            self._has_neutral = False
        # BM25Okapi divides by the vocabulary size, so it cannot be built when no chunk has a token.
        use_bm25 = len(self._chunks) >= BM25_MIN_CHUNKS and any(self._corpus)
        self._index = BM25Okapi(self._corpus) if use_bm25 else None

    def search(self, query: str, k: int) -> list[Hit]:
        """Return up to ``k`` chunks with a positive score, best first."""
        if not any(self._corpus):
            return []
        terms = self._query_terms(query)
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

    def _query_terms(self, query: str) -> list[str]:
        """The query tokens under the Turkish rule, then the default-rule spelling of each token
        that differs, but only when the library holds a document folded by the default rule."""
        turkish = tokenize_tr(query, self._prefix)
        if not self._has_neutral:
            return turkish
        neutral = tokenize(query, self._prefix, fold=casefold_neutral)
        return turkish + [n for t, n in zip(turkish, neutral, strict=False) if t != n]

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
