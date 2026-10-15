"""An English document, asked in English, answered and cited in English, on a fresh server."""

import pytest
from playwright.sync_api import expect
from ui_helpers import open_page, upload_and_wait

pytestmark = pytest.mark.e2e

ENGLISH = (
    "# Shipping\n\nShipping takes five working days.\n\n"
    "# Warranty\n\nThe warranty covers parts for two years.\n\n"
    "# Invoices\n\nInvoices are paid within 30 days of receipt.\n"
)
QUESTION = "How many years does the warranty cover?"
NOTE = (
    "This answer was taken from this sentence in the document. The answer may be short; "
    "see the source text for the full context."
)


def _ask(page, question: str = QUESTION) -> None:
    page.get_by_label("Your question", exact=True).fill(question)
    page.get_by_role("button", name="Find the answer").click()


def test_an_english_document_is_uploaded_asked_and_cited_in_english(make_page, fresh_server):
    page = make_page(locale="en-US", fast_jobs=True)
    open_page(page, fresh_server)
    upload_and_wait(page, "policy.md", ENGLISH, "en")
    _ask(page)
    expect(page.locator(".result-title")).to_have_text("The warranty covers parts for two years.")
    expect(page.locator(".answer-card .note")).to_have_text(NOTE)
    expect(page.locator(".citation-card").first).to_contain_text("Document: policy.md")
    expect(page.locator(".citation-card").first).to_contain_text("Section: Warranty")
    expect(page.locator(".citation-card").first).to_contain_text("Text in the document")
    expect(page.locator(".citation-card").first.locator("mark.source-sentence")).to_have_text(
        "The warranty covers parts for two years."
    )
    expect(page.locator(".citation-card").first.locator("mark strong.source-answer")).to_have_text(
        "The warranty covers parts for two years."
    )


def test_an_unanswerable_english_question_shows_the_english_not_found_card(make_page, fresh_server):
    page = make_page(locale="en-US", fast_jobs=True)
    open_page(page, fresh_server)
    upload_and_wait(page, "policy.md", ENGLISH, "en")
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(
            json={"answer": None, "citations": [], "trace": [], "preset": "L2", "latency_ms": 1.0}
        ),
    )
    _ask(page)
    card = page.locator(".notfound-card")
    expect(card).to_contain_text(
        "The answer to this question is not in the documents you uploaded."
    )
    expect(card).to_contain_text(
        "Try writing your question closer to the words used in the document."
    )


def test_english_errors_and_upload_failures_are_in_english(make_page, fresh_server):
    page = make_page(locale="en-US", fast_jobs=True)
    open_page(page, fresh_server)
    page.locator("#upload-files").set_input_files(
        [
            {"name": "x.exe", "mimeType": "application/octet-stream", "buffer": b"MZ"},
            {"name": "bos.txt", "mimeType": "text/plain", "buffer": b""},
        ]
    )
    rows = page.locator("#document-list li")
    expect(rows.filter(has_text="x.exe")).to_contain_text(
        "Could not be read: This file type is not supported. Add a PDF or a text file."
    )
    expect(rows.filter(has_text="bos.txt")).to_contain_text("Could not be read: The file is empty.")
    upload_and_wait(page, "policy.md", ENGLISH, "en")
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(status=503, json={"detail": "vector_store_unavailable"}),
    )
    _ask(page)
    card = page.locator(".error-card")
    expect(card).to_contain_text("Something went wrong. Please try again.")
    expect(card).to_contain_text(
        "The part of the app that stores your documents cannot be reached right now. "
        "Try again in a few seconds."
    )


@pytest.mark.parametrize(("width", "height"), [(390, 844), (360, 740)])
def test_the_english_page_fits_a_phone(make_page, fresh_server, width, height):
    page = make_page(width=width, height=height, locale="en-US")
    open_page(page, fresh_server)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = page.get_by_text("Choose files", exact=True).bounding_box()
    assert box is not None and box["y"] + box["height"] <= height
