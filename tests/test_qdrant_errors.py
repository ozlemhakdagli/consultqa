"""A Qdrant server that cannot be reached raises ConnectionError, which the API maps to 503."""

import httpx
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

from docrag.store import qdrant_dense
from docrag.store.qdrant_dense import QdrantDenseBackend


def _refuse() -> None:
    """Raise what the qdrant client raises when the server refuses the connection."""
    try:
        raise httpx.ConnectError("[Errno 111] Connection refused")
    except httpx.ConnectError as exc:
        raise ResponseHandlingException(exc) from exc


class _DownClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def collection_exists(self, collection_name, **kwargs):
        _refuse()


class _SearchDownClient(_DownClient):
    def collection_exists(self, collection_name, **kwargs):
        return True

    def query_points(self, **kwargs):
        _refuse()


def test_unreachable_server_at_startup_is_a_connection_error(monkeypatch):
    monkeypatch.setattr(qdrant_dense, "QdrantClient", _DownClient)
    with pytest.raises(ConnectionError):
        QdrantDenseBackend("http://qdrant:6333", "docrag_c", 8)


def test_unreachable_server_during_search_is_a_connection_error(monkeypatch):
    import numpy as np

    monkeypatch.setattr(qdrant_dense, "QdrantClient", _SearchDownClient)
    backend = QdrantDenseBackend("http://qdrant:6333", "docrag_c", 8)
    with pytest.raises(ConnectionError):
        backend.search(np.ones(8, dtype=np.float32), k=3)
