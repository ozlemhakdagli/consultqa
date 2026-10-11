"""The English and the Turkish README: they link to each other, share the Docker commands, and name
both page languages."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMAND_PREFIXES = ("docker compose", "CONSULTQA_BACKEND=real docker compose", "MODELS=")


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
