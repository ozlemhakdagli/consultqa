"""Deterministic stand-ins for model-backed components, used by tests and the stub backend."""

import hashlib
import re
from collections.abc import Sequence

import numpy as np

from docrag.config import ABSTAIN_WORD
from docrag.text import tokenize_tr

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_FIRST_PASSAGE = re.compile(r'<passage n="1">\n(.*?)\n</passage>', re.DOTALL)


class HashEncoder:
    """Hashing bag-of-words encoder. It loads no model and gives the same vectors in every process.

    Each token adds a signed unit to one dimension, chosen by a ``blake2b`` digest
    (never Python's ``hash()``, which is randomised per process).
    """

    def __init__(self, dim: int = 64) -> None:
        if dim < 1:
            raise ValueError("dim must be at least 1")
        self.dim = dim

    def _vector(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        for token in tokenize_tr(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = float(np.linalg.norm(vector))
        return vector / norm if norm > 0 else vector

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.stack([self._vector(text) for text in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._vector(text)


class StubScorer:
    """Cross-encoder stand-in: scores each text by the number of distinct query tokens it shares."""

    def __call__(self, query: str, texts: Sequence[str]) -> list[float]:
        query_tokens = set(tokenize_tr(query))
        return [float(len(query_tokens & set(tokenize_tr(text)))) for text in texts]


class StubReader:
    """Extractive reader stand-in: answers with the first sentence of the context, score 1.0."""

    def answer_span(self, question: str, context: str) -> tuple[str, float]:
        text = context.strip()
        if not text:
            return "", 0.0
        return _SENTENCE_END.split(text, maxsplit=1)[0].strip(), 1.0


class StubLLM:
    """LLM stand-in: repeats the text of passage 1 with a ``[1]`` citation, or abstains."""

    def chat(self, messages: list[dict[str, str]]) -> str:
        match = _FIRST_PASSAGE.search(messages[-1]["content"])
        if match is None:
            return ABSTAIN_WORD
        return f"{match.group(1)} [1]"
