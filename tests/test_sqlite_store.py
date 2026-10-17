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
    assert store.list_chunks(col["id"]) == []


# [R4] Deleting a document removes its chunks; the same content can be added again afterwards.
def test_delete_cascades_and_hash_is_reusable(tmp_path):
    store = _store(tmp_path)
    col = store.create_collection("a")
    store.add_document(col["id"], "x", "sha", "f.txt", [Chunk("x#0", "x", 0, (), "t")])
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


# The lookup indexes: the per-document and per-collection queries search them, not every row.
LOOKUP_INDEXES = {
    "ix_chunks_collection_document_position": ["collection_id", "document_id", "position"],
    "ix_chunks_document": ["document_id"],
    "ix_jobs_collection": ["collection_id"],
}


def _query_plan(path, sql, params=()):
    conn = sqlite3.connect(path)
    try:
        return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params)]
    finally:
        conn.close()


def _lookup_indexes(path):
    conn = sqlite3.connect(path)
    try:
        found = {}
        for table in ("chunks", "jobs"):
            for row in conn.execute(f"PRAGMA index_list({table})").fetchall():
                if row[1].startswith("ix_"):
                    found[row[1]] = [col[2] for col in conn.execute(f"PRAGMA index_info({row[1]})")]
        return found
    finally:
        conn.close()


def _assert_searched_by_index(plan, table):
    assert not any(step.startswith(f"SCAN {table}") for step in plan), plan
    assert any(step.startswith(f"SEARCH {table} USING") for step in plan), plan


def test_a_new_database_has_the_lookup_indexes(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path)
    assert _lookup_indexes(path) == LOOKUP_INDEXES


def test_an_existing_database_gets_the_missing_indexes_when_it_opens(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path)
    conn = sqlite3.connect(path)
    for name in LOOKUP_INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()
    conn.close()
    SqliteStore(path)
    assert _lookup_indexes(path) == LOOKUP_INDEXES


def test_document_chunk_ids_searches_the_index_in_position_order(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path)
    plan = _query_plan(
        path,
        "SELECT chunk_id FROM chunks WHERE collection_id = ? AND document_id = ? ORDER BY position",
        ("c", "d"),
    )
    _assert_searched_by_index(plan, "chunks")
    assert not any("TEMP B-TREE" in step for step in plan), plan


def test_the_delete_cascade_searches_chunks_by_document(tmp_path):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path)
    # The lookup SQLite runs for ON DELETE CASCADE from documents to chunks.document_id.
    plan = _query_plan(path, "DELETE FROM chunks WHERE document_id = ?", ("d",))
    _assert_searched_by_index(plan, "chunks")


@pytest.mark.parametrize(
    "sql",
    [
        # SqliteStore.has_active_jobs
        "SELECT 1 FROM jobs WHERE collection_id = ?"
        " AND state NOT IN ('done', 'failed', 'interrupted') LIMIT 1",
        # SqliteStore.delete_collection
        "DELETE FROM jobs WHERE collection_id = ?",
    ],
)
def test_jobs_of_a_collection_are_searched_by_index(tmp_path, sql):
    path = tmp_path / "s.sqlite3"
    SqliteStore(path)
    _assert_searched_by_index(_query_plan(path, sql, ("c",)), "jobs")
