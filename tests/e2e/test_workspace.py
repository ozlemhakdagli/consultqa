"""End-to-end flows of the document workspace with real PDFs: upload, page buttons, the viewer,
the scope switch, select-and-ask, the tabs at narrow width and the two languages.

The server is ``viewer_url``: its parser reads the PDF text layer (pdfium), so no model is needed.
"""

import re
from pathlib import Path

import pytest
from pdf_fixtures import write_pdf
from playwright.sync_api import expect
from ui_helpers import new_library, open_page, upload_and_wait

pytestmark = pytest.mark.e2e


ASK = "Cevabı bul"
OCAK = "ocak.pdf"
NISAN = "nisan.pdf"
# One distinct sentence per page: the answer of a question is its page's sentence.
OCAK_PAGES = [
    "Sipariş modülü tablo filtreleme özelliği eklendi.",
    "Stok modülü performans iyileştirmesi yapıldı.",
    "Raporlar aylık özet üretir ve arşivlenir.",
]
NISAN_TEXT = "Stok modülü nisan raporu hazırlandı."
# Asked with ocak.pdf open it is answered from ocak.pdf; asked in the whole folder from nisan.pdf.
SCOPE_QUESTION = "Nisan raporu"
NARROW = 800
WIDE = 1280


def _pdf_bytes(tmp_path: Path, name: str, pages: list[str]) -> bytes:
    path = write_pdf(tmp_path / name, [[("p", text)] for text in pages])
    return path.read_bytes()


def _upload_pdf(page, name: str, data: bytes) -> None:
    page.locator("#upload-files").set_input_files(
        [{"name": name, "mimeType": "application/pdf", "buffer": data}]
    )
    expect(page.locator("#document-list li").filter(has_text=name)).to_contain_text(
        "Kullanıma hazır"
    )


def _library_with_pdf(page, base_url: str, tmp_path: Path) -> str:
    """A new folder on the viewer server with the three-page PDF ``ocak.pdf``."""
    cid = new_library(page, base_url)
    open_page(page, base_url)
    _upload_pdf(page, OCAK, _pdf_bytes(tmp_path, OCAK, OCAK_PAGES))
    return cid


def _ask(page, question: str) -> None:
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def _open_document(page, filename: str) -> None:
    page.get_by_role("button", name=f"{filename} belgesini aç").click()


def _turns(page):
    return page.locator("#result section.turn")


def _ask_requests(page) -> list[dict]:
    """The bodies of the question requests the page sends, in order."""
    bodies: list[dict] = []

    def record(request):
        if request.method == "POST" and request.url.endswith("/ask"):
            bodies.append(request.post_data_json)

    page.on("request", record)
    return bodies


@pytest.mark.usefixtures("fast_job_polling")
def test_an_uploaded_pdf_has_an_open_button(page, viewer_url, tmp_path):
    _library_with_pdf(page, viewer_url, tmp_path)
    expect(page.get_by_role("button", name=f"{OCAK} belgesini aç")).to_be_visible()


