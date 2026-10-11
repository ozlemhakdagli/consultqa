"""HTTP API with the stub backend: error contract, ingestion, questions and passage search."""

import httpx
import pytest
from fastapi.testclient import TestClient

from docrag.api import services as services_module
from docrag.api.app import create_app
from docrag.api.jobs import JobRunner
from docrag.api.services import DB_FILENAME, build_services
from docrag.config import Settings
from docrag.generate.llm_client import LLMClient
from docrag.store.sqlite_store import SqliteStore

TWO_SECTIONS = "# Sipariş\n\nSipariş modülü tablo filtreleme.\n\n# Stok\n\nStok modülü performans."


class RecordingReader:
    """Extractive reader that records the context it was given and returns a fixed answer."""

    def __init__(self) -> None:
        self.contexts: list[str] = []

    def answer_span(self, question: str, context: str) -> tuple[str, float]:
        self.contexts.append(context)
        return "ok", 1.0


@pytest.fixture
def services(tmp_path):
    settings = Settings(backend="stub", state_dir=tmp_path, max_upload_mb=0.001)
    svc = build_services(settings, jobs=JobRunner(synchronous=True))
    svc.ready.set()
    return svc


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as c:
        yield c


def _collection(client, name: str = "c") -> str:
    return client.post("/api/collections", json={"name": name}).json()["id"]


def _upload(client, cid: str, text: str, name: str = "a.txt"):
    return client.post(
        f"/api/collections/{cid}/documents",
        files={"file": (name, text.encode("utf-8"), "text/plain")},
    )


def test_blank_question_is_422(client):
    cid = _collection(client)
    r = client.post(f"/api/collections/{cid}/ask", json={"question": "   "})
    assert r.status_code == 422
    assert r.json() == {"detail": "validation_error"}


def test_not_ready_until_loaded(services):
    services.ready.clear()
    # Without the lifespan, no loader thread runs, so the flag stays under the test's control.
    client = TestClient(create_app(services))
    assert client.get("/api/ready").json() == {"detail": "not_ready"}
    assert client.get("/api/ready").status_code == 503
    assert client.get("/api/health").status_code == 200
    services.ready.set()
    assert client.get("/api/ready").status_code == 200


def test_lifespan_loads_in_background(services):
    services.ready.clear()
    with TestClient(create_app(services)) as client:
        assert services.ready.wait(timeout=5)
        assert client.get("/api/ready").status_code == 200


def test_collection_create_list_and_duplicate_name(client):
    created = client.post("/api/collections", json={"name": "Stok"})
    assert created.status_code == 201
    assert created.json()["name"] == "Stok"
    assert client.post("/api/collections", json={"name": "Stok"}).json() == {
        "detail": "collection_exists"
    }
    assert [c["name"] for c in client.get("/api/collections").json()] == ["Stok"]


def test_unknown_collection_is_404(client):
    r = _upload(client, "missing", "metin")
    assert r.status_code == 404
    assert r.json() == {"detail": "collection_not_found"}
    r = client.post("/api/collections/missing/ask", json={"question": "stok"})
    assert r.json() == {"detail": "collection_not_found"}


def test_unsupported_upload_type_is_415(client):
    cid = _collection(client)
    r = client.post(
        f"/api/collections/{cid}/documents",
        files={"file": ("x.exe", b"MZ", "application/octet-stream")},
    )
    assert r.status_code == 415
    assert r.json() == {"detail": "unsupported_type"}


def test_oversize_upload_is_413(client):
    cid = _collection(client)
    r = _upload(client, cid, "a" * 5000)
    assert r.status_code == 413
    assert r.json() == {"detail": "file_too_large"}


# [R3] A corrupt PDF ends as a failed job with a code, and leaves no document behind.
def test_corrupt_pdf_job_reports_parse_failed(client):
    cid = _collection(client)
    r = client.post(
        f"/api/collections/{cid}/documents",
        files={"file": ("x.pdf", b"nope", "application/pdf")},
    )
    assert r.status_code == 202
    job = client.get(f"/api/jobs/{r.json()['job_id']}").json()
    assert job["state"] == "failed"
    assert job["error"] == "parse_failed"
    assert client.get(f"/api/collections/{cid}/documents").json() == []


def test_unknown_job_is_404(client):
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "job_not_found"}


