"""English and mixed-language documents through the API with the stub backend."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from consultqa.api import services as services_module
from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.services import build_services
from consultqa.config import Settings

TERMS = (
    "# Shipping\n\nParcels come weekly.\n\n# Support\n\nCalls come daily.\n\n"
    "# Billing\n\nInvoices come monthly.\n"
)
TURKISH = (
    "# Kargo\n\nIşık çağrıları her gün cevaplanır.\n\n# Teslimat\n\nPaketler her hafta gelir.\n\n"
    "# Fatura\n\nFaturalar ayda bir gelir.\n"
)


@pytest.fixture
def services(tmp_path: Path):
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


def _library(client, name: str, *files: tuple[str, str]) -> str:
    cid = client.post("/api/collections", json={"name": name}).json()["id"]
    for filename, text in files:
        client.post(
            f"/api/collections/{cid}/documents",
            files={"file": (filename, text.encode("utf-8"), "text/markdown")},
        )
    return cid


def test_the_service_builds_a_language_aware_sparse_channel(services, client):
    cid = _library(client, "terms", ("terms.md", TERMS))
    sparse = services.index(cid)._sparse
    assert sparse._has_neutral
    top = sparse.search("how often do invoices come", k=1)[0]
    assert top.chunk.heading_path == ("Billing",)


def test_a_mixed_library_keeps_turkish_and_english_findable(services, client):
    cid = _library(client, "mixed", ("kargo.md", TURKISH), ("terms.md", TERMS))
    sparse = services.index(cid)._sparse
    assert sparse.search("IŞIK", k=1)[0].chunk.heading_path == ("Kargo",)
    assert sparse.search("how often do invoices come", k=1)[0].chunk.heading_path == ("Billing",)


ENGLISH = (
    "# Shipping\n\nShipping takes five working days.\n\n"
    "# Warranty\n\nThe warranty covers parts for two years.\n\n"
    "# Invoices\n\nInvoices are paid within 30 days of receipt.\n"
)
QUESTION = "How many years does the warranty cover?"


def test_an_english_document_can_be_uploaded_asked_and_cited(client):
    cid = _library(client, "policy", ("policy.md", ENGLISH))
    assert [d["filename"] for d in client.get(f"/api/collections/{cid}/documents").json()] == [
        "policy.md"
    ]
    body = client.post(
        f"/api/collections/{cid}/ask", json={"question": QUESTION, "preset": "L2"}
    ).json()
    assert body["answer"] == "The warranty covers parts for two years."
    assert [c["heading_path"] for c in body["citations"]] == [["Warranty"]]
    assert body["citations"][0]["text"] == "The warranty covers parts for two years."
    assert body["preset"] == "L2"


def test_extractive_presets_never_build_a_prompt(client, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("the prompt was built")

    monkeypatch.setattr(services_module, "build_messages", refuse)
    cid = _library(client, "policy", ("policy.md", ENGLISH))
    for preset in ("L2", "L3", "L4", "L5"):
        response = client.post(
            f"/api/collections/{cid}/ask", json={"question": QUESTION, "preset": preset}
        )
        assert response.status_code == 200, preset