def test_a_page_button_opens_the_page_with_its_sentence_marked(make_page, viewer_url, tmp_path):
    page = make_page(width=NARROW, height=900, fast_jobs=True)
    _library_with_pdf(page, viewer_url, tmp_path)
    page.locator("#tab-chat").click()
    _ask(page, "Stok modülü performans iyileştirmesi")
    expect(_turns(page)).to_have_count(1)

    expect(page.locator("#tab-viewer")).to_have_attribute("aria-selected", "false")
    expect(page.locator("#pane-viewer")).to_have_attribute("data-pane-active", "false")
    source_button = page.locator(".citation-card .page-button")
    expect(source_button).to_have_text("Sayfa 2")
    source_button.click()

    expect(page.locator("#pane-viewer")).to_have_attribute("data-pane-active", "true")
    expect(page.locator("#tab-viewer")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#viewer-page")).to_have_value("2")
    expect(page.locator(".pdf-page[data-page='2'] .pdf-highlight").first).to_be_visible()
    # The mark may be split over several spans, so the texts of all of them are joined.
    page.wait_for_function(
        """(sentence) => [...document.querySelectorAll('.pdf-page[data-page="2"] .pdf-highlight')]
          .map((node) => node.textContent).join('') === sentence""",
        arg=OCAK_PAGES[1],
    )
    expect(page.locator("#viewer-message")).to_be_hidden()


@pytest.mark.usefixtures("fast_job_polling")
def test_a_related_page_opens_without_a_mark(page, viewer_url, tmp_path):
    _library_with_pdf(page, viewer_url, tmp_path)
    _ask(page, "Sipariş modülü tablo")
    expect(_turns(page)).to_have_count(1)
    source = page.locator(".citation-card .page-button")
    expect(source).to_have_text("Sayfa 1")

    related = page.locator(".related-pages")
    expect(related).to_be_visible()
    expect(related.get_by_role("heading", name="İlgili sayfalar")).to_be_visible()
    # A related page other than the source page: its button opens that page with no mark.
    chip = related.locator(".page-button").filter(has_not_text="Sayfa 1").first
    expect(chip).to_be_visible()
    number = re.search(r"\d+", chip.inner_text()).group(0)

    _open_document(page, OCAK)
    chip.click()

    expect(page.locator("#viewer-page")).to_have_value(number)
    expect(page.locator("#viewer-canvas .pdf-highlight")).to_have_count(0)
    expect(page.locator("#viewer-message")).to_be_hidden()


@pytest.mark.usefixtures("fast_job_polling")
def test_the_scope_switch_limits_the_question_to_the_open_document(page, viewer_url, tmp_path):
    cid = _library_with_pdf(page, viewer_url, tmp_path)
    _upload_pdf(page, NISAN, _pdf_bytes(tmp_path, NISAN, [NISAN_TEXT]))
    listed = page.request.get(f"{viewer_url}/api/collections/{cid}/documents").json()
    ocak_id = next(item["id"] for item in listed if item["filename"] == OCAK)
    _open_document(page, OCAK)
    expect(page.locator("#scope-document")).to_be_checked()
    bodies = _ask_requests(page)

    _ask(page, SCOPE_QUESTION)
    expect(_turns(page)).to_have_count(1)
    expect(_turns(page).nth(0).locator(".turn-scope")).to_have_text(f"{OCAK} içinde")
    expect(_turns(page).nth(0).locator(".citation-card")).to_contain_text(f"Belge: {OCAK}")

    page.locator("#scope-folder").check()
    _ask(page, SCOPE_QUESTION)
    expect(_turns(page)).to_have_count(2)
    expect(_turns(page).nth(1).locator(".turn-scope")).to_have_text("Tüm klasörde")
    expect(_turns(page).nth(1).locator(".citation-card")).to_contain_text(f"Belge: {NISAN}")

    assert [body.get("doc_id") for body in bodies] == [ocak_id, None]


def _open_ocak_and_select_its_first_sentence(page, viewer_url, tmp_path) -> None:
    _library_with_pdf(page, viewer_url, tmp_path)
    _open_document(page, OCAK)
    expect(page.locator("#viewer-toolbar")).to_be_visible()
    # The first page is the one the viewer shows; its sentence is inside the visible area.
    expect(
        page.locator("#viewer-canvas .textLayer span").filter(has_text="Sipariş")
    ).not_to_have_count(0)
    page.evaluate(
        """() => {
          const span = [...document.querySelectorAll('#viewer-canvas .textLayer span')]
            .find((node) => node.textContent.includes('Sipariş'));
          const range = document.createRange();
          range.selectNodeContents(span);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
        }"""
    )


@pytest.mark.usefixtures("fast_job_polling")
def test_at_narrow_width_the_selected_text_opens_the_chat_with_the_question_focused(
    page, viewer_url, tmp_path
):
    page.set_viewport_size({"width": NARROW, "height": 900})
    _open_ocak_and_select_its_first_sentence(page, viewer_url, tmp_path)
    bodies = _ask_requests(page)

    expect(page.locator("#selection-ask")).to_be_visible()
    page.locator("#selection-ask").click()

    # The chat tab is the chosen one, and the question box is shown and holds the text, focused.
    expect(page.locator("#tab-chat")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#question")).to_be_visible()
    expect(page.locator("#question")).to_have_value(OCAK_PAGES[0])
    expect(page.locator("#question")).to_be_focused()
    expect(_turns(page)).to_have_count(0, timeout=1_000)
    assert bodies == []


@pytest.mark.usefixtures("fast_job_polling")
def test_the_selected_text_of_the_viewer_fills_the_question_without_submitting(
    page, viewer_url, tmp_path
):
    _open_ocak_and_select_its_first_sentence(page, viewer_url, tmp_path)
    bodies = _ask_requests(page)

    expect(page.locator("#selection-ask")).to_be_visible()
    page.locator("#selection-ask").click()

    expect(page.locator("#question")).to_have_value(OCAK_PAGES[0])
    expect(page.locator("#selection-ask")).to_be_hidden()
    # A question is sent only by its button: nothing is sent and no turn appears after the draft.
    expect(_turns(page)).to_have_count(0, timeout=1_000)
    assert bodies == []


@pytest.mark.usefixtures("fast_job_polling")
def test_a_text_file_opens_as_text_in_the_viewer(page, viewer_url):
    new_library(page, viewer_url)
    open_page(page, viewer_url)
    upload_and_wait(page, "notlar.md", "# Notlar\n\nNot metni burada.\n")
    _open_document(page, "notlar.md")
    expect(page.locator("#viewer-text")).to_be_visible()
    expect(page.locator("#viewer-text")).to_contain_text("Not metni burada.")
    expect(page.locator("#viewer-canvas")).to_be_hidden()


def test_the_tabs_show_at_narrow_width_and_not_at_wide_width(make_page, viewer_url):
    narrow = make_page(width=NARROW, height=900)
    open_page(narrow, viewer_url)
    expect(narrow.locator("#pane-tabs")).to_be_visible()
    expect(narrow.locator("#tab-viewer")).to_be_visible()

    wide = make_page(width=WIDE, height=900)
    open_page(wide, viewer_url)
    expect(wide.locator("#pane-tabs")).to_be_hidden()
    expect(wide.locator("#pane-documents")).to_be_visible()
    expect(wide.locator("#pane-viewer")).to_be_visible()
    expect(wide.locator("#pane-chat")).to_be_visible()


@pytest.mark.usefixtures("fast_job_polling")
def test_the_labels_follow_the_language_switch(page, viewer_url):
    open_page(page, viewer_url)
    expect(page.locator("#tab-viewer")).to_have_text("Belge")
    expect(page.get_by_text("Bu belgede", exact=True)).to_be_visible()

    page.locator("#language-switch input[value='en']").check()

    expect(page.locator("#tab-viewer")).to_have_text("Document")
    expect(page.get_by_text("In this document", exact=True)).to_be_visible()
    expect(page.locator("#viewer-empty")).to_have_text(
        "Open a document, or press a page button in an answer, to see the source."
    )


def test_a_document_row_shows_its_name_and_status_beside_its_buttons(page, base_url):
    # The row has a name, an Open button and a Delete button. The name and the status must keep a
    # readable width at a wide screen, not be squeezed into a sliver by the buttons.
    open_page(page, base_url)
    new_library(page, base_url)
    upload_and_wait(page, "rapor.txt", "Stok modülü performans iyileştirmesi yapıldı.")
    row = page.locator(".doc-row").filter(has_text="rapor.txt")
    expect(row.locator(".doc-status")).to_have_text(re.compile("Ready|hazır", re.I))
    name_box = row.locator(".doc-main").bounding_box()
    assert name_box is not None and name_box["width"] >= 160, name_box
    page.set_viewport_size({"width": 1280, "height": 800})
    name_box = row.locator(".doc-main").bounding_box()
    assert name_box is not None and name_box["width"] >= 160, name_box
