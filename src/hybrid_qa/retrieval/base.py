"""Shared types for passage retrieval: hits, encoders and the retriever protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from hybrid_qa.corpus import Passage


@dataclass(frozen=True)
class Hit:
    """A retrieved passage with its retriever score and the meaning of that score."""

    passage: Passage
    score: float
    score_type: str = "unknown"


class Encoder(Protocol):
    """Anything that turns a list of texts into a 2D array of embeddings."""

    def encode(self, texts: list[str]) -> np.ndarray:
        """Return one embedding row per input text."""
        ...


class Retriever(Protocol):
    """Anything that returns the top-k hits for a query, best first."""

    def search(self, query: str, k: int) -> list[Hit]:
        """Return up to k hits for the query, best first."""
        ...
