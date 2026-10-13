"""Retrieval state of a collection. The evidence graph is built on first use by a preset that
expands through it, and the L5 rankings are the same as with a graph built up front."""

import uuid
from pathlib import Path

import pytest

from consultqa.api import services as services_module
from consultqa.api.jobs import JobRunner
from consultqa.api.services import Services, build_services
from consultqa.config import PRESETS, Settings
from consultqa.graph.build import build_graph
from consultqa.ingest.pipeline import ingest_file
from consultqa.retrieve.dense import DenseChannel
from consultqa.retrieve.pipeline import Retriever
from consultqa.retrieve.sparse import SparseChannel
from consultqa.store.originals import OriginalFiles

L2 = PRESETS["L2"]
L5 = PRESETS["L5"]
QUERIES = [
    "Stok modülü performans",
    "Bölüm 2 kurulum adımları",
    "sipariş filtreleme tablo",
    "rapor modülü stok",
]


def _doc_id(name: str) -> str:
    # Document ids name files in the originals folder, so they must be 32 lowercase hex characters.
    return uuid.uuid5(uuid.NAMESPACE_OID, name).hex


def _document(number: int) -> str:
    """Three headed sections. Section 1 refers to section 2 by number, and the terms recur across
    documents, so the graph has structure, section, term, next-chunk and cross-reference edges."""
    return (
        f"# 1 Giriş\n\nSipariş modülü {number} tablo filtreleme. Ayrıntı için Bölüm 2 bkz.\n\n"
        f"# 2 Kurulum\n\nKurulum adımları stok modülü {number} performans.\n\n"
        f"# 3 Raporlar\n\nRapor modülü tablo sipariş {number} stok ortak metin.\n"
    )


def _service(tmp_path: Path) -> Services:
    return build_services(
        Settings(backend="stub", state_dir=tmp_path / "state"), jobs=JobRunner(synchronous=True)
    )


def _collection(svc: Services, tmp_path: Path) -> str:
    cid = svc.store.create_collection("c")["id"]
    for number in range(4):
        path = tmp_path / f"doc{number}.txt"
        path.write_text(_document(number), encoding="utf-8")
        job = svc.store.create_job(cid, f"doc{number}")
        written = ingest_file(
            store=svc.store,
            parser=svc.parser,
            encoder=svc.encoder,
            dense=svc.dense(cid),
            job_id=job,
            collection_id=cid,
            doc_id=_doc_id(f"doc{number}"),
            path=path,
            filename=path.name,
            max_tokens=svc.settings.chunk_max_tokens,
            count_tokens=svc.count_tokens,
            originals=OriginalFiles(tmp_path / "files"),
        )
        assert written is True
    return cid


def _eager_retriever(svc: Services, cid: str, cfg) -> Retriever:
    """The L5 pipeline with its graph built from the chunks before any question is asked."""
    chunks = svc.store.list_chunks(cid)
    dense = DenseChannel({c.chunk_id: c for c in chunks}, svc.encoder, svc.dense(cid))
    return Retriever(
        cfg,
        chunks,
        dense=dense,
        sparse=SparseChannel(chunks, per_document_fold=True),
        graph=build_graph(chunks),
        scorer=svc.scorer,
    )


def _ranking(result) -> list[tuple[str, float]]:
    return [(hit.chunk.chunk_id, hit.score) for hit in result.hits]


@pytest.fixture
def collection(tmp_path):
    svc = _service(tmp_path)
    return svc, _collection(svc, tmp_path)


def test_l5_rankings_are_equal_with_a_lazy_graph_and_an_eager_one(collection):
    svc, cid = collection
    lazy = svc.index(cid).retriever(L5)
    eager = _eager_retriever(svc, cid, L5)
    graph_hits = 0
    for query in QUERIES:
        lazy_result = lazy.retrieve(query)
        eager_result = eager.retrieve(query)
        assert lazy_result.trace == eager_result.trace
        assert _ranking(lazy_result) == _ranking(eager_result)
        graph_hits += sum(entry.stage == "graph" for entry in lazy_result.trace)
    # The comparison means something only if the graph contributed to these rankings.
    assert graph_hits > 0


def test_the_graph_is_built_on_first_use_by_a_graph_preset_only(collection, monkeypatch):
    svc, cid = collection
    built: list[int] = []
    real_build = services_module.build_graph

    def counting_build(chunks):
        built.append(len(chunks))
        return real_build(chunks)

    monkeypatch.setattr(services_module, "build_graph", counting_build)
    index = svc.index(cid)
    index.retriever(L2).retrieve(QUERIES[0])
    assert built == []
    index.retriever(L5).retrieve(QUERIES[0])
    index.retriever(L5).retrieve(QUERIES[1])
    assert built == [len(svc.store.list_chunks(cid))]


def test_the_lazily_built_graph_is_byte_identical_to_the_eager_build(collection):
    svc, cid = collection
    chunks = svc.store.list_chunks(cid)
    assert svc.index(cid).graph().to_bytes() == build_graph(chunks).to_bytes()


def test_a_changed_collection_gets_a_graph_of_its_current_chunks(collection, tmp_path):
    svc, cid = collection
    before = len(svc.index(cid).graph().chunk_ids)
    path = tmp_path / "late.txt"
    path.write_text(_document(9), encoding="utf-8")
    job = svc.store.create_job(cid, "late")
    ingest_file(
        store=svc.store,
        parser=svc.parser,
        encoder=svc.encoder,
        dense=svc.dense(cid),
        job_id=job,
        collection_id=cid,
        doc_id=_doc_id("late"),
        path=path,
        filename=path.name,
        max_tokens=svc.settings.chunk_max_tokens,
        count_tokens=svc.count_tokens,
        originals=OriginalFiles(tmp_path / "files"),
    )
    svc.invalidate(cid)
    after = svc.index(cid).graph()
    assert len(after.chunk_ids) > before
    assert after.to_bytes() == build_graph(svc.store.list_chunks(cid)).to_bytes()
