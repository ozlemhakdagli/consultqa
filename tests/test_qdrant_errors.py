"""A Qdrant server that cannot be reached raises ConnectionError, which the API maps to 503."""

from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from qdrant_client.http.exceptions import ResponseHandlingException

from consultqa.store import qdrant_dense
from consultqa.store.qdrant_dense import QdrantDenseBackend, _point_id


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
        QdrantDenseBackend("http://qdrant:6333", "consultqa_c", 8)


def test_unreachable_server_during_search_is_a_connection_error(monkeypatch):
    monkeypatch.setattr(qdrant_dense, "QdrantClient", _SearchDownClient)
    backend = QdrantDenseBackend("http://qdrant:6333", "consultqa_c", 8)
    with pytest.raises(ConnectionError):
        backend.search(np.ones(8, dtype=np.float32), k=3)


def test_unreachable_server_during_scoped_search_is_a_connection_error(monkeypatch):
    monkeypatch.setattr(qdrant_dense, "QdrantClient", _SearchDownClient)
    backend = QdrantDenseBackend("http://qdrant:6333", "consultqa_c", 8)
    with pytest.raises(ConnectionError):
        backend.search(np.ones(8, dtype=np.float32), k=3, allowed={"d#0", "d#1"})


class _RecordingClient:
    """Answers every query with no points and keeps the keyword arguments of each call."""

    last: "_RecordingClient | None" = None

    def __init__(self, *args, **kwargs) -> None:
        self.calls: list[dict] = []
        _RecordingClient.last = self

    def collection_exists(self, collection_name, **kwargs):
        return True

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(points=[])


def _recording_backend(monkeypatch) -> QdrantDenseBackend:
    monkeypatch.setattr(qdrant_dense, "QdrantClient", _RecordingClient)
    return QdrantDenseBackend("http://qdrant:6333", "consultqa_c", 8)


def test_unscoped_search_sends_no_filter(monkeypatch):
    backend = _recording_backend(monkeypatch)
    backend.search(np.ones(8, dtype=np.float32), k=3)
    (call,) = _RecordingClient.last.calls
    assert call["limit"] == 3
    assert call.get("query_filter") is None


def test_scoped_search_filters_on_the_point_ids_with_limit_k(monkeypatch):
    backend = _recording_backend(monkeypatch)
    backend.search(np.ones(8, dtype=np.float32), k=3, allowed={"d#0", "d#1"})
    (call,) = _RecordingClient.last.calls
    assert call["limit"] == 3
    (condition,) = call["query_filter"].must
    assert set(condition.has_id) == {_point_id("d#0"), _point_id("d#1")}


def test_scoped_search_asks_for_k_points_when_allowed_is_larger_than_k(monkeypatch):
    backend = _recording_backend(monkeypatch)
    backend.search(np.ones(8, dtype=np.float32), k=1, allowed={"d#0", "d#1", "d#2"})
    (call,) = _RecordingClient.last.calls
    assert call["limit"] == 1


def test_scoped_search_passes_five_thousand_allowed_ids_in_one_call(monkeypatch):
    backend = _recording_backend(monkeypatch)
    allowed = {f"c{n}" for n in range(5000)}
    backend.search(np.ones(8, dtype=np.float32), k=5, allowed=allowed)
    (call,) = _RecordingClient.last.calls
    assert call["limit"] == 5
    (condition,) = call["query_filter"].must
    assert set(condition.has_id) == {_point_id(cid) for cid in allowed}


def test_scoped_search_with_no_allowed_ids_asks_nothing(monkeypatch):
    backend = _recording_backend(monkeypatch)
    assert backend.search(np.ones(8, dtype=np.float32), k=3, allowed=set()) == []
    assert _RecordingClient.last.calls == []
