"""The visible and the accessible text of every page state contains no technical word."""

import pytest
from plain_words import find_forbidden
from playwright.sync_api import expect
from ui_helpers import (
    caps_without_llm,
    collection_with_document,
    new_library,
    open_advanced,
    open_page,
)

pytestmark = pytest.mark.e2e
ASK = "Cevabı bul"
WORDS = """() => {
  const attributes = ['aria-label', 'placeholder', 'title', 'alt'];
  const own = [...document.querySelectorAll('*')]
    .flatMap((node) => attributes.map((name) => node.getAttribute(name)).filter(Boolean));
  return document.body.textContent + ' ' + own.join(' ');
}"""


def _clean(page):
    assert find_forbidden(page.evaluate(WORDS)) == []


def _ask(page, question="Stok modülü"):
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def test_first_visit_and_the_open_advanced_section_are_plain(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    _clean(page)
    open_advanced(page)
    _clean(page)


def test_the_disabled_ai_mode_is_plain(page, base_url):
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    open_advanced(page)
    _clean(page)


@pytest.mark.usefixtures("fast_job_polling")
def test_answer_not_found_and_error_states_are_plain(page, base_url):
    collection_with_document(page, base_url)
    _ask(page)
    expect(page.locator(".result-title")).to_be_visible()
    open_advanced(page)
    _clean(page)
    page.route(
        "**/api/collections/*/ask",
        lambda r: r.fulfill(
            json={
                "answer": None,
                "citations": [],
                "trace": [],
                "preset": "L2",
                "latency_ms": 1.0,
            }
        ),
    )
    _ask(page, "Bilinmeyen")
    expect(page.locator(".notfound-card")).to_be_visible()
    _clean(page)
    page.unroute("**/api/collections/*/ask")
    page.route(
        "**/api/collections/*/ask",
        lambda r: r.fulfill(status=503, json={"detail": "vector_store_unavailable"}),
    )
    _ask(page)
    expect(page.locator(".error-card")).to_be_visible()
    _clean(page)


@pytest.mark.usefixtures("fast_job_polling")
def test_upload_rows_and_failures_are_plain(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    page.locator("#upload-files").set_input_files(
        [
            {"name": "x.exe", "mimeType": "application/octet-stream", "buffer": b"MZ"},
            {"name": "bos.txt", "mimeType": "text/plain", "buffer": b"  \n"},
        ]
    )
    expect(page.locator("#document-list li")).to_have_count(2)
    _clean(page)


@pytest.mark.usefixtures("fast_job_polling")
def test_the_theme_switch_the_notice_and_the_marked_answer_are_plain(page, base_url):
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    collection_with_document(page, base_url)
    _ask(page)
    expect(page.locator(".answer-card")).to_be_visible()
    expect(page.locator("#llm-notice")).to_be_visible()
    _clean(page)
