"""SQLite store for collections, documents, chunks, evidence graphs and ingestion jobs.

Every call opens its own connection with foreign keys enforced and closes it afterwards.
Writes run in one transaction, so a failed write leaves no partial rows behind.
"""

import json
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from docrag.models import Chunk

_SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id),
    content_sha256 TEXT NOT NULL,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(collection_id, content_sha256)
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    collection_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    heading_json TEXT NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS graphs (
    collection_id TEXT PRIMARY KEY REFERENCES collections(id),
    data BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    state TEXT NOT NULL,
    error TEXT,
    updated_at TEXT NOT NULL
);
"""


class CollectionExists(Exception):
    """A collection with this name already exists."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


class SqliteStore:
    """Metadata, chunk text, graph blobs and job states, kept in one SQLite file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Yield a fresh connection; commit on success, roll back on error, always close."""
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            with conn:
                yield conn
        finally:
            conn.close()

    def create_collection(self, name: str) -> dict:
        row = {"id": uuid.uuid4().hex, "name": name, "created_at": _now()}
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO collections (id, name, created_at) VALUES (?, ?, ?)",
                    (row["id"], row["name"], row["created_at"]),
                )
        except sqlite3.IntegrityError as exc:
            raise CollectionExists(name) from exc
        return row

    def get_collection(self, cid: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, name, created_at FROM collections WHERE id = ?", (cid,)
            ).fetchone()
        return dict(row) if row else None

    def list_collections(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, created_at FROM collections ORDER BY created_at, name"
            ).fetchall()
        return [dict(row) for row in rows]

    def find_document_by_hash(self, cid: str, sha: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE collection_id = ? AND content_sha256 = ?",
                (cid, sha),
            ).fetchone()
        return row["id"] if row else None

    def add_document(
        self, cid: str, doc_id: str, sha: str, filename: str, chunks: Sequence[Chunk]
    ) -> None:
        """Insert a document and its chunks in one transaction."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO documents (id, collection_id, content_sha256, filename, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (doc_id, cid, sha, filename, _now()),
            )
            conn.executemany(
                "INSERT INTO chunks"
                " (chunk_id, document_id, collection_id, position, heading_json, text)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        c.chunk_id,
                        doc_id,
                        cid,
                        c.position,
                        json.dumps(list(c.heading_path), ensure_ascii=False),
                        c.text,
                    )
                    for c in chunks
                ],
            )

    def list_documents(self, cid: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, collection_id, content_sha256, filename, created_at"
                " FROM documents WHERE collection_id = ? ORDER BY created_at, id",
                (cid,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_document(self, cid: str, doc_id: str) -> bool:
        """Delete a document; its chunks go with it (ON DELETE CASCADE)."""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE id = ? AND collection_id = ?", (doc_id, cid)
            )
            deleted = cur.rowcount > 0
        return deleted

    def list_chunks(self, cid: str) -> list[Chunk]:
        """All chunks of a collection, by document creation order, then position."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT c.chunk_id, c.document_id, c.position, c.heading_json, c.text"
                " FROM chunks c JOIN documents d ON d.id = c.document_id"
                " WHERE c.collection_id = ?"
                " ORDER BY d.created_at, d.id, c.position",
                (cid,),
            ).fetchall()
        return [_chunk_from_row(row) for row in rows]

    def document_chunk_ids(self, cid: str, doc_id: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT chunk_id FROM chunks"
                " WHERE collection_id = ? AND document_id = ? ORDER BY position",
                (cid, doc_id),
            ).fetchall()
        return [row["chunk_id"] for row in rows]

    def save_graph(self, cid: str, data: bytes) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO graphs (collection_id, data) VALUES (?, ?)"
                " ON CONFLICT(collection_id) DO UPDATE SET data = excluded.data",
                (cid, data),
            )

    def load_graph(self, cid: str) -> bytes | None:
        with self._connect() as conn:
            row = conn.execute("SELECT data FROM graphs WHERE collection_id = ?", (cid,)).fetchone()
        return bytes(row["data"]) if row else None

    def create_job(self, cid: str, doc_id: str) -> str:
        job_id = uuid.uuid4().hex
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (id, collection_id, document_id, state, error, updated_at)"
                " VALUES (?, ?, ?, 'queued', NULL, ?)",
                (job_id, cid, doc_id, _now()),
            )
        return job_id

    def set_job(self, job_id: str, state: str, error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET state = ?, error = ?, updated_at = ? WHERE id = ?",
                (state, error, _now(), job_id),
            )

    def fail_unfinished_jobs(self, error: str) -> int:
        """Mark every job that is not finished (queued, parsing, embedding or graph) as failed.

        Called at startup: a job still running when the process stopped will never finish.
        Returns the number of jobs marked.
        """
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE jobs SET state = 'failed', error = ?, updated_at = ?"
                " WHERE state IN ('queued', 'parsing', 'embedding', 'graph')",
                (error, _now()),
            )
            return cur.rowcount

    def set_job_document(self, job_id: str, document_id: str) -> None:
        """Point a job at a document. A duplicate upload points at the document it matched."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET document_id = ?, updated_at = ? WHERE id = ?",
                (document_id, _now(), job_id),
            )

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, collection_id, document_id, state, error, updated_at"
                " FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return dict(row) if row else None


def _chunk_from_row(row: sqlite3.Row) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        doc_id=row["document_id"],
        position=row["position"],
        heading_path=tuple(json.loads(row["heading_json"])),
        text=row["text"],
    )
