"""The page is wired to the document workspace: three panes, the question thread, the scope choice,
the viewer keys and the folder switch, through the real stub backend."""

from pathlib import Path

import pytest
from playwright.sync_api import expect
from ui_helpers import (
    collection_with_document,
    create_collection,
    open_page,
    unique,
    upload_and_wait,
    upload_text,
)

ROOT = Path(__file__).resolve().parents[2]
ASK = "Cevabı bul"
QUESTION = "Stok modülü"


def _ask(page, question=QUESTION):
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def _open_document(page, filename):
    page.get_by_role("button", name=f"{filename} belgesini aç").click()


def _turns(page):
    return page.locator("#result section.turn")


def test_the_old_result_module_is_gone_and_nothing_imports_it():
    assert not (ROOT / "frontend" / "js" / "views" / "result.js").exists()
    for path in (ROOT / "frontend" / "js").rglob("*.js"):
        assert "views/result.js" not in path.read_text(encoding="utf-8"), path


@pytest.mark.e2e
def test_the_three_panes_and_tabs_switch_the_visible_pane(make_page, base_url):
    # Below 1000 px the tab row picks the pane; the tabs are hidden on a wide screen.
    page = make_page(width=800, height=900)
    open_page(page, base_url)
    for pane in ("pane-documents", "pane-viewer", "pane-chat"):
        expect(page.locator(f"#{pane}")).to_have_count(1)
    for tab in ("tab-documents", "tab-viewer", "tab-chat"):
        expect(page.locator(f"#{tab}")).to_have_attribute("role", "tab")
    expect(page.locator("#pane-documents")).to_have_attribute("data-pane-active", "true")

    page.locator("#tab-chat").click()
    expect(page.locator("#pane-chat")).to_have_attribute("data-pane-active", "true")
    expect(page.locator("#pane-documents")).to_have_attribute("data-pane-active", "false")
    expect(page.locator("#tab-chat")).to_have_attribute("aria-selected", "true")

    page.locator("#tab-viewer").click()
    expect(page.locator("#pane-viewer")).to_have_attribute("data-pane-active", "true")
    expect(page.locator("#pane-chat")).to_have_attribute("data-pane-active", "false")


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_an_uploaded_text_file_and_a_question_show_one_turn_with_its_source(page, base_url):
    collection_with_document(page, base_url)
    expect(page.locator("#result section.turn")).to_have_count(0)
    _ask(page)
    expect(_turns(page)).to_have_count(1)
    turn = _turns(page).first
    expect(turn.locator(".turn-question")).to_have_text(QUESTION)
    expect(turn.locator(".answer-card")).to_be_visible()
    expect(turn.locator(".citation-card")).to_contain_text("Belge: ocak.md")
    expect(page.locator("#result-empty")).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_a_second_question_adds_a_second_turn(page, base_url):
    collection_with_document(page, base_url)
    _ask(page)
    expect(_turns(page)).to_have_count(1)
    _ask(page, "Stok modülü performans")
    expect(_turns(page)).to_have_count(2)
    expect(_turns(page).nth(0).locator(".turn-question")).to_have_text(QUESTION)
    expect(_turns(page).nth(1).locator(".turn-question")).to_have_text("Stok modülü performans")


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_switching_the_folder_clears_the_thread(page, base_url):
    # No reload between the steps: the thread and the viewer exist in memory when the folder changes.
    collection_with_document(page, base_url)
    _ask(page)
    expect(_turns(page)).to_have_count(1)
    _open_document(page, "ocak.md")
    expect(page.locator("#viewer-title")).to_have_text("ocak.md")
    page.locator("#scope-folder").check()
    create_collection(page, unique("Yeni klasör"))
    expect(_turns(page)).to_have_count(0)
    expect(page.locator("#viewer-empty")).to_be_visible()
    expect(page.locator("#viewer-title")).to_have_text("Belge")
    expect(page.locator("#viewer-toolbar")).to_be_hidden()
    expect(page.locator("#viewer-canvas")).to_be_hidden()
    expect(page.locator("#viewer-text")).to_be_hidden()
    expect(page.locator("#scope-folder")).to_be_checked()


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_deleting_the_open_document_resets_the_viewer(page, base_url):
    collection_with_document(page, base_url)
    _open_document(page, "ocak.md")
    expect(page.locator("#viewer-title")).to_have_text("ocak.md")
    expect(page.locator("#viewer-empty")).to_be_hidden()

    page.get_by_role("button", name="ocak.md belgesini sil").click()
    page.get_by_role("button", name="Evet, sil").click()
    expect(page.locator("#document-list li").filter(has_text="ocak.md")).to_have_count(0)
    expect(page.locator("#viewer-empty")).to_be_visible()
    expect(page.locator("#viewer-title")).to_have_text("Belge")
    expect(page.locator("#viewer-toolbar")).to_be_hidden()
    expect(page.locator("#viewer-canvas")).to_be_hidden()
    expect(page.locator("#viewer-text")).to_be_hidden()
    expect(page.locator("#viewer-message")).to_be_hidden()
    expect(page.locator("#scope-document")).to_be_disabled()


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_deleting_another_document_keeps_the_open_one_and_clears_the_thread(page, base_url):
    collection_with_document(page, base_url)
    upload_and_wait(page, "nisan.md", "# Nisan\n\nNisan belgesi kısa bir metin.\n")
    _open_document(page, "ocak.md")
    _ask(page)
    expect(_turns(page)).to_have_count(1)

    page.get_by_role("button", name="nisan.md belgesini sil").click()
    page.get_by_role("button", name="Evet, sil").click()
    expect(page.locator("#document-list li").filter(has_text="nisan.md")).to_have_count(0)
    expect(_turns(page)).to_have_count(0)
    expect(page.locator("#viewer-title")).to_have_text("ocak.md")
    expect(page.locator("#viewer-empty")).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_with_an_open_document_the_document_scope_sends_only_that_document(page, base_url):
    cid = collection_with_document(page, base_url)
    open_page(page, base_url)
    upload_and_wait(page, "nisan.md", "# Nisan\n\nNisan belgesi kısa bir metin.\n")
    listed = page.request.get(f"{base_url}/api/collections/{cid}/documents").json()
    doc_id = next(item["id"] for item in listed if item["filename"] == "ocak.md")
    _open_document(page, "ocak.md")
    expect(page.locator("#scope-document")).to_be_checked()

    bodies = []

    def record(request):
        if request.method == "POST" and request.url.endswith("/ask"):
            bodies.append(request.post_data_json)

    page.on("request", record)
    _ask(page)
    expect(_turns(page)).to_have_count(1)
    page.locator("#scope-folder").check()
    _ask(page, "Stok modülü performans")
    expect(_turns(page)).to_have_count(2)
    page.locator("#scope-document").check()
    _ask(page, "Stok modülü performans iyileştirmesi")
    expect(_turns(page)).to_have_count(3)

    assert [body.get("doc_id") for body in bodies] == [doc_id, None, doc_id]


