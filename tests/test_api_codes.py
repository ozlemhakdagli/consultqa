"""The API speaks in codes only: every error literal is a snake_case code and no sentence is sent.

The English flow itself is in test_api_english.py.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.routes import LLM_NOT_CONFIGURED
from consultqa.api.services import build_services
from consultqa.config import ABSTAIN_WORD, Settings

ROOT = Path(__file__).resolve().parents[1]
API_SOURCES = ["api/routes.py", "api/app.py", "api/services.py", "api/schemas.py",
               "ingest/parse.py", "ingest/pipeline.py"]  # fmt: skip
LITERALS = [
    r'detail="([^"]*)"',
    r'"detail": "([^"]*)"',
    r'_error\(\d+, "([^"]*)"\)',
    r'"failed", "([^"]*)"',
    r'ParseError\("([^"]*)"\)',
    r'_ERROR = "([^"]*)"',
    r'LLM_NOT_CONFIGURED = "([^"]*)"',
    r'reason="([^"]*)"',
]
CODE = re.compile(r"[a-z][a-z0-9_]*")
DOCUMENT = "# Shipping\n\nShipping takes five working days.\n"


class EmptyReader:
    def answer_span(self, question, context):
        return "", 0.0


class AbstainingLLM:
    def chat(self, messages):
        return ABSTAIN_WORD


@pytest.fixture
def services(tmp_path):
    svc = build_services(
        Settings(backend="stub", state_dir=tmp_path, max_upload_mb=1),
        jobs=JobRunner(synchronous=True),
    )
    svc.ready.set()
    return svc


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as c:
        yield c


def _library(client) -> str:
    cid = client.post("/api/collections", json={"name": "policy"}).json()["id"]
    client.post(
        f"/api/collections/{cid}/documents",
        files={"file": ("policy.md", DOCUMENT.encode("utf-8"), "text/markdown")},
    )
    return cid


def test_every_error_literal_in_the_api_is_a_code():
    found: set[str] = set()
    for source in API_SOURCES:
        text = (ROOT / "src" / "consultqa" / source).read_text(encoding="utf-8")
        for pattern in LITERALS:
            found.update(re.findall(pattern, text))
    assert {"not_ready", "busy", "llm_unavailable", "validation_error", "internal_error"} <= found
    assert all(CODE.fullmatch(literal) for literal in found), sorted(found)


def test_error_bodies_carry_only_codes(services, client):
    cid = _library(client)
    responses = [
        client.post(f"/api/collections/{cid}/ask", json={"question": "   ", "preset": "L2"}),
        client.post("/api/collections/missing/ask", json={"question": "Shipping?", "preset": "L2"}),
        client.post(f"/api/collections/{cid}/ask", json={"question": "Shipping?", "preset": "L9"}),
        client.get("/api/jobs/nope"),
        client.post(
            f"/api/collections/{cid}/documents",
            files={"file": ("x.exe", b"MZ", "application/octet-stream")},
        ),
        client.post("/api/collections", json={"name": ""}),
    ]
    services.ready.clear()
    responses.append(
        client.post(f"/api/collections/{cid}/ask", json={"question": "Shipping?", "preset": "L2"})
    )
    for response in responses:
        body = response.json()
        assert response.status_code >= 400
        assert list(body) == ["detail"]
        assert CODE.fullmatch(body["detail"])


def test_an_unanswerable_question_returns_null_and_no_sentence(services, client):
    services.reader = EmptyReader()
    cid = _library(client)
    response = client.post(
        f"/api/collections/{cid}/ask", json={"question": "Shipping?", "preset": "L2"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] is None and body["citations"] == []


def test_an_llm_abstention_returns_null(services, client):
    services.llm = AbstainingLLM()
    cid = _library(client)
    response = client.post(
        f"/api/collections/{cid}/ask", json={"question": "Shipping?", "preset": "L4+llm"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"] is None and body["citations"] == []


def test_the_evaluation_sentences_are_not_part_of_the_api():
    banned = ["NO_CONTEXT_ANSWER", "ABSTAIN_WORD", "Maalesef", "bulunamadı"]
    for path in (ROOT / "src" / "consultqa" / "api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in banned:
            assert word not in text, f"{word} found in {path.name}"


def test_capability_reasons_are_codes(services, client):
    services.llm = None
    body = client.get("/api/capabilities").json()
    reasons = {preset["reason"] for preset in body["presets"] if preset["reason"] is not None}
    assert reasons == {LLM_NOT_CONFIGURED}
    assert all(CODE.fullmatch(reason) for reason in reasons)