def test_duplicate_upload_reports_the_existing_document(client):
    cid = _collection(client)
    first = _upload(client, cid, "Aynı metin").json()
    second = _upload(client, cid, "Aynı metin", name="kopya.txt").json()
    job = client.get(f"/api/jobs/{second['job_id']}").json()
    assert job["state"] == "done"
    assert job["document_id"] == first["document_id"]
    assert len(client.get(f"/api/collections/{cid}/documents").json()) == 1


def test_delete_document_removes_it_from_answers(client):
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    before = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok"}).json()
    assert before["answer"] is not None
    doc_id = client.get(f"/api/collections/{cid}/documents").json()[0]["id"]
    assert client.delete(f"/api/collections/{cid}/documents/{doc_id}").status_code == 204
    after = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok"}).json()
    assert after["answer"] is None and after["citations"] == []
    again = client.delete(f"/api/collections/{cid}/documents/{doc_id}")
    assert again.status_code == 404
    assert again.json() == {"detail": "document_not_found"}


def test_busy_returns_429(client):
    cid = _collection(client)
    semaphore = client.app.state.inference_semaphore
    assert semaphore.acquire(blocking=False)
    try:
        r = client.post(f"/api/collections/{cid}/ask", json={"question": "stok"})
    finally:
        semaphore.release()
    assert r.status_code == 429
    assert r.json() == {"detail": "busy"}


def test_unknown_preset_is_422(client):
    cid = _collection(client)
    r = client.post(f"/api/collections/{cid}/ask", json={"question": "stok", "preset": "L9"})
    assert r.status_code == 422
    assert r.json() == {"detail": "unknown_preset"}


def test_presets_list_and_paper_is_unavailable_by_default(client):
    assert client.get("/api/presets").json() == ["L2", "L3", "L4", "L5", "L4+llm", "L5+llm"]
    cid = _collection(client)
    r = client.post(f"/api/collections/{cid}/ask", json={"question": "stok", "preset": "paper"})
    assert r.status_code == 422
    assert r.json() == {"detail": "preset_unavailable"}


def test_llm_preset_without_an_llm_is_503(services, client):
    services.llm = None
    cid = _collection(client)
    r = client.post(f"/api/collections/{cid}/ask", json={"question": "stok", "preset": "L4+llm"})
    assert r.status_code == 503
    assert r.json() == {"detail": "llm_unavailable"}


# [R5] An LLM that times out returns llm_unavailable with the trace, and extractive presets answer.
def test_llm_timeout_is_503_and_extractive_still_works(services, client):
    def handler(request):
        raise httpx.ConnectTimeout("slow")

    services.llm = LLMClient("http://llm", "m", transport=httpx.MockTransport(handler))
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    slow = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L4+llm"})
    assert slow.status_code == 503
    assert slow.json()["detail"] == "llm_unavailable"
    assert slow.json()["trace"]
    fast = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L4"})
    assert fast.status_code == 200
    assert fast.json()["answer"] is not None


def test_extractive_reader_sees_only_the_best_passage(services, client):
    # L4 adds a neighbour for the LLM, but the extractive reader gets the top hit alone.
    reader = RecordingReader()
    services.reader = reader
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L4"})
    assert body.status_code == 200
    assert len(reader.contexts) == 1
    assert "Stok" in reader.contexts[0] and "Sipariş" not in reader.contexts[0]
    assert body.json()["answer"] == "ok"
    citation = body.json()["citations"][0]
    assert citation["number"] == 1 and citation["heading_path"] == ["Stok"]


def test_llm_answer_is_parsed_into_citations(client):
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L4+llm"})
    assert body.status_code == 200
    data = body.json()
    assert data["preset"] == "L4+llm"
    assert data["answer"].endswith("[1]")
    assert [c["number"] for c in data["citations"]] == [1]
    assert {"stage", "chunk_id", "rank", "score", "score_type", "channel"} <= set(data["trace"][0])


def test_ask_on_an_empty_collection_has_no_answer(client):
    cid = _collection(client)
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "stok"}).json()
    assert body["answer"] is None and body["citations"] == []


def test_search_returns_the_final_ranking_up_to_k(client):
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    body = client.post(f"/api/collections/{cid}/search", json={"query": "Stok", "k": 1}).json()
    assert len(body["hits"]) == 1
    assert body["hits"][0]["stage"] == "pool"
    assert body["hits"][0]["rank"] == 1
    assert body["preset"] == "L2"


