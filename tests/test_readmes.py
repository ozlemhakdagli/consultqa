"""The English and the Turkish README: they link to each other, share the Docker commands, and name
both page languages."""

from pathlib import Path

from consultqa.config import MODEL_PINS

ROOT = Path(__file__).resolve().parents[1]
COMMAND_PREFIXES = ("docker compose", "CONSULTQA_BACKEND=real docker compose", "MODELS=")
# The four models that the README copies from the cache (scripts/fetch_models.py FETCH_KEYS).
COPIED_KEYS = ("bge-m3", "reranker-v2-m3", "xlm-roberta-squad2", "paper-embedder")


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def _stripped_lines(name: str) -> list[str]:
    return [line.strip() for line in _text(name).splitlines()]


def test_the_readmes_link_to_each_other():
    assert "[Türkçe](README.tr.md)" in _text("README.md")
    assert "[English](README.md)" in _text("README.tr.md")


def test_the_turkish_readme_has_every_docker_command():
    english = [line for line in _stripped_lines("README.md") if line.startswith(COMMAND_PREFIXES)]
    turkish = set(_stripped_lines("README.tr.md"))
    assert len(english) >= 4
    assert [line for line in english if line not in turkish] == []


def test_the_readmes_name_both_page_languages():
    english = _text("README.md")
    turkish = _text("README.tr.md")
    assert "## Languages" in english and "Türkçe" in english and "English" in english
    assert "## Diller" in turkish and "My documents" in turkish and "Belgelerim" in turkish


def _copy_line(name: str) -> str:
    # The line of the Docker command that copies the cache into the volume.
    return next((line for line in _stripped_lines(name) if "cp -rL" in line), "")


def test_the_readme_copy_takes_the_pinned_revision_folders_only():
    for name in ("README.md", "README.tr.md"):
        models = next(line for line in _stripped_lines(name) if line.startswith("MODELS="))
        for key in COPIED_KEYS:
            repo_id, revision = MODEL_PINS[key]
            assert f"models--{repo_id.replace('/', '--')}/{revision}" in models, (name, key)
        copy = _copy_line(name)
        assert "/snapshots/" in copy, name
        assert "cp -r /src" not in _text(name), name


def test_the_readme_copy_skips_the_onnx_and_image_files():
    # The bge-m3 ONNX export (about 2.2 GB) and the model-card images are never loaded.
    for name in ("README.md", "README.tr.md"):
        copy = _copy_line(name)
        for skipped in ("onnx", "imgs", "*.jpg", "*.webp"):
            assert skipped in copy, (name, skipped)
