"""Repository privacy checks: private material must never be tracked or copied into images."""

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_PREFIXES = ("private/", "data/raw/")
PRIVATE_SUFFIXES = (".pdf",)


def test_no_private_path_is_tracked() -> None:
    """No private directory, raw data file or PDF is tracked by git."""
    if not (REPO_ROOT / ".git").exists():
        pytest.skip("not a git repository; cannot check tracked files")
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    result = subprocess.run(  # noqa: S603
        ["git", "ls-files"],  # noqa: S607
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = [line for line in result.stdout.splitlines() if line]
    offending = [
        path
        for path in tracked
        if path.startswith(PRIVATE_PREFIXES) or path.endswith(PRIVATE_SUFFIXES)
    ]
    assert offending == [], f"private paths are tracked: {offending}"


def test_dockerignore_is_an_allowlist() -> None:
    """The first rule of .dockerignore excludes everything; private paths are never re-allowed."""
    lines = (REPO_ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    rules = [line.strip() for line in lines if line.strip() and not line.strip().startswith("#")]

    assert rules, ".dockerignore has no rules"
    assert rules[0] == "*"
    allowed = [rule for rule in rules if rule.startswith("!")]
    assert not any("private" in rule for rule in allowed), "private must never be allowed"