def test_paper_preset_runs_the_published_method_when_enabled(services, client, monkeypatch):
    class FakePaper:
        def __init__(self, chunks) -> None:
            self._chunks = list(chunks)

        def ranked_chunk_ids(self, query: str) -> list[str]:
            return [self._chunks[0].chunk_id]

        def answer(self, query: str) -> str:
            return "paper answer"

    monkeypatch.setattr(services_module, "PaperMethod", FakePaper)
    services.paper_enabled = True
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    assert "paper" in client.get("/api/presets").json()
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "paper"})
    assert body.status_code == 200
    assert body.json()["answer"] == "paper answer"
    assert [c["number"] for c in body.json()["citations"]] == [1]


# [R5] An unexpected failure is reported with a code and no details.
def test_unexpected_error_is_500_internal_error(services):
    class Boom:
        def answer_span(self, question: str, context: str) -> tuple[str, float]:
            raise RuntimeError("secret detail")

    services.reader = Boom()
    client = TestClient(create_app(services), raise_server_exceptions=False)
    cid = client.post("/api/collections", json={"name": "c"}).json()["id"]
    _upload(client, cid, TWO_SECTIONS)
    r = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L4"})
    assert r.status_code == 500
    assert r.json() == {"detail": "internal_error"}


def test_upload_is_refused_until_the_models_are_ready(services):
    services.ready.clear()
    # No lifespan here, so the loader thread does not set the flag behind the test's back.
    client = TestClient(create_app(services))
    cid = _collection(client)
    r = _upload(client, cid, TWO_SECTIONS)
    assert r.status_code == 503
    assert r.json() == {"detail": "not_ready"}
    assert client.get(f"/api/collections/{cid}/documents").json() == []


def test_stored_name_is_the_upload_name_and_never_the_staging_name(client):
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS, name="Ocak Kılavuzu.txt")
    _upload(client, cid, "Başka metin", name="../../gizli/kaynak.md")
    names = [d["filename"] for d in client.get(f"/api/collections/{cid}/documents").json()]
    assert names == ["Ocak Kılavuzu.txt", "kaynak.md"]


def test_declared_length_above_the_limit_is_413_before_the_body_is_read(client):
    cid = _collection(client)
    r = client.post(
        f"/api/collections/{cid}/documents",
        files={"file": ("a.txt", "kısa".encode(), "text/plain")},
        headers={"Content-Length": str(10**9)},
    )
    assert r.status_code == 413
    assert r.json() == {"detail": "file_too_large"}
    assert client.get(f"/api/collections/{cid}/documents").json() == []


class _UnreachableStore:
    """A dense store whose server cannot be reached, as when Qdrant is down."""

    def upsert(self, ids, vectors):
        raise ConnectionError("refused")

    def delete(self, ids):
        raise ConnectionError("refused")

    def search(self, vector, k):
        raise ConnectionError("refused")


def test_unreachable_vector_store_is_503_for_ask_and_delete(services, client):
    cid = _collection(client)
    _upload(client, cid, TWO_SECTIONS)
    doc_id = client.get(f"/api/collections/{cid}/documents").json()[0]["id"]
    # Drop the cached retrieval state, then point the service at the unreachable store.
    services.invalidate(cid)
    services.make_dense = lambda collection_id, dim: _UnreachableStore()
    ask = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2"})
    assert ask.status_code == 503
    assert ask.json() == {"detail": "vector_store_unavailable"}
    delete = client.delete(f"/api/collections/{cid}/documents/{doc_id}")
    assert delete.status_code == 503
    assert delete.json() == {"detail": "vector_store_unavailable"}


def test_startup_marks_unfinished_jobs_as_interrupted(tmp_path):
    store = SqliteStore(tmp_path / DB_FILENAME)
    cid = store.create_collection("c")["id"]
    stuck = store.create_job(cid, "d1")
    store.set_job(stuck, "embedding")
    queued = store.create_job(cid, "d2")
    finished = store.create_job(cid, "d3")
    store.set_job(finished, "done")
    build_services(Settings(backend="stub", state_dir=tmp_path))
    for job_id in (stuck, queued):
        job = store.get_job(job_id)
        assert job["state"] == "failed" and job["error"] == "interrupted"
    assert store.get_job(finished)["state"] == "done"
