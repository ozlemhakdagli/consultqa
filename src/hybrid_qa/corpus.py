"""Corpus schema and JSONL persistence for update passages.

A passage is one update description with its document context. Passages can be
read from the private processed update-report JSON or from the synthetic JSONL corpus.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Passage:
    """A single update description together with its document context."""

    doc_id: str
    update_id: str
    version: str
    description: str
    tool: str | None = None
    section: str | None = None

    @property
    def passage_id(self) -> str:
        """Return the identifier formed from the document and update ids."""
        return f"{self.doc_id}:{self.update_id}"

    @property
    def text(self) -> str:
        """Return the passage text used for indexing and answer context."""
        return f"{self.description} (Versiyon: {self.version})"


def load_update_report_json(json_path: Path) -> list[Passage]:
    """Read the processed update-report JSON and return one Passage per update, in file order."""
    with Path(json_path).open(encoding="utf-8") as f:
        documents = json.load(f)

    passages: list[Passage] = []
    for document in documents:
        doc_id = document["id"]
        version = document["version_info"]["version"]
        for update in document["updates"]:
            passages.append(
                Passage(
                    doc_id=doc_id,
                    update_id=update["id"],
                    version=version,
                    description=update["description"],
                )
            )
    return passages


def load_jsonl_passages(path: Path) -> list[Passage]:
    """Read passages from a JSONL file, one JSON object per non-blank line."""
    passages: list[Passage] = []
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                passages.append(Passage(**json.loads(line)))
    return passages


def save_jsonl_passages(passages: Sequence[Passage], path: Path) -> None:
    """Write passages to a UTF-8 JSONL file, one JSON object per line."""
    with Path(path).open("w", encoding="utf-8") as f:
        for passage in passages:
            f.write(json.dumps(asdict(passage), ensure_ascii=False) + "\n")
