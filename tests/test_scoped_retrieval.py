"""Document-scoped retrieval, related chunks and cleanup of originals on folder delete."""

import uuid
from pathlib import Path

import numpy as np
import pytest

from consultqa.api.jobs import JobRunner
from consultqa.api.services import CollectionIndex, Services, build_services, related_chunks
from consultqa.config import PRESETS, Settings
from consultqa.ingest.pipeline import ingest_file
from consultqa.models import Chunk, Hit
from consultqa.retrieve.dense import DenseChannel, NumpyDenseBackend

L2 = PRESETS["L2"]


class _FixedEncoder:
    """Returns one fixed vector for the query; passages are never encoded in these tests."""

    def __init__(self, query_vector: np.ndarray) -> None:
        self._query = query_vector

    def encode_query(self, text: str) -> np.ndarray:
        return self._query


def _chunk(chunk_id: str, doc_id: str = "d", page: int | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc_id,
        position=0,
        heading_path=(),
        text=f"text {chunk_id}",
        page=page,
    )


def _hit(chunk: Chunk) -> Hit:
    return Hit(chunk=chunk, score=1.0, score_type="cosine", channel="dense")


def _service(tmp_path: Path) -> Services:
    return build_services(
        Settings(backend="stub", state_dir=tmp_path / "state"), jobs=JobRunner(synchronous=True)
    )


def _ingest(svc: Services, cid: str, tmp_path: Path, text: str, doc_id: str) -> None:
    path = tmp_path / f"{doc_id}.txt"
    path.write_text(text, encoding="utf-8")
    job = svc.store.create_job(cid, doc_id)
    written = ingest_file(
        store=svc.store,
        parser=svc.parser,
        encoder=svc.encoder,
        dense=svc.dense(cid),
        job_id=job,
        collection_id=cid,
        doc_id=doc_id,
        path=path,
        filename=f"{doc_id}.txt",
        max_tokens=svc.settings.chunk_max_tokens,
        count_tokens=svc.count_tokens,
        originals=svc.originals,
    )
    assert written is True


@pytest.fixture
def folder(tmp_path):
    """Two documents. The target has one section; the other has many chunks on the same terms."""
    svc = _service(tmp_path)
    cid = svc.store.create_collection("c")["id"]
    target = uuid.uuid4().hex
    other = uuid.uuid4().hex
    _ingest(svc, cid, tmp_path, "# Kurulum\n\nZephyr kurulum adımları burada.\n", target)
    body = "".join(f"# Bölüm {n}\n\nSipariş stok modülü tablo {n}.\n\n" for n in range(60))
    _ingest(svc, cid, tmp_path, body, other)
    return svc, cid, target, other


def test_dense_restricted_answers_from_its_own_chunks_even_when_folder_top_k_misses_them():
    backend = NumpyDenseBackend()
    other_ids = [f"o{n}" for n in range(60)]
    # Other document: all 60 chunks point at the query; the target chunk points away from it.
    query = np.array([1.0, 0.0], dtype=np.float32)
    backend.upsert(other_ids, np.tile(np.array([1.0, 0.01], dtype=np.float32), (60, 1)))
    backend.upsert(["t"], np.array([[0.0, 1.0]], dtype=np.float32))
    chunks = {cid: _chunk(cid, "other") for cid in other_ids}
    chunks["t"] = _chunk("t", "target")
    folder = DenseChannel(chunks, _FixedEncoder(query), backend)

    assert [h.chunk.chunk_id for h in folder.search("q", 3)] == other_ids[:3]
    scoped = folder.restricted({"t": chunks["t"]})
    assert [h.chunk.chunk_id for h in scoped.search("q", 3)] == ["t"]


def test_scoped_ask_cites_only_the_document(folder):
    svc, cid, target, _other = folder
    answer = svc.ask(cid, L2, "Zephyr kurulum", k=None, doc_id=target)
    assert answer.cited
    assert {chunk.doc_id for _n, chunk in answer.cited} == {target}
    assert {entry.chunk_id for entry in answer.trace} <= {
        c.chunk_id for c in svc.store.list_chunks(cid) if c.doc_id == target
    }


