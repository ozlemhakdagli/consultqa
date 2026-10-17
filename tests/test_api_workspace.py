"""Document workspace over HTTP: original files, document kinds, page citations and scoping."""

import hashlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pdf_fixtures import write_pdf

from consultqa.api.app import create_app
from consultqa.api.jobs import JobRunner
from consultqa.api.services import Services, build_services
from consultqa.config import Settings
from consultqa.models import Chunk

TEXT_NOTE = "# Stok\n\nStok modülü performans.\n".encode()
CSP = "default-src 'none'; sandbox"


@pytest.fixture
def services(tmp_path):
    svc = build_services(
        Settings(backend="stub", state_dir=tmp_path, max_upload_mb=1),
        jobs=JobRunner(synchronous=True),
    )
    svc.ready.set()
    return svc


@pytest.fixture
def client(services):
    with TestClient(create_app(services)) as c:
        yield c


@pytest.fixture
def pdf_services(tmp_path):
    svc = build_services(
        Settings(backend="stub", parser="pdfium", state_dir=tmp_path, max_upload_mb=1),
        jobs=JobRunner(synchronous=True),
    )
    svc.ready.set()
    return svc


@pytest.fixture
def pdf_client(pdf_services):
    with TestClient(create_app(pdf_services)) as c:
        yield c


def _collection(client, name: str = "c") -> str:
    return client.post("/api/collections", json={"name": name}).json()["id"]


def _upload_bytes(client, cid: str, data: bytes, name: str, media: str):
    return client.post(f"/api/collections/{cid}/documents", files={"file": (name, data, media)})


def _doc_ids(client, cid: str) -> list[str]:
    return [d["id"] for d in client.get(f"/api/collections/{cid}/documents").json()]


def _write_three_page_pdf(tmp_path: Path) -> Path:
    # Page 2 has no heading and page 3 is blank in the middle of the text, so page numbers
    # have to come from the pages themselves.
    return write_pdf(
        tmp_path / "rehber.pdf",
        [
            [("h1", "Sipariş"), ("p", "Sipariş modülü tablo filtreleme.")],
            [("p", "Stok modülü performans.")],
            [],
            [("p", "Kargo teslimatı beş gün sürer.")],
        ],
    )


# Step 1: the original file is served inline, with the headers that keep it from running.
def test_text_original_is_served_inline_with_the_safety_headers(client):
    cid = _collection(client)
    assert _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown").status_code == 202
    doc_id = _doc_ids(client, cid)[0]
    r = client.get(f"/api/collections/{cid}/documents/{doc_id}/file")
    assert r.status_code == 200
    assert r.content == TEXT_NOTE
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == CSP


def test_pdf_original_is_served_as_pdf(tmp_path, pdf_client):
    source = _write_three_page_pdf(tmp_path)
    cid = _collection(pdf_client)
    data = source.read_bytes()
    assert _upload_bytes(pdf_client, cid, data, "rehber.pdf", "application/pdf").status_code == 202
    doc_id = _doc_ids(pdf_client, cid)[0]
    r = pdf_client.get(f"/api/collections/{cid}/documents/{doc_id}/file")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == data
    assert r.headers["content-disposition"] == "inline"
    assert r.headers["content-security-policy"] == CSP


def test_file_of_an_unknown_collection_is_404(client):
    r = client.get(f"/api/collections/missing/documents/{uuid.uuid4().hex}/file")
    assert r.status_code == 404
    assert r.json() == {"detail": "collection_not_found"}


def test_file_of_an_unknown_document_is_404(client):
    cid = _collection(client)
    r = client.get(f"/api/collections/{cid}/documents/{uuid.uuid4().hex}/file")
    assert r.status_code == 404
    assert r.json() == {"detail": "document_not_found"}


# Review Focus 4: hostile ids never reach a file outside the originals folder. The exact detail is
# pinned per case. A plain "%2f" (and "%252f") is decoded to a real slash before routing, so the
# router answers its own 404 and the handler never runs. A triple-encoded "%25252f" reaches the
# handler as the literal text "..%2f", which the lookup then refuses.
@pytest.mark.parametrize(
    ("hostile", "detail"),
    [
        ("..%2f..%2fx", "not_found"),
        ("..%25252f..%25252fx", "document_not_found"),
        ("..%5c..%5cx", "document_not_found"),
        ("a" * 200, "document_not_found"),
    ],
)
def test_hostile_ids_on_the_file_endpoint_are_404(client, tmp_path, hostile, detail):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    # A file beside the originals folder must never be served through a hostile id.
    (tmp_path / "secret.txt").write_text("gizli", encoding="utf-8")
    r = client.get(f"/api/collections/{cid}/documents/{hostile}/file")
    assert r.status_code == 404
    assert r.json() == {"detail": detail}
    assert "gizli" not in r.text


