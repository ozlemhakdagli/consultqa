"""Keyword passage retrieval with Okapi BM25."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from hybrid_qa.config import SPARSE_TOP_K
from hybrid_qa.corpus import Passage
from hybrid_qa.retrieval.base import Hit
from hybrid_qa.text import reference_tokens


class BM25Retriever:
    """Keyword retrieval with BM25 over tokens produced by a configurable tokenizer."""

    def __init__(
        self,
        passages: list[Passage],
        tokenizer: Callable[[str], list[str]] = reference_tokens,
        text_fn: Callable[[Passage], str] = lambda p: p.text,
        min_score: float | None = None,
    ) -> None:
        """Index passages by text_fn output; drop hits scoring at or below min_score."""
        from rank_bm25 import BM25Okapi

        self._passages = list(passages)
        self._tokenizer = tokenizer
        self._min_score = min_score
        self._bm25 = BM25Okapi([self._tokenizer(text_fn(p)) for p in self._passages])

    def search(self, query: str, k: int = SPARSE_TOP_K) -> list[Hit]:
        """Return up to k passages with the highest BM25 score, best first."""
        scores = self._bm25.get_scores(self._tokenizer(query))
        top = np.argsort(scores)[::-1][:k]
        hits = [
            Hit(passage=self._passages[i], score=float(scores[i]), score_type="bm25") for i in top
        ]
        if self._min_score is not None:
            hits = [h for h in hits if h.score > self._min_score]
        return hits
