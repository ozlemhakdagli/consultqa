"""GET /api/capabilities: what the page needs to know before it offers anything."""

import pytest
from fastapi.testclient import TestClient

from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.services import build_services
from consultqa.config import PRESETS, Settings


@pytest.fixture
def services(tmp_path):
    settings = Settings(backend="stub", state_dir=tmp_path, max_upload_mb=20)
    svc = build_services(settings, jobs=JobRunner(synchronous=True))
    svc.ready.set()
    return svc


@pytest.fixture
def client(services):
    return TestClient(create_app(services))


def test_capabilities_describe_every_preset(client):
    body = client.get("/api/capabilities").json()
    assert body["ready"] is True and body["llm_configured"] is True
    assert body["max_upload_mb"] == 20
    assert body["extensions"] == [".md", ".pdf", ".txt"]
    assert body["default_preset"] == "L2"
    assert [p["name"] for p in body["presets"]] == list(PRESETS)
    assert all(p["available"] and p["reason"] is None for p in body["presets"])
    assert {p["name"] for p in body["presets"] if p["uses_llm"]} == {"L4+llm", "L5+llm"}


def test_llm_presets_are_unavailable_without_an_llm(services, client):
    services.llm = None
    body = client.get("/api/capabilities").json()
    assert body["llm_configured"] is False
    by_name = {p["name"]: p for p in body["presets"]}
    for name in ("L4+llm", "L5+llm"):
        assert by_name[name] == {
            "name": name,
            "available": False,
            "reason": "llm_not_configured",
            "uses_llm": True,
        }
    assert by_name["L2"]["available"] is True


def test_paper_preset_is_listed_only_when_enabled(services, client):
    assert "paper" not in [p["name"] for p in client.get("/api/capabilities").json()["presets"]]
    services.paper_enabled = True
    paper = client.get("/api/capabilities").json()["presets"][-1]
    assert paper == {"name": "paper", "available": True, "reason": None, "uses_llm": False}


def test_capabilities_answer_while_the_models_load(services, client):
    services.ready.clear()
    response = client.get("/api/capabilities")
    assert response.status_code == 200
    assert response.json()["ready"] is False


def test_presets_endpoint_is_unchanged(client):
    assert client.get("/api/presets").json() == list(PRESETS)


def test_ask_request_default_is_the_service_default():
    from consultqa.api.schemas import AskRequest
    from consultqa.api.services import DEFAULT_PRESET

    assert AskRequest(question="x").preset == DEFAULT_PRESET