def test_upper_case_version_of_a_real_id_is_404(client):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    real = _doc_ids(client, cid)[0]
    r = client.get(f"/api/collections/{cid}/documents/{real.upper()}/file")
    assert r.status_code == 404
    assert r.json() == {"detail": "document_not_found"}


def test_a_document_of_another_folder_is_404_on_file_ask_and_search(client):
    mine = _collection(client, "mine")
    theirs = _collection(client, "theirs")
    _upload_bytes(client, theirs, TEXT_NOTE, "notlar.md", "text/markdown")
    foreign = _doc_ids(client, theirs)[0]
    file_r = client.get(f"/api/collections/{mine}/documents/{foreign}/file")
    assert file_r.status_code == 404
    assert file_r.json() == {"detail": "document_not_found"}
    ask = client.post(f"/api/collections/{mine}/ask", json={"question": "Stok", "doc_id": foreign})
    assert ask.status_code == 404 and ask.json() == {"detail": "document_not_found"}
    search = client.post(
        f"/api/collections/{mine}/search", json={"query": "Stok", "doc_id": foreign}
    )
    assert search.status_code == 404 and search.json() == {"detail": "document_not_found"}


def test_an_unknown_doc_id_in_ask_is_404_and_too_long_is_422(client):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    unknown = client.post(
        f"/api/collections/{cid}/ask", json={"question": "Stok", "doc_id": uuid.uuid4().hex}
    )
    assert unknown.status_code == 404 and unknown.json() == {"detail": "document_not_found"}
    long_id = client.post(
        f"/api/collections/{cid}/ask", json={"question": "Stok", "doc_id": "a" * 200}
    )
    assert long_id.status_code == 422 and long_id.json() == {"detail": "validation_error"}


def test_an_upper_case_pdf_name_is_kind_pdf(tmp_path, pdf_client):
    source = _write_three_page_pdf(tmp_path)
    cid = _collection(pdf_client)
    _upload_bytes(pdf_client, cid, source.read_bytes(), "REHBER.PDF", "application/pdf")
    listed = pdf_client.get(f"/api/collections/{cid}/documents").json()
    assert listed[0]["kind"] == "pdf" and listed[0]["page_count"] == 4


def test_document_list_gives_kind_pages_and_original_flag(tmp_path, pdf_client):
    cid = _collection(pdf_client)
    _upload_bytes(pdf_client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    source = _write_three_page_pdf(tmp_path)
    _upload_bytes(pdf_client, cid, source.read_bytes(), "rehber.pdf", "application/pdf")
    listed = {d["filename"]: d for d in pdf_client.get(f"/api/collections/{cid}/documents").json()}
    note = listed["notlar.md"]
    assert note["kind"] == "text"
    assert note["page_count"] is None
    assert note["has_original"] is True
    assert {"id", "filename", "created_at"} <= set(note)
    guide = listed["rehber.pdf"]
    assert guide["kind"] == "pdf"
    assert guide["page_count"] == 4
    assert guide["has_original"] is True


def test_ask_cites_the_page_and_lists_related_pages(tmp_path, pdf_client):
    cid = _collection(pdf_client)
    source = _write_three_page_pdf(tmp_path)
    _upload_bytes(pdf_client, cid, source.read_bytes(), "rehber.pdf", "application/pdf")
    body = pdf_client.post(
        f"/api/collections/{cid}/ask", json={"question": "Kargo teslimatı", "preset": "L2"}
    ).json()
    assert body["citations"][0]["page"] == 4
    related = body["related"]
    assert related, "related must list the top pages of the answer"
    assert {"chunk_id", "doc_id", "page", "heading_path"} <= set(related[0])
    assert related[0]["page"] == 4
    assert len({r["page"] for r in related}) == len(related)


def test_text_citation_and_related_have_no_page(client):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2"})
    data = body.json()
    assert data["citations"][0]["page"] is None
    assert data["related"][0]["page"] is None
    assert data["related"][0]["heading_path"] == ["Stok"]


def test_doc_id_scopes_ask_and_search_to_that_document(client):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "bir.md", "text/markdown")
    _upload_bytes(client, cid, b"# Stok\n\nStok ikinci belge.\n", "iki.md", "text/markdown")
    first, second = _doc_ids(client, cid)
    ask = client.post(
        f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2", "doc_id": second}
    ).json()
    assert ask["citations"] and all(c["doc_id"] == second for c in ask["citations"])
    search = client.post(
        f"/api/collections/{cid}/search", json={"query": "Stok", "k": 5, "doc_id": first}
    ).json()
    assert search["hits"] and all(h["chunk_id"].startswith(first) for h in search["hits"])


