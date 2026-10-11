"""Combining dense and sparse retrievers into hybrid rankings."""

from __future__ import annotations

from hybrid_qa.config import FINAL_TOP_K
from hybrid_qa.corpus import Passage
from hybrid_qa.retrieval.base import Retriever


class HybridRetriever:
    """Dense hits first, then sparse hits, deduplicated by passage text."""

    def __init__(
        self,
        dense: Retriever,
        sparse: Retriever,
        top_k: int = FINAL_TOP_K,
    ) -> None:
        self._dense = dense
        self._sparse = sparse
        self._top_k = top_k

    def search(self, query: str) -> list[Passage]:
        """Return up to top_k unique passages for the query."""
        candidates = self._dense.search(query) + self._sparse.search(query)

        seen: set[str] = set()
        unique: list[Passage] = []
        for hit in candidates:
            if hit.passage.text in seen:
                continue
            seen.add(hit.passage.text)
            unique.append(hit.passage)
        return unique[: self._top_k]
