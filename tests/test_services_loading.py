"""Model loading on the real backend: the loader thread loads the encoder, then the reranker, then
the reader. ``ready`` is set only after all three are in memory, and no text is encoded to learn
the embedding dimension."""

import logging
import threading

import numpy as np
from fastapi.testclient import TestClient

from consultqa.api import services as services_module
from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.services import build_services, load_in_background
from consultqa.config import Settings

DIM = 8


class Steps:
    """Records each model load together with whether ``ready`` was set at that moment."""

    def __init__(self) -> None:
        self.events: list[tuple[str, bool]] = []
        self.ready: threading.Event | None = None
        self.scorer = None
        self.reader = None

    def note(self, name: str) -> None:
        self.events.append((name, self.ready is not None and self.ready.is_set()))


class FakeEncoder:
    """Stands in for the sentence encoder. Encoding a text to learn the dimension is a failure."""

    def __init__(self, steps: Steps) -> None:
        self._steps = steps

    def get_sentence_embedding_dimension(self) -> int:
        self._steps.note("encoder")
        return DIM

    def encode_query(self, text: str) -> np.ndarray:
        self._steps.note("probe")
        return np.zeros(DIM + 3, dtype=np.float32)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class FakeReader:
    def answer_span(self, question: str, context: str) -> tuple[str, float]:
        return "", 0.0


def _patch_models(monkeypatch, steps: Steps, *, reader_gate: threading.Event | None = None) -> None:
    """Replace the three model loaders with fakes that record when they run."""

    def load_reranker():
        steps.note("reranker")
        steps.scorer = lambda query, texts: [0.0] * len(texts)
        return steps.scorer

    def load_reader():
        steps.note("reader")
        if reader_gate is not None:
            reader_gate.wait(timeout=5)
        steps.reader = FakeReader()
        return steps.reader

    monkeypatch.setattr(services_module, "SentenceEncoder", lambda spec: FakeEncoder(steps))
    monkeypatch.setattr(services_module, "load_cross_encoder", load_reranker)
    monkeypatch.setattr(services_module, "ExtractiveReader", load_reader)


def _real_services(tmp_path, steps: Steps):
    svc = build_services(
        Settings(backend="real", qdrant_url="http://qdrant.test", state_dir=tmp_path),
        jobs=JobRunner(synchronous=True),
    )
    steps.ready = svc.ready
    svc.warm_parser = None  # keeps Docling out of these tests
    return svc


def test_models_load_in_turn_and_ready_is_set_after_the_last_one(monkeypatch, tmp_path):
    steps = Steps()
    _patch_models(monkeypatch, steps)
    svc = _real_services(tmp_path, steps)
    # Building the services loads nothing, so the port can open before the models are in memory.
    assert steps.events == []
    load_in_background(svc).join(timeout=5)
    assert steps.events == [("encoder", False), ("reranker", False), ("reader", False)]
    assert svc.ready.is_set()
    assert svc.scorer is steps.scorer
    assert svc.reader is steps.reader


def test_dimension_comes_from_the_encoder_and_no_probe_is_encoded(monkeypatch, tmp_path):
    steps = Steps()
    _patch_models(monkeypatch, steps)
    svc = _real_services(tmp_path, steps)
    load_in_background(svc).join(timeout=5)
    dims: list[int] = []
    svc.make_dense = lambda cid, dim: dims.append(dim)
    svc.dense("c1")
    svc.dense("c2")
    assert dims == [DIM, DIM]
    assert all(name != "probe" for name, _ in steps.events)


def test_api_refuses_questions_and_ready_until_the_reader_is_loaded(monkeypatch, tmp_path):
    steps = Steps()
    gate = threading.Event()
    _patch_models(monkeypatch, steps, reader_gate=gate)
    svc = _real_services(tmp_path, steps)
    try:
        with TestClient(create_app(svc)) as client:
            cid = client.post("/api/collections", json={"name": "c"}).json()["id"]
            # The loader is held at the reader; the encoder and the reranker are already in.
            assert client.get("/api/health").status_code == 200
            assert client.get("/api/ready").status_code == 503
            refused = client.post(f"/api/collections/{cid}/ask", json={"question": "Soru?"})
            assert refused.status_code == 503
            assert refused.json() == {"detail": "not_ready"}
            gate.set()
            assert svc.ready.wait(timeout=5)
            assert client.get("/api/ready").status_code == 200
    finally:
        gate.set()


class RecordingWarmer:
    """Stands in for the parser's warm-up. Records whether ``ready`` was set when it ran."""

    def __init__(self, ready: threading.Event, *, fail: bool = False) -> None:
        self.ready = ready
        self.fail = fail
        self.calls: list[bool] = []

    def __call__(self) -> None:
        self.calls.append(self.ready.is_set())
        if self.fail:
            raise RuntimeError("docling models missing")


# O5: the parser is warmed once, after ready, and a failed warm-up does not stop the service.
def test_docling_is_warmed_once_and_only_after_ready(monkeypatch, tmp_path):
    steps = Steps()
    _patch_models(monkeypatch, steps)
    svc = _real_services(tmp_path, steps)
    warmer = RecordingWarmer(svc.ready)
    svc.warm_parser = warmer
    load_in_background(svc).join(timeout=5)
    assert warmer.calls == [True]


def test_a_failed_warm_up_leaves_the_service_ready(monkeypatch, tmp_path, caplog):
    steps = Steps()
    _patch_models(monkeypatch, steps)
    svc = _real_services(tmp_path, steps)
    svc.warm_parser = RecordingWarmer(svc.ready, fail=True)
    with caplog.at_level(logging.ERROR):
        load_in_background(svc).join(timeout=5)
    assert svc.ready.is_set()
    assert "warm-up failed" in caplog.text


def test_warm_up_does_not_run_when_a_model_fails_to_load(monkeypatch, tmp_path):
    steps = Steps()
    _patch_models(monkeypatch, steps)

    def broken_reranker():
        raise RuntimeError("reranker missing")

    monkeypatch.setattr(services_module, "load_cross_encoder", broken_reranker)
    svc = _real_services(tmp_path, steps)
    warmer = RecordingWarmer(svc.ready)
    svc.warm_parser = warmer
    load_in_background(svc).join(timeout=5)
    assert warmer.calls == []
    assert not svc.ready.is_set()


def test_only_the_real_backend_has_a_parser_warm_up(tmp_path):
    stub = build_services(Settings(backend="stub", state_dir=tmp_path / "stub"), jobs=JobRunner())
    assert stub.warm_parser is None
    real = build_services(
        Settings(backend="real", qdrant_url="http://qdrant.test", state_dir=tmp_path / "real"),
        jobs=JobRunner(),
    )
    assert real.warm_parser is not None
