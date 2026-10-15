"""Ingestion pipeline: indexing, duplicate uploads, failures, deletion and the job runner."""

import uuid
from pathlib import Path

import numpy as np
import pytest
from pdf_fixtures import write_pdf

from consultqa.api.jobs import JobRunner
from consultqa.graph.build import EvidenceGraph
from consultqa.ingest.parse import DocumentParser, TextParser
from consultqa.ingest.pdfium import PdfiumParser
from consultqa.ingest.pipeline import delete_document, ingest_file
from consultqa.retrieve.dense import NumpyDenseBackend
from consultqa.store.originals import OriginalFiles
from consultqa.store.sqlite_store import SqliteStore
from consultqa.stub import HashEncoder


def _count(text: str) -> int:
    return len(text.split())


def _doc_id(name: str) -> str:
    # Document ids name files in the originals folder, so they must be 32 lowercase hex characters.
    return uuid.uuid5(uuid.NAMESPACE_OID, name).hex


def _run(
    store,
    dense,
    path: Path,
    job: str,
    col: str,
    doc: str,
    parser=None,
    encoder=None,
    originals=None,
):
    return ingest_file(
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
        originals=originals or OriginalFiles(path.parent / "files"),
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
    _run(store, dense, doc_file, job, col, _doc_id("doc1"))
    assert store.get_job(job)["state"] == "done"
    assert len(store.list_chunks(col)) >= 1
    # O11: ingestion stores no graph; the graph is built when a graph preset first asks for it.
    assert store.load_graph(col) is None
    assert dense.search(HashEncoder(dim=64).encode_query("Stok"), k=5)


def test_identical_content_is_not_indexed_twice(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    _run(store, dense, doc_file, store.create_job(col, _doc_id("d1")), col, _doc_id("d1"))
    job2 = store.create_job(col, _doc_id("d2"))
    _run(store, dense, doc_file, job2, col, _doc_id("d2"))
    assert store.get_job(job2)["state"] == "done"
    assert len(store.list_documents(col)) == 1


def test_corrupt_pdf_fails_with_code(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"nope")
    job = store.create_job(col, _doc_id("d1"))
    _run(
        store,
        NumpyDenseBackend(),
        bad,
        job,
        col,
        _doc_id("d1"),
        parser=DocumentParser(max_pages=10),
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
    originals = OriginalFiles(tmp_path / "files")
    _run(
        store,
        dense,
        doc_file,
        store.create_job(col, "d1"),
        col,
        _doc_id("d1"),
        originals=originals,
    )
    assert (
        delete_document(
            store=store, dense=dense, collection_id=col, doc_id=_doc_id("d1"), originals=originals
        )
        is True
    )
    assert store.list_chunks(col) == []
    assert store.load_graph(col) is None
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []
    assert (
        delete_document(
            store=store, dense=dense, collection_id=col, doc_id=_doc_id("d1"), originals=originals
        )
        is False
    )


def test_embedding_failure_fails_the_job(tmp_path):
    class Boom(HashEncoder):
        def encode_passages(self, texts):
            raise RuntimeError("boom")

    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("metin", encoding="utf-8")
    job = store.create_job(col, _doc_id("d1"))
    _run(store, NumpyDenseBackend(), doc_file, job, col, _doc_id("d1"), encoder=Boom(dim=64))
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "internal_error"
    assert store.list_documents(col) == []


def test_failure_after_the_document_is_written_rolls_it_back(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    real_set_job = store.set_job

    def fail_when_done(job_id, state, error=None):
        if state == "done":
            raise RuntimeError("store failed")
        real_set_job(job_id, state, error)

    monkeypatch.setattr(store, "set_job", fail_when_done)
    job = store.create_job(col, _doc_id("d1"))
    # Vectors and the document were written before the failure, so the job reports that it wrote.
    assert _run(store, dense, doc_file, job, col, _doc_id("d1")) is True
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "internal_error"
    assert store.list_documents(col) == []
    assert store.list_chunks(col) == []
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []


def test_ingestion_never_serialises_a_graph(tmp_path, monkeypatch):
    def boom(self):
        raise RuntimeError("graph serialised during ingestion")

    monkeypatch.setattr(EvidenceGraph, "to_bytes", boom)
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    job = store.create_job(col, _doc_id("d1"))
    _run(store, NumpyDenseBackend(), doc_file, job, col, _doc_id("d1"))
    assert store.get_job(job)["state"] == "done"


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
    _run(store, dense, doc_file, store.create_job(col, _doc_id("first")), col, _doc_id("first"))
    job2 = store.create_job(col, _doc_id("second"))
    _run(store, dense, doc_file, job2, col, _doc_id("second"))
    assert store.get_job(job2)["state"] == "done"
    assert store.get_job(job2)["document_id"] == _doc_id("first")


# The stored document name is the name the user uploaded, never the staging name.
def test_stored_filename_is_the_uploaded_name(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    staged = tmp_path / "3f9a2c1e.txt"
    staged.write_text("Kılavuz metni", encoding="utf-8")
    job = store.create_job(col, _doc_id("d1"))
    ingest_file(
        store=store,
        parser=TextParser(),
        encoder=HashEncoder(dim=64),
        dense=NumpyDenseBackend(),
        job_id=job,
        collection_id=col,
        doc_id=_doc_id("d1"),
        path=staged,
        filename="Kılavuz Ocak.txt",
        max_tokens=50,
        count_tokens=_count,
        originals=OriginalFiles(tmp_path / "files"),
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
    job = store.create_job(col, _doc_id("d1"))
    _run(store, dense, doc_file, job, col, _doc_id("d1"))
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "no_text"
    assert store.list_documents(col) == []
    assert store.list_chunks(col) == []
    assert dense.search(np.ones(64, dtype=np.float32), k=5) == []


# O11: only a job that wrote chunks or vectors reports it, so only then is the state dropped.
def test_a_job_that_writes_reports_true(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    assert (
        _run(
            store,
            NumpyDenseBackend(),
            doc_file,
            store.create_job(col, _doc_id("d1")),
            col,
            _doc_id("d1"),
        )
        is True
    )


def test_a_duplicate_job_writes_nothing_and_reports_false(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    _run(store, dense, doc_file, store.create_job(col, _doc_id("first")), col, _doc_id("first"))
    assert (
        _run(
            store, dense, doc_file, store.create_job(col, _doc_id("second")), col, _doc_id("second")
        )
        is False
    )


@pytest.mark.parametrize("content", ["", "  \n\n \t"])
def test_a_document_without_text_writes_nothing_and_reports_false(tmp_path, content):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "bos.txt"
    doc_file.write_text(content, encoding="utf-8")
    assert (
        _run(
            store,
            NumpyDenseBackend(),
            doc_file,
            store.create_job(col, _doc_id("d1")),
            col,
            _doc_id("d1"),
        )
        is False
    )


def test_an_embedding_failure_writes_nothing_and_reports_false(tmp_path):
    class Boom(HashEncoder):
        def encode_passages(self, texts):
            raise RuntimeError("boom")

    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("metin", encoding="utf-8")
    result = _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        store.create_job(col, _doc_id("d1")),
        col,
        _doc_id("d1"),
        encoder=Boom(dim=64),
    )
    assert result is False


def _stored_files(folder: Path) -> list[str]:
    return sorted(f.name for f in folder.iterdir()) if folder.exists() else []


def test_pdf_upload_stores_pages_and_keeps_the_original(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    originals = OriginalFiles(tmp_path / "files")
    pdf = write_pdf(
        tmp_path / "rapor.pdf",
        [
            [("h1", "Giriş"), ("p", "Stok modülü performans raporu")],
            [],
            [("p", "Sipariş modülü tablo filtreleme")],
        ],
    )
    job = store.create_job(col, "d1")
    doc = _doc_id("pdf")
    _run(
        store,
        NumpyDenseBackend(),
        pdf,
        job,
        col,
        doc,
        parser=PdfiumParser(max_pages=10),
        originals=originals,
    )
    assert store.get_job(job)["state"] == "done"
    assert [c.page for c in store.list_chunks(col)] == [1, 3]
    [document] = store.list_documents(col)
    assert document["page_count"] == 3
    assert document["has_original"] is True
    assert originals.path(doc) is not None


def test_text_upload_has_no_pages_and_keeps_the_original(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    originals = OriginalFiles(tmp_path / "files")
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    doc = _doc_id("text")
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        store.create_job(col, "d1"),
        col,
        doc,
        originals=originals,
    )
    assert [c.page for c in store.list_chunks(col)] == [None]
    [document] = store.list_documents(col)
    assert document["page_count"] is None
    assert document["has_original"] is True
    assert originals.path(doc) is not None


def test_the_same_file_twice_keeps_one_original_and_one_document(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    folder = tmp_path / "files"
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    dense = NumpyDenseBackend()
    _run(
        store,
        dense,
        doc_file,
        store.create_job(col, "first"),
        col,
        _doc_id("first"),
        originals=OriginalFiles(folder),
    )
    _run(
        store,
        dense,
        doc_file,
        store.create_job(col, "second"),
        col,
        _doc_id("second"),
        originals=OriginalFiles(folder),
    )
    assert len(store.list_documents(col)) == 1
    assert len(_stored_files(folder)) == 1


@pytest.mark.parametrize("content", ["", "  \n\n \t"])
def test_a_document_without_text_keeps_no_original(tmp_path, content):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    folder = tmp_path / "files"
    doc_file = tmp_path / "bos.txt"
    doc_file.write_text(content, encoding="utf-8")
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        store.create_job(col, "d1"),
        col,
        _doc_id("d1"),
        originals=OriginalFiles(folder),
    )
    assert _stored_files(folder) == []


def test_an_embedding_failure_keeps_no_original(tmp_path):
    class Boom(HashEncoder):
        def encode_passages(self, texts):
            raise RuntimeError("boom")

    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    folder = tmp_path / "files"
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("metin", encoding="utf-8")
    doc = _doc_id("d1")
    job = store.create_job(col, "d1")
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        job,
        col,
        doc,
        encoder=Boom(dim=64),
        originals=OriginalFiles(folder),
    )
    assert store.get_job(job)["state"] == "failed"
    assert store.list_documents(col) == []
    assert _stored_files(folder) == []


def test_a_failure_while_saving_the_document_removes_the_original(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    folder = tmp_path / "files"
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    doc = _doc_id("d1")

    def boom(*args, **kwargs):
        raise RuntimeError("store failed")

    monkeypatch.setattr(store, "add_document", boom)
    job = store.create_job(col, "d1")
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        job,
        col,
        doc,
        originals=OriginalFiles(folder),
    )
    assert store.get_job(job)["state"] == "failed"
    assert _stored_files(folder) == []


def test_delete_removes_the_original(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    originals = OriginalFiles(tmp_path / "files")
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    doc = _doc_id("d1")
    _run(store, dense, doc_file, store.create_job(col, "d1"), col, doc, originals=originals)
    assert originals.path(doc) is not None
    assert delete_document(
        store=store, dense=dense, collection_id=col, doc_id=doc, originals=originals
    )
    assert originals.path(doc) is None


class _Pages:
    """A parser whose pages are the ones the test gives."""

    name = "pages"
    suffixes = frozenset({".txt"})

    def __init__(self, pages):
        self._pages = list(pages)

    def warm_up(self):
        pass

    def parse(self, path):
        return "\n\n".join(self._pages)

    def parse_pages(self, path):
        return list(self._pages)


def test_blank_pages_do_not_change_the_content_hash(tmp_path):
    # A PDF exported page by page has blank pages in the middle; the whole-document export of the
    # same text has none, and must still count as the same content.
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("metin", encoding="utf-8")
    first = _doc_id("first")
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        store.create_job(col, first),
        col,
        first,
        parser=_Pages(["zeytin kayısı", "", "nohut"]),
    )
    second = _doc_id("second")
    job = store.create_job(col, second)
    _run(
        store,
        NumpyDenseBackend(),
        doc_file,
        job,
        col,
        second,
        parser=_Pages(["zeytin kayısı\n\nnohut"]),
    )
    assert store.get_job(job)["state"] == "done"
    assert store.get_job(job)["document_id"] == first


class _LockedOriginals(OriginalFiles):
    """Originals that cannot be removed, as on a locked file."""

    def delete(self, doc_id):
        raise OSError("locked")


def test_a_failed_original_removal_still_fails_the_job_and_drops_the_vectors(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    dense = NumpyDenseBackend()

    def boom(*args, **kwargs):
        raise RuntimeError("store failed")

    monkeypatch.setattr(store, "add_document", boom)
    job = store.create_job(col, "d1")
    _run(
        store,
        dense,
        doc_file,
        job,
        col,
        _doc_id("d1"),
        originals=_LockedOriginals(tmp_path / "files"),
    )
    assert store.get_job(job)["state"] == "failed"
    assert store.get_job(job)["error"] == "internal_error"
    assert dense.search(np.ones(64, dtype=np.float32), 5) == []
