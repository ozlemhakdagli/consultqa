# tests/test_store_pages.py
import sqlite3

from consultqa.models import Chunk
from consultqa.store.sqlite_store import SqliteStore

# The schema before page numbers and originals were added.
_OLD_SCHEMA = """
CREATE TABLE collections (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    collection_id TEXT NOT NULL REFERENCES collections(id),
    content_sha256 TEXT NOT NULL,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(collection_id, content_sha256)
);
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    collection_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    heading_json TEXT NOT NULL,
    text TEXT NOT NULL
);
"""


def test_add_document_roundtrip(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")
    chunks = [
        Chunk("x#0", "x", 0, ("A",), "one", page=1),
        Chunk("x#1", "x", 1, ("A",), "two", page=3),
    ]
    store.add_document(col["id"], "x", "sha", "f.pdf", chunks, page_count=4, has_original=True)

    (doc,) = store.list_documents(col["id"])
    assert doc["page_count"] == 4
    assert doc["has_original"] is True
    assert [c.page for c in store.list_chunks(col["id"])] == [1, 3]


def test_old_database_gains_columns(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(_OLD_SCHEMA)
        conn.execute("INSERT INTO collections VALUES ('c', 'a', '2026-01-01')")
        conn.execute("INSERT INTO documents VALUES ('x', 'c', 'sha', 'f.txt', '2026-01-01')")
        conn.execute("INSERT INTO chunks VALUES ('x#0', 'x', 'c', 0, '[]', 'old text')")
    conn.close()

    store = SqliteStore(path)

    (doc,) = store.list_documents("c")
    assert doc["page_count"] is None
    assert doc["has_original"] is False
    (chunk,) = store.list_chunks("c")
    assert chunk.page is None
    assert chunk.text == "old text"


def test_get_document_other_collection_is_none(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")
    other = store.create_collection("b")
    store.add_document(col["id"], "x", "sha", "f.txt", [])

    doc = store.get_document(col["id"], "x")
    assert doc["id"] == "x"
    assert doc["has_original"] is False
    assert store.get_document(other["id"], "x") is None
