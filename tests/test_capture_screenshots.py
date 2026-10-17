"""Unit tests for the pure helpers of scripts/capture_screenshots.py (no browser, no server)."""

from __future__ import annotations

import importlib.util
import socket
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "capture_screenshots.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("capture_screenshots", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture = _load_script()


def test_server_env_drops_every_inherited_consultqa_variable(tmp_path: Path) -> None:
    base = {
        "CONSULTQA_LLM_BASE_URL": "http://x",
        "CONSULTQA_QDRANT_URL": "http://q",
        "CONSULTQA_STATE_DIR": "/somewhere",
        "PATH": "/usr/bin",
    }

    env = capture.server_env(tmp_path, base)

    assert env["CONSULTQA_STATE_DIR"] == str(tmp_path)
    assert "CONSULTQA_LLM_BASE_URL" not in env
    assert "CONSULTQA_QDRANT_URL" not in env
    assert env["PATH"] == "/usr/bin"


def test_server_env_selects_the_stub_backend_and_the_pdfium_parser(tmp_path: Path) -> None:
    env = capture.server_env(tmp_path, {"PATH": "/usr/bin"})

    assert env["CONSULTQA_BACKEND"] == "stub"
    assert env["CONSULTQA_PARSER"] == "pdfium"
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["PYTHONPATH"].endswith("src")


def test_server_env_refuses_a_state_folder_outside_the_temp_folder() -> None:
    # The owner's real state folder: the check must refuse it before anything touches it.
    real_state = Path.home() / ".consultqa"

    with pytest.raises(ValueError):
        capture.server_env(real_state, {"PATH": "/usr/bin"})


def test_free_port_returns_a_bindable_port() -> None:
    port = capture.free_port()

    assert 0 < port < 65536
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_the_shot_names_match_the_names_the_readme_tests_expect() -> None:
    from screenshot_names import SCREENSHOT_FILES

    assert capture.SHOT_NAMES == SCREENSHOT_FILES


def test_sample_pdfs_are_the_sample_documents() -> None:
    sample_dir = ROOT / "data" / "sample" / "pdf"

    assert capture.SAMPLE_PDFS == ("order_guide.pdf", "stock_report.pdf")
    for name in capture.SAMPLE_PDFS:
        assert (sample_dir / Path(name).with_suffix(".md")).is_file(), name


def test_temp_folder_check_uses_the_system_temp_folder(tmp_path: Path) -> None:
    # A folder under the system temp folder is accepted; the check is the one the plan names.
    assert Path(tempfile.gettempdir()).resolve() in tmp_path.resolve().parents
    env = capture.server_env(tmp_path, {})
    assert env["CONSULTQA_STATE_DIR"] == str(tmp_path)