def test_a_document_without_an_original_is_404_and_still_searchable(services, client):
    cid = _collection(client)
    doc_id = uuid.uuid4().hex
    chunk = Chunk(
        chunk_id=f"{doc_id}-0",
        doc_id=doc_id,
        position=0,
        heading_path=("Stok",),
        text="Stok modülü performans.",
    )
    services.store.add_document(cid, doc_id, "old-sha", "eski.md", [chunk], has_original=False)
    services.dense(cid).upsert([chunk.chunk_id], services.encoder.encode_passages([chunk.text]))
    services.invalidate(cid)
    r = client.get(f"/api/collections/{cid}/documents/{doc_id}/file")
    assert r.status_code == 404 and r.json() == {"detail": "file_not_found"}
    listed = client.get(f"/api/collections/{cid}/documents").json()
    assert listed[0]["has_original"] is False and listed[0]["kind"] == "text"
    ask = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2"})
    assert ask.status_code == 200 and ask.json()["citations"][0]["doc_id"] == doc_id
    search = client.post(f"/api/collections/{cid}/search", json={"query": "Stok", "k": 3})
    assert search.status_code == 200 and search.json()["hits"][0]["chunk_id"] == f"{doc_id}-0"


def test_deleting_a_document_removes_its_original(client, services):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    doc_id = _doc_ids(client, cid)[0]
    assert services.originals.path(doc_id) is not None
    assert client.delete(f"/api/collections/{cid}/documents/{doc_id}").status_code == 204
    assert services.originals.path(doc_id) is None
    gone = client.get(f"/api/collections/{cid}/documents/{doc_id}/file")
    assert gone.status_code == 404


def test_deleting_a_folder_removes_the_originals(client, services):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    doc_id = _doc_ids(client, cid)[0]
    assert client.delete(f"/api/collections/{cid}").status_code == 204
    assert services.originals.path(doc_id) is None


def test_delete_is_204_when_the_original_cannot_be_removed(client, services, monkeypatch, caplog):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    doc_id = _doc_ids(client, cid)[0]

    def refuse(_doc_id):
        raise OSError("disk unplugged")

    monkeypatch.setattr(services.originals, "delete", refuse)
    with caplog.at_level("WARNING"):
        r = client.delete(f"/api/collections/{cid}/documents/{doc_id}")
    assert r.status_code == 204
    assert _doc_ids(client, cid) == []
    assert doc_id in caplog.text


def test_listing_and_the_file_endpoint_need_no_model_readiness(services, client):
    services.ready.clear()
    cid = _collection(client)
    assert client.get(f"/api/collections/{cid}/documents").status_code == 200
    r = client.get(f"/api/collections/{cid}/documents/{uuid.uuid4().hex}/file")
    assert r.status_code == 404 and r.json() == {"detail": "document_not_found"}


def test_a_delete_of_an_unknown_id_keeps_the_unreachable_store_status(services, client):
    cid = _collection(client)

    def unreachable(collection_id, dim):
        # Building the store connects to the server, so a cold cache fails here.
        raise ConnectionError("refused")

    services.make_dense = unreachable
    services.invalidate(cid)
    r = client.delete(f"/api/collections/{cid}/documents/{uuid.uuid4().hex}")
    assert r.status_code == 503
    assert r.json() == {"detail": "vector_store_unavailable"}


def test_a_scoped_question_whose_document_vanished_is_404(client, monkeypatch):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    doc_id = _doc_ids(client, cid)[0]

    def vanished(self, *args, **kwargs):
        raise KeyError(doc_id)

    monkeypatch.setattr(Services, "ask", vanished)
    body = {"question": "Stok", "preset": "L2", "doc_id": doc_id}
    r = client.post(f"/api/collections/{cid}/ask", json=body)
    assert r.status_code == 404 and r.json() == {"detail": "document_not_found"}


