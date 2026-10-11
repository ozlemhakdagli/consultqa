"""Shared pytest fixtures for the test suite."""

import socket

import pytest


@pytest.fixture(autouse=True)
def offline_hub(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Hugging Face offline mode so tests never download model weights."""
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")


@pytest.fixture(autouse=True)
def block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make outgoing network connections fail so unit tests cannot reach the network.

    No current unit test needs the network. If one ever does, it should be
    moved behind the ``model`` marker (excluded by default, per the spec) rather
    than weakening this block.
    """

    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network access is blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", _blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
