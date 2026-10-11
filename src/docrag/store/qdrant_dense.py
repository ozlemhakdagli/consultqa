"""Qdrant-backed dense vector store: the service's dense index, behind the DenseBackend protocol."""

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

import httpx
import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import ResponseHandlingException
from qdrant_client.models import Distance, PointIdsList, PointStruct, VectorParams

# Fixed namespace so that a chunk id always maps to the same Qdrant point id.
POINT_NAMESPACE = uuid.UUID("2af8b78d-4a1c-4f7d-be13-f6e1c5c73e40")


def _point_id(chunk_id: str) -> str:
    return str(uuid.uuid5(POINT_NAMESPACE, chunk_id))


@contextmanager
def _reachable() -> Iterator[None]:
    """Report a server that cannot be reached as ``ConnectionError``, which the API maps to 503.

    The qdrant client wraps the transport failure, so both the wrapper and its cause are checked.
    A reply the client could not parse is not a connection problem and is re-raised unchanged.
    """
    try:
        yield
    except (httpx.TransportError, ResponseHandlingException) as exc:
        cause = exc.__cause__ or exc.__context__
        if isinstance(exc, httpx.TransportError) or isinstance(cause, httpx.TransportError):
            raise ConnectionError("vector store unavailable") from exc
        raise


class QdrantDenseBackend:
    """Cosine nearest-neighbour search over one Qdrant collection of passage vectors."""

    def __init__(self, url: str, collection: str, dim: int) -> None:
        with _reachable():
            self._client = QdrantClient(url=url)
            self._collection = collection
            if not self._client.collection_exists(collection):
                self._client.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                )

    def upsert(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.shape[0] != len(ids):
            raise ValueError("ids and vectors must have the same length")
        if not ids:
            return
        points = [
            PointStruct(id=_point_id(chunk_id), vector=row.tolist(), payload={"chunk_id": chunk_id})
            for chunk_id, row in zip(ids, matrix, strict=True)
        ]
        with _reachable():
            self._client.upsert(collection_name=self._collection, points=points)

    def delete(self, ids: Sequence[str]) -> None:
        if not ids:
            return
        with _reachable():
            self._client.delete(
                collection_name=self._collection,
                points_selector=PointIdsList(points=[_point_id(chunk_id) for chunk_id in ids]),
            )

    def search(self, vector: np.ndarray, k: int) -> list[tuple[str, float]]:
        if k <= 0:
            return []
        with _reachable():
            response = self._client.query_points(
                collection_name=self._collection,
                query=np.asarray(vector, dtype=np.float32).tolist(),
                limit=k,
            )
        return [(point.payload["chunk_id"], float(point.score)) for point in response.points]