def test_a_key_error_without_a_scope_stays_an_internal_error(services, monkeypatch):
    with TestClient(create_app(services), raise_server_exceptions=False) as client:
        cid = _collection(client)
        _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")

        def broken(self, *args, **kwargs):
            raise KeyError("chunk")

        monkeypatch.setattr(Services, "ask", broken)
        monkeypatch.setattr(Services, "search", broken)
        ask = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2"})
        assert ask.status_code == 500 and ask.json() == {"detail": "internal_error"}
        search = client.post(f"/api/collections/{cid}/search", json={"query": "Stok"})
        assert search.status_code == 500 and search.json() == {"detail": "internal_error"}


def test_a_legacy_document_is_replaced_by_the_same_text_uploaded_again(client, services):
    cid = _collection(client)
    old = uuid.uuid4().hex
    chunk = Chunk(
        chunk_id=f"{old}-0",
        doc_id=old,
        position=0,
        heading_path=("Stok",),
        text="Stok modülü performans.",
    )
    digest = hashlib.sha256(TEXT_NOTE.decode("utf-8").encode("utf-8")).hexdigest()
    services.store.add_document(cid, old, digest, "notlar.md", [chunk], has_original=False)
    services.dense(cid).upsert([chunk.chunk_id], services.encoder.encode_passages([chunk.text]))
    services.invalidate(cid)
    assert _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown").status_code == 202
    listed = client.get(f"/api/collections/{cid}/documents").json()
    assert len(listed) == 1 and listed[0]["id"] != old
    assert listed[0]["has_original"] is True
    assert all(c.doc_id == listed[0]["id"] for c in services.store.list_chunks(cid))


# The text fallback: a document's passages grouped by page, with the same id checks as the file.
def test_text_of_a_pdf_groups_its_passages_by_page(tmp_path, pdf_client):
    cid = _collection(pdf_client)
    source = _write_three_page_pdf(tmp_path)
    _upload_bytes(pdf_client, cid, source.read_bytes(), "rehber.pdf", "application/pdf")
    doc = _doc_ids(pdf_client, cid)[0]
    r = pdf_client.get(f"/api/collections/{cid}/documents/{doc}/text")
    assert r.status_code == 200
    pages = r.json()["pages"]
    # Page 3 is blank and has no passage, so it has no entry.
    assert [p["page"] for p in pages] == [1, 2, 4]
    assert "Sipariş modülü tablo filtreleme." in pages[0]["text"]
    assert pages[1]["text"] == "Stok modülü performans."


def test_text_of_a_markdown_upload_is_one_entry_without_page(client, services):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    doc = _doc_ids(client, cid)[0]
    r = client.get(f"/api/collections/{cid}/documents/{doc}/text")
    assert r.status_code == 200
    (entry,) = r.json()["pages"]
    assert entry["page"] is None
    assert "Stok modülü performans." in entry["text"]


def test_text_joins_the_passages_of_one_page_with_a_blank_line(client, services):
    cid = _collection(client)
    chunks = [
        Chunk("x#0", "x", 0, (), "birinci", page=1),
        Chunk("x#1", "x", 1, (), "ikinci", page=1),
        Chunk("x#2", "x", 2, (), "üçüncü", page=2),
    ]
    services.store.add_document(cid, "x", "sha", "rehber.pdf", chunks, page_count=2)
    r = client.get(f"/api/collections/{cid}/documents/x/text")
    assert r.status_code == 200
    assert r.json() == {
        "pages": [{"page": 1, "text": "birinci\n\nikinci"}, {"page": 2, "text": "üçüncü"}]
    }


def test_text_of_a_document_without_original_is_still_served(client, services):
    cid = _collection(client)
    chunks = [Chunk("x#0", "x", 0, (), "eski metin")]
    services.store.add_document(cid, "x", "sha", "eski.txt", chunks, has_original=False)
    r = client.get(f"/api/collections/{cid}/documents/x/text")
    assert r.status_code == 200
    assert r.json() == {"pages": [{"page": None, "text": "eski metin"}]}


def test_text_of_an_unknown_collection_is_404(client):
    r = client.get(f"/api/collections/missing/documents/{uuid.uuid4().hex}/text")
    assert r.status_code == 404
    assert r.json() == {"detail": "collection_not_found"}


