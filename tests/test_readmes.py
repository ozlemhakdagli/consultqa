"""The README: the Docker commands it documents and the cache copy it describes."""

from pathlib import Path

from consultqa.config import MODEL_PINS

ROOT = Path(__file__).resolve().parents[1]
COMMAND_PREFIXES = ("docker compose", "CONSULTQA_BACKEND=real docker compose", "MODELS=")
# The four models that the README copies from the cache (scripts/fetch_models.py FETCH_KEYS).
COPIED_KEYS = ("bge-m3", "reranker-v2-m3", "xlm-roberta-squad2", "paper-embedder")


def _text() -> str:
    return (ROOT / "README.md").read_text(encoding="utf-8")


def _stripped_lines() -> list[str]:
    return [line.strip() for line in _text().splitlines()]


def _copy_line() -> str:
    # The line of the Docker command that copies the cache into the volume.
    return next((line for line in _stripped_lines() if "cp -rL" in line), "")


def test_the_readme_documents_the_docker_commands():
    commands = [line for line in _stripped_lines() if line.startswith(COMMAND_PREFIXES)]
    assert len(commands) >= 4


def test_the_readme_describes_the_page_languages():
    assert "## Languages" in _text()


def test_the_readme_copy_takes_the_pinned_revision_folders_only():
    models = next(line for line in _stripped_lines() if line.startswith("MODELS="))
    for key in COPIED_KEYS:
        repo_id, revision = MODEL_PINS[key]
        assert f"models--{repo_id.replace('/', '--')}/{revision}" in models, key
    assert "/snapshots/" in _copy_line()
    assert "cp -r /src" not in _text()


def test_the_readme_copy_skips_the_onnx_and_image_files():
    # The bge-m3 ONNX export (about 2.2 GB) and the model-card images are never loaded.
    copy = _copy_line()
    for skipped in ("onnx", "imgs", "*.jpg", "*.webp"):
        assert skipped in copy, skipped
