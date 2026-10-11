"""The Docling models that scripts/fetch_models.py caches, pinned and placed where the app looks."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_fetch_models():
    spec = importlib.util.spec_from_file_location(
        "fetch_models", ROOT / "scripts" / "fetch_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docling_models_are_pinned_to_full_commit_hashes():
    fetch = _load_fetch_models()
    assert fetch.DOCLING_REPOS, "no Docling repositories are listed"
    for repo_id, revision in fetch.DOCLING_REPOS:
        assert re.fullmatch(r"[0-9a-f]{40}", revision), repo_id


def test_docling_folders_use_the_name_docling_looks_for():
    # Docling reads artifacts_path / "<org>--<name>" for each repository it loads.
    fetch = _load_fetch_models()
    folders = {repo_id.replace("/", "--") for repo_id, _ in fetch.DOCLING_REPOS}
    assert folders == {"docling-project--docling-layout-heron", "docling-project--docling-models"}


def test_rapidocr_files_are_the_ones_the_installed_wheel_ships():
    # Docling's OCR reads these from artifacts_path / "RapidOcr" once artifacts_path is set. The
    # rapidocr wheel bundles the same files, so the fetch copies them from the installed package.
    import rapidocr

    fetch = _load_fetch_models()
    bundled = Path(rapidocr.__file__).resolve().parent / "models"
    assert fetch.RAPIDOCR_FILES
    for name in fetch.RAPIDOCR_FILES:
        assert (bundled / name).is_file(), name
