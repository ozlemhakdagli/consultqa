"""End-to-end question answering: hybrid retrieval followed by extractive QA."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import NO_CONTEXT_ANSWER
from .data_loader import Passage, load_passages
from .qa import AnswerExtractor
from .retrieval import BM25Retriever, DenseRetriever, HybridRetriever

RETRIEVER_MODES = ("dense", "sparse", "hybrid")


class PassageSearch(Protocol):
    """Anything that returns ranked passages for a query."""

    def search(self, query: str) -> list[Passage]: ...


@dataclass(frozen=True)
class Answer:
    question: str
    text: str
    source: Passage | None


class HybridQASystem:
    def __init__(self, retriever: PassageSearch, extractor: AnswerExtractor) -> None:
        self.retriever = retriever
        self.extractor = extractor

    def answer(self, question: str) -> Answer:
        passages = self.retriever.search(question)
        if not passages:
            return Answer(question=question, text=NO_CONTEXT_ANSWER, source=None)

        # Only the best-ranked passage is used as context, as in the reference notebook.
        best = passages[0]
        text = self.extractor.answer(question, best.text)
        if not text:
            text = NO_CONTEXT_ANSWER
        return Answer(question=question, text=text, source=best)


class _HitsAsPassages:
    """Adapt a retriever that returns scored hits to the passage-only interface."""

    def __init__(self, retriever: DenseRetriever | BM25Retriever) -> None:
        self._retriever = retriever

    def search(self, query: str) -> list[Passage]:
        return [hit.passage for hit in self._retriever.search(query)]


def build_retriever(
    mode: str,
    dense: DenseRetriever,
    sparse: BM25Retriever,
) -> PassageSearch:
    """Select the retrieval strategy: FAISS only, BM25 only, or the hybrid of both."""
    if mode == "dense":
        return _HitsAsPassages(dense)
    if mode == "sparse":
        return _HitsAsPassages(sparse)
    if mode == "hybrid":
        return HybridRetriever(dense, sparse)
    raise ValueError(f"Unknown retriever mode: {mode!r}; expected one of {RETRIEVER_MODES}")


def build_system(passages: list[Passage] | None = None, mode: str = "hybrid") -> HybridQASystem:
    """Build the full system. Models are loaded here, not at import time."""
    if passages is None:
        passages = load_passages()

    dense = DenseRetriever(passages)
    sparse = BM25Retriever(passages)
    return HybridQASystem(build_retriever(mode, dense, sparse), AnswerExtractor())
