"""The vendored pdf.js build: files, version, notice and how the app serves it."""

from pathlib import Path

from fastapi.testclient import TestClient

from consultqa.api.app import create_app
from consultqa.api.services import build_services
from consultqa.config import Settings

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "frontend" / "vendor" / "pdfjs"
VERSION = "4.10.38"
FILES = ("pdf.min.mjs", "pdf.worker.min.mjs", "pdf_viewer.css", "LICENSE", "VERSION")


def test_vendored_files_exist_and_are_pinned():
    for name in FILES:
        assert (VENDOR / name).is_file(), name
    assert (VENDOR / "VERSION").read_text(encoding="utf-8").strip() == VERSION


def test_notice_names_the_library_version_and_license():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert "pdf.js" in notice
    assert VERSION in notice
    assert "Apache License, Version 2.0" in notice


def test_vendor_folder_is_outside_the_own_code_scan():
    text = (ROOT / "tests" / "test_frontend_static.py").read_text(encoding="utf-8")
    assert '"vendor" not in' in text


def test_app_serves_the_module_as_javascript_with_page_headers(tmp_path):
    settings = Settings(backend="stub", state_dir=tmp_path, frontend_dir=ROOT / "frontend")
    with TestClient(create_app(build_services(settings))) as client:
        response = client.get("/vendor/pdfjs/pdf.min.mjs")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
