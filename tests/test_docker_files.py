"""Static checks for the Docker, Compose and packaging files. They need no Docker daemon."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_never_copies_the_whole_context():
    assert "COPY . ." not in (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_images_are_pinned():
    text = (ROOT / "compose.yml").read_text(encoding="utf-8")
    assert ":latest" not in text
    assert "image: qdrant/qdrant:" in text


def test_base_image_is_pinned_to_an_exact_version():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    bases = re.findall(r"^FROM\s+(\S+)", dockerfile, flags=re.MULTILINE)
    assert bases, "the Dockerfile has no FROM line"
    assert all(re.fullmatch(r"python:3\.11\.\d+-slim-[a-z]+", base) for base in bases), bases


def test_dockerignore_is_an_allowlist():
    lines = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    assert rules[0] == "*"


def test_static_web_page_ships_with_the_package():
    """The API serves docrag/api/static, so a non-editable install must include it."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["tool"]["setuptools"]["package-data"]["docrag.api"] == ["static/*"]