def test_text_of_an_unknown_document_is_404(client):
    cid = _collection(client)
    r = client.get(f"/api/collections/{cid}/documents/{uuid.uuid4().hex}/text")
    assert r.status_code == 404
    assert r.json() == {"detail": "document_not_found"}


@pytest.mark.parametrize(
    ("hostile", "detail"),
    [
        ("..%2f..%2fx", "not_found"),
        ("..%25252f..%25252fx", "document_not_found"),
        ("..%5c..%5cx", "document_not_found"),
        ("a" * 200, "document_not_found"),
    ],
)
def test_hostile_ids_on_the_text_endpoint_are_404(client, hostile, detail):
    cid = _collection(client)
    _upload_bytes(client, cid, TEXT_NOTE, "notlar.md", "text/markdown")
    r = client.get(f"/api/collections/{cid}/documents/{hostile}/text")
    assert r.status_code == 404
    assert r.json() == {"detail": detail}


def test_upper_case_id_and_a_foreign_folders_document_are_404_on_text(client):
    mine = _collection(client, "mine")
    theirs = _collection(client, "theirs")
    _upload_bytes(client, theirs, TEXT_NOTE, "notlar.md", "text/markdown")
    foreign = _doc_ids(client, theirs)[0]
    r = client.get(f"/api/collections/{mine}/documents/{foreign}/text")
    assert r.status_code == 404 and r.json() == {"detail": "document_not_found"}
    r = client.get(f"/api/collections/{theirs}/documents/{foreign.upper()}/text")
    assert r.status_code == 404 and r.json() == {"detail": "document_not_found"}


def test_a_200_page_document_comes_back_in_one_response(tmp_path, pdf_client):
    cid = _collection(pdf_client)
    source = write_pdf(tmp_path / "uzun.pdf", [[("p", f"Sayfa {n} metni.")] for n in range(1, 201)])
    _upload_bytes(pdf_client, cid, source.read_bytes(), "uzun.pdf", "application/pdf")
    doc = _doc_ids(pdf_client, cid)[0]
    r = pdf_client.get(f"/api/collections/{cid}/documents/{doc}/text")
    assert r.status_code == 200
    pages = r.json()["pages"]
    assert [p["page"] for p in pages] == list(range(1, 201))
    assert pages[199]["text"] == "Sayfa 200 metni."


# Docling writes image placeholders as lines of their own. They are hidden in responses only;
# the stored chunk keeps them, so the content hash of the document does not change.
PLACEHOLDER_NOTE = "# Stok\n\n<!-- image -->\n\nStok modülü performans.\n".encode()


def test_citation_text_hides_the_image_placeholder_and_keeps_the_text(client, services):
    cid = _collection(client)
    _upload_bytes(client, cid, PLACEHOLDER_NOTE, "notlar.md", "text/markdown")
    body = client.post(f"/api/collections/{cid}/ask", json={"question": "Stok", "preset": "L2"})
    text = body.json()["citations"][0]["text"]
    assert "<!-- image -->" not in text
    assert "Stok modülü performans." in text
    assert any("<!-- image -->" in c.text for c in services.store.list_chunks(cid))


def test_text_endpoint_hides_the_image_placeholder_but_storage_keeps_it(client, services):
    cid = _collection(client)
    _upload_bytes(client, cid, PLACEHOLDER_NOTE, "notlar.md", "text/markdown")
    doc = _doc_ids(client, cid)[0]
    r = client.get(f"/api/collections/{cid}/documents/{doc}/text")
    assert r.status_code == 200
    (entry,) = r.json()["pages"]
    assert "<!-- image -->" not in entry["text"]
    assert entry["text"].endswith("Stok modülü performans.")
    stored = [c.text for c in services.store.document_chunks(cid, doc)]
    assert any("<!-- image -->" in text for text in stored)


def test_text_without_a_placeholder_is_returned_unchanged(client, services):
    cid = _collection(client)
    chunks = [Chunk("x#0", "x", 0, (), "  birinci\n\nikinci  ")]
    services.store.add_document(cid, "x", "sha", "eski.txt", chunks, has_original=False)
    r = client.get(f"/api/collections/{cid}/documents/x/text")
    assert r.json() == {"pages": [{"page": None, "text": "  birinci\n\nikinci  "}]}
