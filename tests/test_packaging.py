"""Licence and dependency checks: Apache-2.0, no PyMuPDF, Docling for PDFs, reportlab for tests."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
EXTRAS = PYPROJECT["project"]["optional-dependencies"]


def _pins(name: str) -> set[str]:
    lines = (ROOT / name).read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith(("#", "-r"))}


def test_the_project_is_licensed_under_apache_2_0():
    assert PYPROJECT["project"]["license"] == "Apache-2.0"
    assert not any("MIT" in c for c in PYPROJECT["project"].get("classifiers", []))
    # The official text starts with a blank line, then the title.
    lines = (ROOT / "LICENSE").read_text(encoding="utf-8").splitlines()
    assert next(line.strip() for line in lines if line.strip()) == "Apache License"
    assert "Apache-2.0" in (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")
    assert notice.splitlines()[:2] == ["consultqa", "Copyright 2026 ozlemhakdagli"]


def test_no_pymupdf_in_any_dependency_file():
    files = ["pyproject.toml", "requirements.txt", "requirements-dev.txt", "environment.yml"]
    for name in files:
        text = (ROOT / name).read_text(encoding="utf-8")
        assert not re.search(r"pymupdf|fitz", text, flags=re.IGNORECASE), name


def test_the_pdf_extra_is_docling():
    assert EXTRAS["pdf"] == ["docling==2.137.0"]
    assert "docling" not in EXTRAS


def test_requirements_list_exactly_the_runtime_extras():
    runtime = {dep for name in ("core", "ml", "pdf", "api") for dep in EXTRAS[name]}
    assert _pins("requirements.txt") == runtime


def test_reportlab_is_a_dev_only_dependency():
    assert "reportlab==5.0.1" in EXTRAS["dev"]
    for name in ("core", "ml", "pdf", "api", "e2e"):
        assert not any("reportlab" in dep for dep in EXTRAS[name]), name
    dev_file = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    assert "-r requirements.txt" in dev_file
    assert _pins("requirements-dev.txt") == set(EXTRAS["dev"])
    assert not any("reportlab" in pin for pin in _pins("requirements.txt"))
