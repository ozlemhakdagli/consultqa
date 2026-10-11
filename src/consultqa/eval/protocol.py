"""Evaluation protocol: the declared file hashes that every run must verify against."""

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from consultqa.eval.datasets import file_sha256


def load_protocol(path: Path) -> dict[str, Any]:
    """Read the protocol JSON file and return its contents as a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def verify_protocol(protocol: Mapping[str, Any], file_paths: Mapping[str, Path]) -> list[str]:
    """Return one message per protocol file that is missing or whose SHA-256 differs.

    ``protocol["files"]`` maps each name to ``{"sha256": ...}``, and ``file_paths`` maps the
    same names to local paths. A declared file with no path, or a path that is not a file,
    is reported as missing rather than passing silently. An empty list means every declared
    file matches.
    """
    problems: list[str] = []
    for name, entry in sorted(protocol["files"].items()):
        path = file_paths.get(name)
        if path is None or not path.is_file():
            problems.append(f"{name}: file missing")
        elif file_sha256(path) != entry["sha256"]:
            problems.append(f"{name}: sha256 differs from protocol")
    return problems
