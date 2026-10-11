"""The answer view: the whole source passage, the answer's sentence marked, and plain notes."""

import pytest
from playwright.sync_api import expect
from ui_helpers import caps_without_llm, choose_method, collection_with_document, open_page

pytestmark = pytest.mark.e2e

ASK = "Cevabı bul"
PASSAGE = (
    "Birinci satırda genel bilgi verilir. Stok modülü performans iyileştirmesi yapıldı. "
    "Son cümle burada biter."
)
ANSWER = "performans iyileştirmesi yapıldı"
NOTE_EXTRACTIVE = "Bu cevap belgedeki bu cümleden alındı. Cevap kısa olabilir; tam bağlam için kaynak metnine bakın."
NOTE_NO_MARK = "Bu cevap aşağıdaki kaynaktan alındı. Cevap kısa olabilir; tam bağlam için kaynak metnine bakın."


def _mock_answer(page, answer, text=PASSAGE):
    body = {
        "answer": answer,
        "trace": [],
        "preset": "L2",
        "latency_ms": 1.0,
        "citations": [
            {
                "number": 1,
                "chunk_id": "c",
                "doc_id": "yok",
                "heading_path": ["Stok"],
                "text": text,
            }
        ],
    }
    page.route("**/api/collections/*/ask", lambda route: route.fulfill(json=body))


def _ask(page, question="Stok modülü"):
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def test_the_source_is_shown_in_full_with_the_answer_sentence_marked(page, base_url):
    collection_with_document(page, base_url)
    _mock_answer(page, ANSWER)
    _ask(page)
    expect(page.locator("#result-title")).to_have_text(ANSWER)
    expect(page.locator(".answer-card .note")).to_have_text(NOTE_EXTRACTIVE)
    expect(page.locator("#cite-1")).to_contain_text("Bölüm: Stok")
    expect(page.locator("#cite-1")).to_contain_text("Belgedeki metin")
    expect(page.locator("#cite-1-text")).to_be_visible()
    expect(page.locator("#cite-1-text")).to_have_text(PASSAGE)
    expect(page.locator("#cite-1-text mark.source-sentence")).to_have_text(
        "Stok modülü performans iyileştirmesi yapıldı."
    )
    expect(page.locator("#cite-1-text mark strong.source-answer")).to_have_text(ANSWER)
    expect(page.get_by_role("button", name="Kaynağın metnini göster")).to_have_count(0)


def test_an_answer_that_is_not_inside_the_passage_marks_nothing_and_claims_nothing(page, base_url):
    collection_with_document(page, base_url)
    _mock_answer(page, "başka bir ifade")
    _ask(page)
    expect(page.locator("#cite-1-text")).to_be_visible()
    expect(page.locator("#cite-1-text")).to_have_text(PASSAGE)
    expect(page.locator("#cite-1-text mark")).to_have_count(0)
    expect(page.locator(".answer-card .note")).to_have_text(NOTE_NO_MARK)


def test_the_ai_answer_shows_its_sources_open_and_marks_nothing(page, base_url):
    collection_with_document(page, base_url)
    choose_method(page, "Yapay zekâ ile yazılmış cevap")
    _ask(page)
    expect(page.locator(".answer-card .note")).to_contain_text("Bu cevabı yapay zekâ yazdı.")
    expect(page.locator("#cite-1-text")).to_be_visible()
    expect(page.locator(".source-passage mark")).to_have_count(0)
    page.get_by_role("button", name="1. kaynağa git").click()
    expect(page.locator("#cite-1")).to_be_focused()
    expect(page.locator("#cite-1")).to_have_attribute("data-active", "true")


def test_the_passage_text_is_never_parsed_as_html(page, base_url):
    collection_with_document(page, base_url)
    text = "Önce bir cümle. Bu <script>window.__pwned = 1</script> içerir. Sonra bir cümle."
    _mock_answer(page, "<script>window.__pwned = 1</script>", text=text)
    _ask(page)
    expect(page.locator("#cite-1-text mark strong")).to_have_text(
        "<script>window.__pwned = 1</script>"
    )
    assert page.evaluate("window.__pwned") is None


def test_the_notice_says_when_the_ai_mode_is_not_configured(page, base_url):
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    expect(page.locator("#llm-notice")).to_be_visible()
    expect(page.locator("#llm-notice")).to_have_text(
        "Yapay zekâ ile cevap yazma bu sistemde kapalı; "
        "bu yüzden cevaplar belgeden alınan kısa kesitlerdir."
    )


def test_no_notice_when_the_ai_mode_is_configured(page, base_url):
    open_page(page, base_url)
    expect(page.locator("#llm-notice")).to_be_hidden()