@pytest.mark.e2e
def test_at_800px_the_tabs_show_one_pane_at_a_time(make_page, base_url):
    page = make_page(width=800, height=900)
    open_page(page, base_url)
    expect(page.locator("#pane-tabs")).to_be_visible()
    expect(page.locator("#pane-documents")).to_be_visible()
    expect(page.locator("#pane-chat")).to_be_hidden()
    expect(page.locator("#pane-viewer")).to_be_hidden()
    page.locator("#tab-chat").click()
    expect(page.locator("#pane-chat")).to_be_visible()
    expect(page.locator("#pane-documents")).to_be_hidden()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth") is True


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_a_missing_document_closes_the_viewer_and_reloads_the_list(page, base_url):
    # main.js passes `documents` to the ask actions: a scoped question that finds no document
    # closes the open viewer and asks the server for the document list again.
    cid = collection_with_document(page, base_url)
    _open_document(page, "ocak.md")
    expect(page.locator("#viewer-title")).to_have_text("ocak.md")
    expect(page.locator("#scope-document")).to_be_checked()
    page.route(
        f"**/api/collections/{cid}/ask",
        lambda route: route.fulfill(status=404, json={"detail": "document_not_found"}),
    )

    with page.expect_request(
        lambda request: (
            request.method == "GET" and request.url.endswith(f"/api/collections/{cid}/documents")
        )
    ):
        _ask(page)

    expect(page.locator("#viewer-empty")).to_be_visible()
    expect(page.locator("#viewer-title")).to_have_text("Belge")
    expect(page.locator("#viewer-toolbar")).to_be_hidden()


@pytest.mark.e2e
@pytest.mark.usefixtures("fast_job_polling")
def test_a_replaced_open_document_returns_the_viewer_to_empty(page, base_url):
    # A re-upload replaces an old document with a new row. The list the page loads next no longer
    # has the open document's id, so the viewer must return to its empty state; the new row with
    # the same name is listed and can be opened.
    cid = collection_with_document(page, base_url)
    _open_document(page, "ocak.md")
    expect(page.locator("#viewer-title")).to_have_text("ocak.md")

    def replaced_row(route):
        if route.request.method != "GET":
            route.continue_()
            return
        response = route.fetch()
        rows = response.json()
        for row in rows:
            if row["filename"] == "ocak.md":
                row["id"] = "replaced" + row["id"]
        route.fulfill(response=response, json=rows)

    page.route(f"**/api/collections/{cid}/documents", replaced_row)
    upload_text(page, "diger.md")

    expect(page.locator("#viewer-empty")).to_be_visible()
    expect(page.locator("#viewer-title")).to_have_text("Belge")
    expect(page.get_by_role("button", name="ocak.md belgesini aç")).to_be_visible()
