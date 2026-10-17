"""Ingestion pipeline: indexing, duplicate uploads, failures, deletion and the job runner."""

import hashlib
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
from consultqa.models import Chunk
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


def _legacy(store, cid, doc_id, text, filename, *, page_count=None, sha=None, dense=None):
    """A document uploaded before originals were kept: no original, and no pages unless given."""
    chunk = Chunk(chunk_id=f"{doc_id}-0", doc_id=doc_id, position=0, heading_path=(), text=text)
    digest = sha or hashlib.sha256(text.encode("utf-8")).hexdigest()
    store.add_document(
        cid, doc_id, digest, filename, [chunk], page_count=page_count, has_original=False
    )
    if dense is not None:
        dense.upsert([chunk.chunk_id], HashEncoder(dim=64).encode_passages([text]))


def test_a_legacy_document_with_the_same_content_is_replaced(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü performans", encoding="utf-8")
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü performans", "a.txt", dense=dense)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    [document] = store.list_documents(col)
    assert document["id"] == new and document["has_original"] is True
    assert [c.doc_id for c in store.list_chunks(col)] == [new]
    hits = [chunk_id for chunk_id, _ in dense.search(np.ones(64, dtype=np.float32), k=5)]
    assert hits and all(chunk_id.startswith(new) for chunk_id in hits)


def test_a_legacy_pdf_with_the_same_name_is_replaced_even_when_its_hash_differs(tmp_path):
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
    old, new = _doc_id("old"), _doc_id("new")
    # Docling merged the text across page breaks before, so the old hash differs.
    _legacy(store, col, old, "eski metin", "rapor.pdf", page_count=None)
    job = store.create_job(col, new)
    assert (
        _run(
            store,
            NumpyDenseBackend(),
            pdf,
            job,
            col,
            new,
            parser=PdfiumParser(max_pages=10),
            originals=originals,
        )
        is True
    )
    [document] = store.list_documents(col)
    assert document["id"] == new
    assert document["page_count"] == 3 and document["has_original"] is True
    assert originals.path(new) is not None


def test_a_document_with_an_original_is_kept_on_an_identical_upload(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Aynı metin", encoding="utf-8")
    first, second = _doc_id("first"), _doc_id("second")
    _run(store, dense, doc_file, store.create_job(col, first), col, first)
    job = store.create_job(col, second)
    assert _run(store, dense, doc_file, job, col, second) is False
    assert store.get_job(job)["state"] == "done"
    assert store.get_job(job)["document_id"] == first
    assert [d["id"] for d in store.list_documents(col)] == [first]


def test_a_document_with_an_original_is_not_replaced_by_a_same_named_upload(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Birinci metin", encoding="utf-8")
    first = _doc_id("first")
    _run(store, dense, doc_file, store.create_job(col, first), col, first)
    doc_file.write_text("İkinci metin", encoding="utf-8")
    second = _doc_id("second")
    assert _run(store, dense, doc_file, store.create_job(col, second), col, second) is True
    assert sorted(d["id"] for d in store.list_documents(col)) == sorted([first, second])


def test_a_legacy_document_of_another_folder_is_left_alone(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    mine = store.create_collection("mine")["id"]
    other_folder = store.create_collection("other")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    elsewhere, new = _doc_id("elsewhere"), _doc_id("new")
    _legacy(store, other_folder, elsewhere, "Stok modülü", "a.txt", dense=dense)
    assert _run(store, dense, doc_file, store.create_job(mine, new), mine, new) is True
    assert [d["id"] for d in store.list_documents(other_folder)] == [elsewhere]
    assert [d["id"] for d in store.list_documents(mine)] == [new]


class _Boom(HashEncoder):
    def encode_passages(self, texts):
        raise RuntimeError("boom")


@pytest.mark.parametrize("failure", ["encoder", "store"])
def test_a_failed_replacement_keeps_the_old_document(tmp_path, monkeypatch, failure):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "a.txt", sha="eski", dense=dense)
    if failure == "store":

        def boom(*args, **kwargs):
            raise RuntimeError("store failed")

        monkeypatch.setattr(store, "replace_document", boom)
    encoder = _Boom(dim=64) if failure == "encoder" else HashEncoder(dim=64)
    job = store.create_job(col, new)
    _run(store, dense, doc_file, job, col, new, encoder=encoder)
    assert store.get_job(job)["state"] == "failed"
    assert [d["id"] for d in store.list_documents(col)] == [old]
    assert [c.chunk_id for c in store.list_chunks(col)] == [f"{old}-0"]
    hits = [chunk_id for chunk_id, _ in dense.search(np.ones(64, dtype=np.float32), k=5)]
    assert hits == [f"{old}-0"]


def test_the_old_vectors_are_removed_only_after_the_new_document_is_stored(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    calls: list = []

    class Recording(NumpyDenseBackend):
        def upsert(self, ids, vectors):
            calls.append(("upsert", list(ids)))
            super().upsert(ids, vectors)

        def delete(self, ids):
            present = [d["id"] for d in store.list_documents(col)]
            calls.append(("delete", list(ids), present))
            super().delete(ids)

    dense = Recording()
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "a.txt", sha="eski", dense=dense)
    calls.clear()
    assert _run(store, dense, doc_file, store.create_job(col, new), col, new) is True
    assert [call[0] for call in calls] == ["upsert", "delete"]
    assert calls[1][1] == [f"{old}-0"]
    assert calls[1][2] == [new]


def test_a_failed_removal_of_old_vectors_does_not_fail_the_replacement(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")

    class Stuck(NumpyDenseBackend):
        def delete(self, ids):
            raise OSError("index locked")

    dense = Stuck()
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "a.txt", sha="eski")
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]


def test_a_legacy_document_with_the_same_content_under_another_name_is_replaced(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "eski.txt", dense=dense)
    assert _run(store, dense, doc_file, store.create_job(col, new), col, new) is True
    assert [d["id"] for d in store.list_documents(col)] == [new]


def test_an_unrelated_legacy_document_is_left_alone(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    unrelated, new = _doc_id("unrelated"), _doc_id("new")
    _legacy(store, col, unrelated, "Sipariş modülü", "diger.txt", sha="baska", dense=dense)
    assert _run(store, dense, doc_file, store.create_job(col, new), col, new) is True
    assert sorted(d["id"] for d in store.list_documents(col)) == sorted([unrelated, new])


def test_a_legacy_row_with_a_page_count_and_the_same_name_is_left_alone(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    paged, new = _doc_id("paged"), _doc_id("new")
    _legacy(store, col, paged, "Sipariş modülü", "a.txt", page_count=2, sha="baska", dense=dense)
    assert _run(store, dense, doc_file, store.create_job(col, new), col, new) is True
    assert sorted(d["id"] for d in store.list_documents(col)) == sorted([paged, new])


@pytest.mark.parametrize("older", ["same_name", "same_content"])
def test_several_legacy_matches_end_with_one_document(tmp_path, older):
    # The first legacy row has the upload's name and another hash; the second has the upload's
    # content. Replacing the first with a row whose hash the second still holds would collide.
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    by_name, by_content, new = _doc_id("name"), _doc_id("content"), _doc_id("new")
    rows = [
        (by_name, "Sipariş modülü", "a.txt", "baska"),
        (by_content, "Stok modülü", "diger.txt", None),
    ]
    if older == "same_content":
        rows.reverse()
    for doc, text, name, sha in rows:
        _legacy(store, col, doc, text, name, sha=sha, dense=dense)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]


def test_a_failed_mark_of_done_after_the_replace_keeps_the_new_document(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "a.txt", sha="eski", dense=dense)
    real_set_job = store.set_job

    def fail_when_done(job_id, state, error=None):
        if state == "done":
            raise RuntimeError("store failed")
        real_set_job(job_id, state, error)

    monkeypatch.setattr(store, "set_job", fail_when_done)
    job = store.create_job(col, new)
    _run(store, dense, doc_file, job, col, new)
    # The replace committed first, so the new document stays; only the job's own state is lost.
    [document] = store.list_documents(col)
    assert document["id"] == new and document["has_original"] is True
    assert [c.doc_id for c in store.list_chunks(col)] == [new]
    assert store.get_job(job)["state"] == "failed"


def test_a_replacement_whose_old_document_vanished_is_added(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    old, new = _doc_id("old"), _doc_id("new")
    _legacy(store, col, old, "Stok modülü", "a.txt", sha="eski", dense=dense)

    def vanished(cid, old_doc_id, *args, **kwargs):
        # Someone deleted the old document between the listing and the replace.
        store.delete_document(cid, old_doc_id)
        raise LookupError(old_doc_id)

    monkeypatch.setattr(store, "replace_document", vanished)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]


def _vector_ids(dense):
    return sorted(chunk_id for chunk_id, _ in dense.search(np.ones(64, dtype=np.float32), k=10))


def _first_match_vanishes_once(store, dense, monkeypatch):
    """The first replace finds its document gone (a concurrent delete); later calls are real."""
    real_replace = store.replace_document
    vanished = []

    def replace_after_a_concurrent_delete(cid, old_doc_id, *args, **kwargs):
        if not vanished:
            vanished.append(old_doc_id)
            store.delete_document(cid, old_doc_id)
            dense.delete([f"{old_doc_id}-0"])
        return real_replace(cid, old_doc_id, *args, **kwargs)

    monkeypatch.setattr(store, "replace_document", replace_after_a_concurrent_delete)


def test_a_match_vanishing_mid_job_is_skipped_and_the_next_match_is_replaced(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    first, second, new = _doc_id("first"), _doc_id("second"), _doc_id("new")
    _legacy(store, col, first, "Sipariş modülü", "a.txt", sha="x1", dense=dense)
    _legacy(store, col, second, "Başka metin", "a.txt", sha="x2", dense=dense)
    _first_match_vanishes_once(store, dense, monkeypatch)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]
    assert all(vector_id.startswith(new) for vector_id in _vector_ids(dense))


def test_a_match_by_hash_vanishing_mid_job_does_not_fail_the_upload(tmp_path, monkeypatch):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    first, second, new = _doc_id("first"), _doc_id("second"), _doc_id("new")
    _legacy(store, col, first, "Sipariş modülü", "a.txt", sha="x1", dense=dense)
    _legacy(store, col, second, "Stok modülü", "diger.txt", dense=dense)
    _first_match_vanishes_once(store, dense, monkeypatch)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]
    assert all(vector_id.startswith(new) for vector_id in _vector_ids(dense))


def test_the_vectors_of_every_extra_match_are_dropped_after_a_committed_replace(tmp_path):
    store = SqliteStore(tmp_path / "s.sqlite3")
    col = store.create_collection("c")["id"]
    dense = NumpyDenseBackend()
    doc_file = tmp_path / "a.txt"
    doc_file.write_text("Stok modülü", encoding="utf-8")
    first, second, new = _doc_id("first"), _doc_id("second"), _doc_id("new")
    _legacy(store, col, first, "Sipariş modülü", "a.txt", sha="x1", dense=dense)
    _legacy(store, col, second, "Stok modülü", "diger.txt", dense=dense)
    job = store.create_job(col, new)
    assert _run(store, dense, doc_file, job, col, new) is True
    assert store.get_job(job)["state"] == "done"
    assert [d["id"] for d in store.list_documents(col)] == [new]
    assert all(vector_id.startswith(new) for vector_id in _vector_ids(dense))
