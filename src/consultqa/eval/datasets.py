"""Evaluation corpus loading and file fingerprints."""

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from consultqa.models import Chunk

_CHUNK_SIZE = 1 << 20


def file_sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of the file at ``path``."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK_SIZE), b""):
            digest.update(block)
    return digest.hexdigest()


def load_corpus_jsonl(path: Path) -> list[Chunk]:
    """Read update passages from a UTF-8 JSONL file and return them as chunks, in file order.

    Each line holds ``doc_id``, ``update_id``, ``version``, ``description``, ``tool`` and
    ``section``. ``tool`` and ``section`` may be null. ``position`` counts passages within
    each document from 0. ``heading_path`` keeps the non-empty ``tool`` and ``section``.
    """
    chunks: list[Chunk] = []
    next_position: dict[str, int] = defaultdict(int)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            doc_id = row["doc_id"]
            position = next_position[doc_id]
            next_position[doc_id] += 1
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}:{row['update_id']}",
                    doc_id=doc_id,
                    position=position,
                    heading_path=tuple(x for x in (row.get("tool"), row.get("section")) if x),
                    text=f"{row['description']} (Versiyon: {row['version']})",
                )
            )
    return chunks
