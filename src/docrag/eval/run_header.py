"""Run header: the state that produced an evaluation table.

The header records the git HEAD and whether the work tree is dirty, the corpus and evaluation
file hashes, the Python version, the versions of the ML libraries and whether CUDA is available,
and the pipeline configurations of the run. Anything that cannot be read is ``None``.
"""

import importlib.metadata as metadata
import platform
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LIBRARY_DISTRIBUTIONS = ("torch", "transformers", "sentence-transformers")


def _git(*args: str) -> str | None:
    """Return the stdout of a git command in the project, or None when git cannot answer."""
    git = shutil.which("git")
    if git is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603 - fixed arguments, no shell
            [git, *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout


def _git_state() -> dict[str, Any]:
    """Return the HEAD commit and whether the work tree has uncommitted changes."""
    head = _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    return {
        "head": head.strip() if head is not None else None,
        "dirty": bool(status.strip()) if status is not None else None,
    }


def _library_version(distribution: str) -> str | None:
    """Return the installed version of a distribution, or None when it is not installed."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def _cuda_available(torch_version: str | None) -> bool | None:
    """Return whether torch sees a CUDA device, or None when torch is not installed."""
    if torch_version is None:
        return None
    try:
        import torch
    except (ImportError, OSError):
        return None
    return bool(torch.cuda.is_available())


def build_run_header(
    *,
    corpus_sha: str,
    eval_sha: str,
    configs: Mapping[str, object],
) -> dict[str, Any]:
    """Return the run header as a JSON-serialisable dict.

    ``configs`` maps a system name to its pipeline configuration. Dataclasses are written as
    dicts of their fields; other values are written as given.
    """
    libraries = {name: _library_version(name) for name in LIBRARY_DISTRIBUTIONS}
    return {
        "corpus_sha": corpus_sha,
        "eval_sha": eval_sha,
        "git": _git_state(),
        "python": platform.python_version(),
        "libraries": libraries,
        "cuda_available": _cuda_available(libraries["torch"]),
        "configs": {
            name: asdict(config) if is_dataclass(config) else config
            for name, config in configs.items()
        },
    }
