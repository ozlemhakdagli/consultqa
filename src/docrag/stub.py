"""Deterministic stand-ins for model-backed components, used by tests and the stub backend."""

import hashlib
from collections.abc import Sequence

import numpy as np

from docrag.text import tokenize_tr


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
