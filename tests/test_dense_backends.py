import ipaddress
import os
import socket

import numpy as np
import pytest

from consultqa.retrieve.dense import NumpyDenseBackend

COLLECTION = "contract_test"

# Captured at import time, before the autouse ``block_network`` fixture patches the socket layer.
_REAL_CONNECT = socket.socket.connect
_REAL_CREATE_CONNECTION = socket.create_connection


def _is_loopback(address) -> bool:
    host = address[0] if isinstance(address, tuple) else address
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _allow_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the network block for loopback only, for the live Qdrant contract cases.

    Only called when the owner sets ``CONSULTQA_QDRANT_URL``. Any non-loopback connection
    still fails, so the rest of the guard in ``conftest.py`` stays in force.
    """

    def connect(self, address):
        if not _is_loopback(address):
            raise RuntimeError("only loopback connections are allowed in these tests")
        return _REAL_CONNECT(self, address)

    def create_connection(address, *args, **kwargs):
        if not _is_loopback(address):
            raise RuntimeError("only loopback connections are allowed in these tests")
        return _REAL_CREATE_CONNECTION(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)


def _numpy(_monkeypatch):
    return NumpyDenseBackend()


def _qdrant(monkeypatch):
    url = os.environ.get("CONSULTQA_QDRANT_URL")
    if not url:
        pytest.skip("CONSULTQA_QDRANT_URL is not set")
    from qdrant_client import QdrantClient

    from consultqa.store.qdrant_dense import QdrantDenseBackend

    _allow_loopback(monkeypatch)
    client = QdrantClient(url=url)
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.close()
    return QdrantDenseBackend(url, COLLECTION, dim=3)


@pytest.mark.parametrize("factory", [_numpy, _qdrant], ids=["numpy", "qdrant"])
def test_contract_best_match_then_delete(factory, monkeypatch):
    backend = factory(monkeypatch)
    backend.upsert(["a", "b", "c"], np.eye(3, dtype=np.float32))
    assert backend.search(np.array([0, 1, 0], dtype=np.float32), k=1)[0][0] == "b"
    backend.delete(["b"])
    assert all(cid != "b" for cid, _ in backend.search(np.array([0, 1, 0], dtype=np.float32), k=3))


@pytest.mark.parametrize("factory", [_numpy, _qdrant], ids=["numpy", "qdrant"])
def test_contract_upsert_is_idempotent(factory, monkeypatch):
    backend = factory(monkeypatch)
    backend.upsert(["a"], np.eye(3, dtype=np.float32)[:1])
    backend.upsert(["a"], np.eye(3, dtype=np.float32)[:1])
    assert [cid for cid, _ in backend.search(np.eye(3, dtype=np.float32)[0], k=5)].count("a") == 1


@pytest.mark.parametrize("factory", [_numpy, _qdrant], ids=["numpy", "qdrant"])
def test_contract_drop_can_be_repeated(factory, monkeypatch):
    backend = factory(monkeypatch)
    backend.upsert(["a", "b"], np.eye(3, dtype=np.float32)[:2])
    backend.drop()
    backend.drop()  # dropping a store that is already gone is not an error


def test_numpy_drop_forgets_every_vector():
    backend = NumpyDenseBackend()
    backend.upsert(["a", "b"], np.eye(3, dtype=np.float32)[:2])
    backend.drop()
    assert backend.search(np.array([0, 1, 0], dtype=np.float32), k=5) == []


def test_qdrant_drop_removes_the_collection_and_its_points(monkeypatch):
    url = os.environ.get("CONSULTQA_QDRANT_URL")
    backend = _qdrant(monkeypatch)
    backend.upsert(["a"], np.eye(3, dtype=np.float32)[:1])
    backend.drop()
    from qdrant_client import QdrantClient

    client = QdrantClient(url=url)
    try:
        assert client.collection_exists(COLLECTION) is False
    finally:
        client.close()