def test_scoped_ask_answers_a_document_with_one_chunk_among_many(folder):
    svc, cid, target, _other = folder
    answer = svc.ask(cid, L2, "Zephyr kurulum adımları", k=None, doc_id=target)
    assert answer.text is not None
    assert answer.cited[0][1].doc_id == target


def test_scoped_search_returns_only_that_documents_chunks(folder):
    svc, cid, target, _other = folder
    entries = svc.search(cid, L2, "sipariş stok modülü", k=10, doc_id=target)
    assert entries
    doc_chunk_ids = {c.chunk_id for c in svc.store.list_chunks(cid) if c.doc_id == target}
    assert {entry.chunk_id for entry in entries} <= doc_chunk_ids


def test_unknown_document_is_a_key_error(folder):
    svc, cid, _target, _other = folder
    with pytest.raises(KeyError):
        svc.index(cid).for_document(uuid.uuid4().hex)


def test_for_document_is_cached_until_the_collection_is_invalidated(folder):
    svc, cid, target, _other = folder
    index = svc.index(cid)
    assert index.for_document(target) is index.for_document(target)
    assert isinstance(index.for_document(target), CollectionIndex)
    svc.invalidate(cid)
    assert svc.index(cid).for_document(target) is not index.for_document(target)


def test_related_chunks_keeps_one_chunk_per_page_in_rank_order():
    hits = [
        _hit(_chunk("a", "d1", page=1)),
        _hit(_chunk("b", "d1", page=1)),
        _hit(_chunk("c", "d1", page=2)),
        _hit(_chunk("d", "d2", page=1)),
    ]
    assert [c.chunk_id for c in related_chunks(hits)] == ["a", "c", "d"]


def test_related_chunks_treats_chunks_without_a_page_as_distinct():
    hits = [_hit(_chunk("x", "d1")), _hit(_chunk("y", "d1")), _hit(_chunk("z", "d1", page=3))]
    assert [c.chunk_id for c in related_chunks(hits)] == ["x", "y", "z"]


def test_related_chunks_caps_the_count():
    hits = [_hit(_chunk(f"c{n}", "d", page=n)) for n in range(1, 10)]
    assert len(related_chunks(hits)) == 5
    assert len(related_chunks(hits, limit=2)) == 2


def test_ask_fills_related_in_rank_order(folder):
    svc, cid, _target, _other = folder
    answer = svc.ask(cid, L2, "sipariş stok modülü", k=None)
    pool = [entry.chunk_id for entry in answer.trace if entry.stage == "pool"]
    related = [chunk.chunk_id for chunk in answer.related]
    assert related
    assert related[0] == pool[0]
    assert related == sorted(related, key=pool.index)


def test_delete_collection_removes_its_originals_only(folder, tmp_path):
    svc, cid, target, other = folder
    assert svc.originals.path(target) is not None
    assert svc.originals.path(other) is not None
    source = tmp_path / "source.txt"
    source.write_text("kaynak", encoding="utf-8")
    keep_cid = svc.store.create_collection("keep")["id"]
    keep_doc = uuid.uuid4().hex
    svc.originals.save(keep_doc, source)
    assert svc.delete_collection(cid) is True
    assert svc.originals.path(target) is None
    assert svc.originals.path(other) is None
    assert svc.originals.path(keep_doc) is not None
    assert svc.store.get_collection(keep_cid) is not None


def test_one_original_that_cannot_be_removed_does_not_stop_the_rest(
    folder, tmp_path, monkeypatch, caplog
):
    svc, cid, target, other = folder
    third = uuid.uuid4().hex
    _ingest(svc, cid, tmp_path, "# Üçüncü\n\nÜçüncü belge metni.\n", third)
    failing = other
    real_delete = svc.originals.delete

    def delete_or_fail(doc_id: str) -> None:
        if doc_id == failing:
            raise OSError("disk busy")
        real_delete(doc_id)

    monkeypatch.setattr(svc.originals, "delete", delete_or_fail)
    with caplog.at_level("WARNING", logger="consultqa.api.services"):
        assert svc.delete_collection(cid) is True
    assert svc.store.get_collection(cid) is None
    assert svc.store.list_documents(cid) == []
    assert svc.originals.path(target) is None
    assert svc.originals.path(third) is None
    assert svc.originals.path(failing) is not None
    assert any(failing in record.getMessage() for record in caplog.records)
