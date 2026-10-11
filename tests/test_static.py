from pathlib import Path

from fastapi.testclient import TestClient

from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.services import build_services
from consultqa.config import Settings


def _client_with_frontend(tmp_path, files):
    frontend = tmp_path / "frontend"
    for name, text in files.items():
        path = frontend / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    settings = Settings(backend="stub", state_dir=tmp_path / "state", frontend_dir=frontend)
    svc = build_services(settings, jobs=JobRunner(synchronous=True))
    svc.ready.set()
    return TestClient(create_app(svc))


PAGE_FILES = {"index.html": "<!doctype html><title>x</title>", "js/a.js": "export const a = 1;"}


def test_page_files_carry_security_and_revalidation_headers(tmp_path):
    client = _client_with_frontend(tmp_path, PAGE_FILES)
    for path in ("/", "/js/a.js"):
        headers = client.get(path).headers
        policy = headers["content-security-policy"]
        assert "script-src 'self'" in policy and "frame-ancestors 'none'" in policy
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["cache-control"] == "no-cache"
    assert "javascript" in client.get("/js/a.js").headers["content-type"]


def test_api_responses_have_no_page_headers_and_still_win_over_the_page(tmp_path):
    client = _client_with_frontend(tmp_path, PAGE_FILES)
    response = client.get("/api/health")
    assert response.json() == {"status": "ok"}
    assert "content-security-policy" not in response.headers


def test_missing_frontend_dir_leaves_the_api_running(tmp_path):
    settings = Settings(backend="stub", state_dir=tmp_path, frontend_dir=tmp_path / "absent")
    svc = build_services(settings, jobs=JobRunner(synchronous=True))
    client = TestClient(create_app(svc))
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 404


def test_default_frontend_dir_is_the_repository_folder():
    from consultqa.api.app import DEFAULT_FRONTEND_DIR

    assert DEFAULT_FRONTEND_DIR == Path(__file__).resolve().parents[1] / "frontend"
    assert (DEFAULT_FRONTEND_DIR / "index.html").is_file()
