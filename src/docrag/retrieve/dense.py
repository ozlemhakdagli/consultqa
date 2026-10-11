"""Dense retrieval: sentence encoders, an exact numpy vector index and the dense channel."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from docrag.config import MODEL_PINS
from docrag.models import Chunk, Hit


class Encoder(Protocol):
    """Maps texts to L2-normalised float32 vectors."""

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        """Return one row per passage text."""
        ...

    def encode_query(self, text: str) -> np.ndarray:
        """Return the vector of one query text."""
        ...


class DenseBackend(Protocol):
    """A store of passage vectors that answers nearest-neighbour queries."""

    def upsert(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        """Insert or replace the vectors of the given ids."""
        ...

    def delete(self, ids: Sequence[str]) -> None:
        """Remove the vectors of the given ids; unknown ids are ignored."""
        ...

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        """Return up to ``k`` ``(id, cosine)`` pairs, best first."""
        ...


def _normalise_rows(matrix: np.ndarray) -> np.ndarray:
    """L2-normalise each row (or the single vector); zero vectors stay zero."""
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


class NumpyDenseBackend:
    """Exact cosine search over vectors held in memory."""

    def __init__(self) -> None:
        self._vectors: dict[str, np.ndarray] = {}
        self._cache: tuple[list[str], np.ndarray] | None = None

    def upsert(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape[0] != len(ids):
            raise ValueError("ids and vectors must have the same length")
        for chunk_id, row in zip(ids, _normalise_rows(matrix), strict=True):
            self._vectors[chunk_id] = row
        self._cache = None

    def delete(self, ids: Sequence[str]) -> None:
        for chunk_id in ids:
            self._vectors.pop(chunk_id, None)
        self._cache = None

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        if k <= 0 or not self._vectors:
            return []
        if self._cache is None:
            ids = list(self._vectors)
            self._cache = (ids, np.stack([self._vectors[i] for i in ids]))
        ids, matrix = self._cache
        query = _normalise_rows(np.asarray(vector, dtype=np.float32))
        scores = matrix @ query
        order = np.argsort(-scores, kind="stable")[:k]
        return [(ids[i], float(scores[i])) for i in order]


class DenseChannel:
    """Retrieves chunks by cosine similarity between the query and the passage vectors."""

    def __init__(
        self, chunks: Mapping[str, Chunk], encoder: Encoder, backend: DenseBackend
    ) -> None:
        self._chunks = chunks
        self._encoder = encoder
        self._backend = backend

    def search(self, query: str, k: int) -> list[Hit]:
        vector = self._encoder.encode_query(query)
        hits: list[Hit] = []
        for chunk_id, score in self._backend.search(vector, k):
            chunk = self._chunks.get(chunk_id)
            if chunk is None:
                continue
            hits.append(Hit(chunk=chunk, score=score, score_type="cosine", channel="dense"))
        return hits


@dataclass(frozen=True)
class EncoderSpec:
    """How one pinned sentence-embedding model is called."""

    model_key: str
    query_prefix: str = ""
    passage_prefix: str = ""


ENCODER_SPECS: dict[str, EncoderSpec] = {
    "bge-m3": EncoderSpec(model_key="bge-m3"),
    "e5-small": EncoderSpec(
        model_key="e5-small", query_prefix="query: ", passage_prefix="passage: "
    ),
}


class SentenceEncoder:
    """A pinned sentence-transformers model, loaded on first use."""

    def __init__(self, spec: EncoderSpec) -> None:
        self._spec = spec
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            # Deferred so that importing this module does not load the ML stack.
            from sentence_transformers import SentenceTransformer

            model_id, revision = MODEL_PINS[self._spec.model_key]
            self._model = SentenceTransformer(model_id, revision=revision)
        return self._model

    def _encode(self, texts: list[str]) -> np.ndarray:
        model = self._load()
        if not texts:
            return np.zeros((0, model.get_sentence_embedding_dimension()), dtype=np.float32)
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype=np.float32)

    def encode_passages(self, texts: Sequence[str]) -> np.ndarray:
        return self._encode([self._spec.passage_prefix + text for text in texts])

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode([self._spec.query_prefix + text])[0]

    def count_tokens(self, text: str) -> int:
        return len(self._load().tokenizer.encode(text))
