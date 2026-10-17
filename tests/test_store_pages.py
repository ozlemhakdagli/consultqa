# tests/test_store_pages.py
import sqlite3

import pytest

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


def test_replace_document_swaps_the_old_row_and_its_chunks(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")["id"]
    store.add_document(col, "old", "sha", "f.txt", [Chunk("old#0", "old", 0, (), "eski")])
    store.replace_document(
        col, "old", "new", "sha", "f.txt", [Chunk("new#0", "new", 0, (), "yeni")]
    )
    assert [d["id"] for d in store.list_documents(col)] == ["new"]
    assert [c.chunk_id for c in store.list_chunks(col)] == ["new#0"]


def test_a_failed_replace_keeps_the_old_document_and_its_chunks(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")["id"]
    store.add_document(col, "old", "sha", "f.txt", [Chunk("old#0", "old", 0, (), "eski")])
    # Two chunks with one id: the insert fails after the old row was deleted in the transaction.
    broken = [Chunk("new#0", "new", 0, (), "bir"), Chunk("new#0", "new", 1, (), "iki")]
    with pytest.raises(sqlite3.IntegrityError):
        store.replace_document(col, "old", "new", "sha", "f.txt", broken)
    assert [d["id"] for d in store.list_documents(col)] == ["old"]
    assert [c.chunk_id for c in store.list_chunks(col)] == ["old#0"]


def test_replacing_a_document_of_another_folder_raises_and_changes_nothing(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    mine = store.create_collection("a")["id"]
    other = store.create_collection("b")["id"]
    store.add_document(other, "old", "sha", "f.txt", [Chunk("old#0", "old", 0, (), "eski")])
    with pytest.raises(LookupError):
        store.replace_document(mine, "old", "new", "sha", "f.txt", [])
    assert [d["id"] for d in store.list_documents(other)] == ["old"]
    assert store.list_documents(mine) == []


def test_replace_document_also_deletes_the_extra_documents_in_the_same_transaction(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")["id"]
    store.add_document(col, "old", "sha-a", "f.txt", [Chunk("old#0", "old", 0, (), "a")])
    store.add_document(col, "extra", "sha", "f.txt", [Chunk("extra#0", "extra", 0, (), "b")])
    # The new document has the extra document's hash, so it can only be stored once that row
    # is gone; both deletions and the insert are one transaction.
    store.replace_document(
        col,
        "old",
        "new",
        "sha",
        "f.txt",
        [Chunk("new#0", "new", 0, (), "c")],
        also_delete=["extra"],
    )
    assert [d["id"] for d in store.list_documents(col)] == ["new"]
    assert [c.chunk_id for c in store.list_chunks(col)] == ["new#0"]


def test_document_chunks_are_in_position_order_and_scoped(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("a")
    other = store.create_collection("b")
    chunks = [
        Chunk("x#2", "x", 2, (), "uc", page=2),
        Chunk("x#0", "x", 0, (), "ua", page=1),
        Chunk("x#1", "x", 1, (), "ub", page=1),
    ]
    store.add_document(col["id"], "x", "sha", "f.pdf", chunks, page_count=2, has_original=True)
    store.add_document(col["id"], "y", "sha2", "g.txt", [Chunk("y#0", "y", 0, (), "yy")])

    got = store.document_chunks(col["id"], "x")
    assert [c.text for c in got] == ["ua", "ub", "uc"]
    assert [c.page for c in got] == [1, 1, 2]
    assert store.document_chunks(col["id"], "missing") == []
    assert store.document_chunks(other["id"], "x") == []
