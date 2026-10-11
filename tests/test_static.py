from fastapi.testclient import TestClient

from docrag.api.app import create_app
from docrag.api.jobs import JobRunner
from docrag.api.services import build_services
from docrag.config import Settings


def _client(tmp_path):
    svc = build_services(
        Settings(backend="stub", state_dir=tmp_path), jobs=JobRunner(synchronous=True)
    )
    svc.ready.set()
    return TestClient(create_app(svc))


def test_index_page_has_the_upload_form(tmp_path):
    response = _client(tmp_path).get("/")
    assert response.status_code == 200 and 'id="upload-form"' in response.text


def test_script_never_inserts_server_html(tmp_path):
    script = _client(tmp_path).get("/app.js").text
    assert "textContent" in script and "innerHTML" not in script
