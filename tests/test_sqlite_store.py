import sqlite3

import pytest

from consultqa.models import Chunk
from consultqa.store.sqlite_store import CollectionExists, SqliteStore


def _store(tmp_path):
    return SqliteStore(tmp_path / "s.sqlite3")


def test_duplicate_collection_name_is_rejected(tmp_path):
    store = _store(tmp_path)
    store.create_collection("a")
    with pytest.raises(CollectionExists):
        store.create_collection("a")


def test_failed_add_leaves_no_rows(tmp_path):
    store = _store(tmp_path)
    col = store.create_collection("a")
    dup = [Chunk("x#0", "x", 0, (), "t"), Chunk("x#0", "x", 1, (), "u")]  # same chunk_id twice
    with pytest.raises(sqlite3.IntegrityError):
        store.add_document(col["id"], "x", "sha", "f.txt", dup)
    assert store.find_document_by_hash(col["id"], "sha") is None
    assert store.list_chunks(col["id"]) == []


# [R4] Deleting a document removes its chunks; the same content can be added again afterwards.
def test_delete_cascades_and_hash_is_reusable(tmp_path):
    store = _store(tmp_path)
    col = store.create_collection("a")
    store.add_document(col["id"], "x", "sha", "f.txt", [Chunk("x#0", "x", 0, (), "t")])
    assert store.find_document_by_hash(col["id"], "sha") == "x"
    assert store.delete_document(col["id"], "x") is True
    assert store.list_chunks(col["id"]) == []
    store.add_document(col["id"], "y", "sha", "f.txt", [Chunk("y#0", "y", 0, (), "t")])


def test_set_job_document_points_the_job_at_another_document(tmp_path):
    store = _store(tmp_path)
    col = store.create_collection("a")["id"]
    job = store.create_job(col, "new-doc")
    store.set_job_document(job, "existing-doc")
    assert store.get_job(job)["document_id"] == "existing-doc"
