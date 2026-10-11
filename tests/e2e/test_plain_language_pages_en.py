"""The visible and the accessible text of every English page state contains no technical word."""

import pytest
from plain_words import find_forbidden_en
from playwright.sync_api import expect
from ui_helpers import caps_without_llm, new_library, open_advanced, open_page, upload_and_wait

pytestmark = pytest.mark.e2e
ENGLISH = (
    "# Shipping\n\nShipping takes five working days.\n\n"
    "# Warranty\n\nThe warranty covers parts for two years.\n\n"
    "# Invoices\n\nInvoices are paid within 30 days of receipt.\n"
)
QUESTION = "How many years does the warranty cover?"
WORDS = """() => {
  const attributes = ['aria-label', 'placeholder', 'title', 'alt'];
  const own = [...document.querySelectorAll('*')]
    .flatMap((node) => attributes.map((name) => node.getAttribute(name)).filter(Boolean));
  return document.body.textContent + ' ' + own.join(' ');
}"""


def _clean(page):
    assert find_forbidden_en(page.evaluate(WORDS)) == []


def _ask(page, question=QUESTION):
    page.get_by_label("Your question", exact=True).fill(question)
    page.get_by_role("button", name="Find the answer").click()


def test_first_visit_and_the_open_advanced_section_are_plain_in_english(make_page, base_url):
    page = make_page(locale="en-US")
    new_library(page, base_url)
    open_page(page, base_url)
    _clean(page)
    open_advanced(page)
    _clean(page)


def test_the_disabled_ai_mode_and_the_notice_are_plain_in_english(make_page, base_url):
    page = make_page(locale="en-US")
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    open_advanced(page)
    _clean(page)
    expect(page.locator("#llm-notice")).to_be_visible()
    _clean(page)


def test_answer_not_found_and_error_states_are_plain_in_english(make_page, base_url):
    page = make_page(locale="en-US", fast_jobs=True)
    new_library(page, base_url)
    open_page(page, base_url)
    upload_and_wait(page, "policy.md", ENGLISH, "en")
    _ask(page)
    expect(page.locator("#result-title")).to_be_visible()
    open_advanced(page)
    _clean(page)
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(
            json={"answer": None, "citations": [], "trace": [], "preset": "L2", "latency_ms": 1.0}
        ),
    )
    _ask(page, "Unknown topic")
    expect(page.locator(".notfound-card")).to_be_visible()
    _clean(page)
    page.unroute("**/api/collections/*/ask")
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(status=503, json={"detail": "vector_store_unavailable"}),
    )
    _ask(page)
    expect(page.locator(".error-card")).to_be_visible()
    _clean(page)


def test_upload_rows_and_failures_are_plain_in_english(make_page, base_url):
    page = make_page(locale="en-US", fast_jobs=True)
    new_library(page, base_url)
    open_page(page, base_url)
    page.locator("#upload-files").set_input_files(
        [
            {"name": "x.exe", "mimeType": "application/octet-stream", "buffer": b"MZ"},
            {"name": "bos.txt", "mimeType": "text/plain", "buffer": b""},
        ]
    )
    expect(page.locator("#document-list li")).to_have_count(2)
    _clean(page)
