"""Load update passages from the processed update-report JSON file.

Kept as a thin shim over ``hybrid_qa.corpus`` for existing imports.
"""

from pathlib import Path

from hybrid_qa.config import PROCESSED_JSON_PATH
from hybrid_qa.corpus import Passage, load_update_report_json

__all__ = ["Passage", "load_passages"]


def load_passages(json_path: Path = PROCESSED_JSON_PATH) -> list[Passage]:
    """Read the processed JSON and return one Passage per update, in file order."""
    return load_update_report_json(json_path)
