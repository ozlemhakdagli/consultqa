"""Row counts of the SQLite store, for tests that check a collection's rows are all removed."""

import sqlite3
from pathlib import Path

ROW_COUNTS = {
    "collections": "SELECT COUNT(*) FROM collections WHERE id = ?",
    "documents": "SELECT COUNT(*) FROM documents WHERE collection_id = ?",
    "chunks": "SELECT COUNT(*) FROM chunks WHERE collection_id = ?",
    "graphs": "SELECT COUNT(*) FROM graphs WHERE collection_id = ?",
    "jobs": "SELECT COUNT(*) FROM jobs WHERE collection_id = ?",
}


def rows_left(path: Path, cid: str) -> dict[str, int]:
    """How many rows of each table still belong to the collection ``cid``."""
    conn = sqlite3.connect(path)
    try:
        return {name: conn.execute(sql, (cid,)).fetchone()[0] for name, sql in ROW_COUNTS.items()}
    finally:
        conn.close()
