"""The README: the Docker commands it documents and the cache copy it describes."""

import re
from pathlib import Path

import pytest
from screenshot_names import SCREENSHOT_FILES

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


def _prose_lines() -> list[str]:
    """README lines outside fenced code blocks."""
    lines: list[str] = []
    in_fence = False
    for line in _text().splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            lines.append(line)
    return lines


def test_the_readme_has_the_sections_in_order():
    headings = [line for line in _prose_lines() if line.startswith(("# ", "## "))]
    assert headings == [
        "# consultqa",
        "## What is in the repository",
        "## Running",
        "## Using the page",
        "## Languages",
        "## Application architecture and development",
        "## The method and reproducible results",
        "## Licence",
    ]
    subheadings = [line for line in _prose_lines() if line.startswith("### ")]
    method = [
        "### Status",
        "### From the published method to consultqa",
        "### Results",
        "### What did not work",
        "### Limitations",
        "### Reproduce",
        "### The published method",
    ]
    positions = [subheadings.index(heading) for heading in method]
    assert positions == sorted(positions), "method subsections are out of order"
    assert all(heading in subheadings for heading in method)


def test_every_readme_image_is_a_listed_screenshot_that_exists():
    text = _text()
    paths = set(re.findall(r'src="(assets/images/[^"]+)"', text))
    paths |= set(re.findall(r"\]\((assets/images/[^)]+)\)", text))
    expected = {f"assets/images/{name}" for name in SCREENSHOT_FILES}
    assert paths == expected
    missing = [path for path in sorted(paths) if not (ROOT / path).is_file()]
    assert missing == [], f"README images are missing: {missing}"


def test_the_readme_has_the_badges():
    text = _text()
    assert text.count("img.shields.io") >= 5
    head = "\n".join(text.splitlines()[:12])
    for word in ("License", "tests", "Python", "FastAPI", "Docker"):
        assert word in head, word


def test_details_blocks_are_balanced_and_summaries_are_followed_by_a_blank_line():
    lines = _text().splitlines()
    opened = sum(line.count("<details>") for line in lines)
    closed = sum(line.count("</details>") for line in lines)
    assert opened == closed
    assert opened >= 3
    for index, line in enumerate(lines):
        if "</summary>" in line:
            assert index + 1 < len(lines) and lines[index + 1].strip() == "", (
                f"line {index + 1}: no blank line after </summary>"
            )


def test_the_readme_does_not_link_into_docs():
    text = _text()
    assert "docs/" not in text
    assert "](docs" not in text


def test_the_readme_has_no_forbidden_term():
    terms_file = ROOT / "private" / "forbidden_terms.txt"
    if not terms_file.exists():
        pytest.skip("private/forbidden_terms.txt is not present (as in CI)")
    terms = [
        line.strip().lower()
        for line in terms_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    text = _text().lower()
    # Count only: a failure must never print the term itself.
    hits = sum(1 for term in terms if term in text)
    assert hits == 0, "README contains a forbidden term"
