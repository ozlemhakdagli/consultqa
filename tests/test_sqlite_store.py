import sqlite3

import pytest
from store_rows import rows_left

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


# [R1] Deleting a collection removes its documents, chunks, graph and jobs, and no other's.
def test_delete_collection_removes_its_rows_and_no_others(tmp_path):
    path = tmp_path / "s.sqlite3"
    store = SqliteStore(path)
    doomed = store.create_collection("a")["id"]
    kept = store.create_collection("b")["id"]
    store.add_document(doomed, "d1", "sha1", "f.txt", [Chunk("d1#0", "d1", 0, (), "t")])
    store.add_document(kept, "d2", "sha2", "g.txt", [Chunk("d2#0", "d2", 0, (), "u")])
    store.save_graph(doomed, b"doomed-graph")
    store.save_graph(kept, b"kept-graph")
    store.set_job(store.create_job(doomed, "d1"), "done")
    kept_job = store.create_job(kept, "d2")
    store.delete_collection(doomed)
    assert rows_left(path, doomed) == {
        "collections": 0,
        "documents": 0,
        "chunks": 0,
        "graphs": 0,
        "jobs": 0,
    }
    assert store.get_collection(kept) is not None
    assert [doc["id"] for doc in store.list_documents(kept)] == ["d2"]
    assert store.list_chunks(kept)[0].chunk_id == "d2#0"
    assert store.load_graph(kept) == b"kept-graph"
    assert store.get_job(kept_job)["state"] == "queued"


@pytest.mark.parametrize("state", ["queued", "parsing", "embedding", "graph"])
def test_a_job_that_has_not_finished_makes_the_collection_active(tmp_path, state):
    store = _store(tmp_path)
    cid = store.create_collection("a")["id"]
    job = store.create_job(cid, "d1")
    store.set_job(job, state)
    assert store.has_active_jobs(cid) is True


@pytest.mark.parametrize("state", ["done", "failed", "interrupted"])
def test_finished_jobs_do_not_make_the_collection_active(tmp_path, state):
    store = _store(tmp_path)
    cid = store.create_collection("a")["id"]
    job = store.create_job(cid, "d1")
    store.set_job(job, state)
    assert store.has_active_jobs(cid) is False


def test_a_collection_without_jobs_is_not_active(tmp_path):
    store = _store(tmp_path)
    cid = store.create_collection("a")["id"]
    assert store.has_active_jobs(cid) is False


def test_collections_are_listed_with_their_document_count(tmp_path):
    store = _store(tmp_path)
    empty = store.create_collection("a")["id"]
    full = store.create_collection("b")["id"]
    store.add_document(full, "d1", "s1", "f.txt", [Chunk("d1#0", "d1", 0, (), "t")])
    store.add_document(full, "d2", "s2", "g.txt", [Chunk("d2#0", "d2", 0, (), "u")])
    counts = {row["id"]: row["document_count"] for row in store.list_collections()}
    assert counts == {empty: 0, full: 2}
