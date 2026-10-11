"""Ingestion pipeline: indexing, duplicate uploads, failures, deletion and the job runner."""

from pathlib import Path

import numpy as np
import pytest

from consultqa.api.jobs import JobRunner
from consultqa.ingest import pipeline
from consultqa.ingest.parse import PyMuPDFParser, TextParser
from consultqa.ingest.pipeline import delete_document, ingest_file
from consultqa.retrieve.dense import NumpyDenseBackend
from consultqa.store.sqlite_store import SqliteStore
from consultqa.stub import HashEncoder


def _count(text: str) -> int:
    return len(text.split())


def _run(store, dense, path: Path, job: str, col: str, doc: str, parser=None, encoder=None):
    ingest_file(
        store=store,
        parser=parser or TextParser(),
        encoder=encoder or HashEncoder(dim=64),
        dense=dense,
        job_id=job,
        collection_id=col,
        doc_id=doc,
        path=path,
        filename=path.name,
        max_tokens=50,
        count_tokens=_count,
    )


def test_happy_path_indexes_chunks_and_vectors(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text(
        "Sipariş modülü tablo filtreleme\n\nStok modülü performans", encoding="utf-8"
    )
    job = store.create_job(col, "doc1")
    _run(store, dense, doc_file, job, col, "doc1")
    assert store.get_job(job)["state"] == "done"
    assert len(store.list_chunks(col)) >= 1
    assert store.load_graph(col) is not None
    assert dense.search(HashEncoder(dim=64).encode_query("Stok"), k=5)


def test_identical_content_is_not_indexed_twice(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    _run(store, dense, doc_file, store.create_job(col, "d1"), col, "d1")
    job2 = store.create_job(col, "d2")
    _run(store, dense, doc_file, job2, col, "d2")
    assert store.get_job(job2)["state"] == "done"
    assert len(store.list_documents(col)) == 1


def test_corrupt_pdf_fails_with_code(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    job = store.create_job(col, "d1")
    _run(
        store,
        NumpyDenseBackend(),
        bad,
        job,
        col,
        "d1",
        parser=PyMuPDFParser(max_pages=10),
    )
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "parse_failed"
    assert store.list_documents(col) == []


def test_delete_removes_vectors_and_chunks(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    _run(store, dense, doc_file, store.create_job(col, "d1"), col, "d1")
    assert delete_document(store=store, dense=dense, collection_id=col, doc_id="d1") is True
    assert store.list_chunks(col) == []
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []
    assert delete_document(store=store, dense=dense, collection_id=col, doc_id="d1") is False


def test_embedding_failure_fails_the_job(tmp_path):
    class Boom(HashEncoder):
        def encode_passages(self, texts):
            raise RuntimeError("boom")

    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("metin", encoding="utf-8")
    job = store.create_job(col, "d1")
    _run(store, NumpyDenseBackend(), doc_file, job, col, "d1", encoder=Boom(dim=64))
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "internal_error"
    assert store.list_documents(col) == []


def test_graph_failure_rolls_back_document_and_vectors(tmp_path, monkeypatch):
    def boom(chunks):
        raise RuntimeError("graph failed")

    monkeypatch.setattr(pipeline, "build_graph", boom)
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    job = store.create_job(col, "d1")
    _run(store, dense, doc_file, job, col, "d1")
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "internal_error"
    assert store.list_documents(col) == []
    assert store.list_chunks(col) == []
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []


def test_job_runner_runs_inline_when_synchronous():
    calls: list[str] = []
    JobRunner(synchronous=True).submit(calls.append, "x").result()
    assert calls == ["x"]


def test_job_runner_runs_on_a_worker_thread():
    calls: list[str] = []
    JobRunner().submit(calls.append, "y").result(timeout=5)
    assert calls == ["y"]


def test_duplicate_job_reports_the_existing_document(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    _run(store, dense, doc_file, store.create_job(col, "first"), col, "first")
    job2 = store.create_job(col, "second")
    _run(store, dense, doc_file, job2, col, "second")
    assert store.get_job(job2)["state"] == "done"
    assert store.get_job(job2)["document_id"] == "first"


# The stored document name is the name the user uploaded, never the staging name.
def test_stored_filename_is_the_uploaded_name(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    staged = tmp_path / "3f9a2c1e.txt"
    staged.write_text("Kılavuz metni", encoding="utf-8")
    job = store.create_job(col, "d1")
    ingest_file(
        store=store,
        parser=TextParser(),
        encoder=HashEncoder(dim=64),
        dense=NumpyDenseBackend(),
        job_id=job,
        collection_id=col,
        doc_id="d1",
        path=staged,
        filename="Kılavuz Ocak.txt",
        max_tokens=50,
        count_tokens=_count,
    )
    assert store.get_job(job)["state"] == "done"
    assert [d["filename"] for d in store.list_documents(col)] == ["Kılavuz Ocak.txt"]


# A document with no chunks (an empty text file, or a PDF without text) is a failed job.
@pytest.mark.parametrize("content", ["", "  \n\n \t"])
def test_document_without_text_fails_as_no_text(tmp_path, content):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "bos.txt"
    doc_file.write_text(content, encoding="utf-8")
    job = store.create_job(col, "d1")
    _run(store, dense, doc_file, job, col, "d1")
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "no_text"
    assert store.list_documents(col) == []
    assert store.list_chunks(col) == []
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []
