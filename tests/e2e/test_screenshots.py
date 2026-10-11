"""Screenshots of every page state at phone and desktop width, for the visual review.

Runs only when DOCRAG_SHOTS_DIR names a folder; the files are named {device}-{n}-{state}.png.
"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_helpers import (
    caps_without_llm,
    choose_method,
    collection_with_document,
    new_library,
    open_advanced,
    open_page,
    upload_text,
)

SHOTS = os.environ.get("DOCRAG_SHOTS_DIR")
DEVICES = {"phone": (390, 844), "desktop": (1280, 900)}
ASK = "Cevabı bul"
EXAMPLE = "Garanti süresi kaç yıldır?"
AI_METHOD = "Yapay zekâ ile yazılmış cevap"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not SHOTS, reason="set DOCRAG_SHOTS_DIR to save the screenshots"),
]


def _shooter(device: str) -> Callable[..., None]:
    """Return a shot function that numbers the files of one device in call order."""
    folder = Path(SHOTS)
    folder.mkdir(parents=True, exist_ok=True)
    count = {"n": 0}

    def shot(page: Page, state: str, full_page: bool = True) -> None:
        count["n"] += 1
        name = f"{device}-{count['n']}-{state}.png"
        page.screenshot(path=str(folder / name), full_page=full_page)

    return shot


def _ask(page: Page, question: str, method: str | None = None) -> None:
    if method:
        choose_method(page, method)
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


@pytest.mark.parametrize("device", DEVICES)
def test_screenshots_of_every_state(device, make_page, base_url):
    width, height = DEVICES[device]
    shot = _shooter(device)
    page = make_page(width=width, height=height)
    real = page.request.get(base_url + "/api/capabilities").json()

    # 1. what a person sees before scrolling
    new_library(page, base_url)
    open_page(page, base_url)
    shot(page, "first-screen", full_page=False)

    # 2. the same page, from top to bottom
    shot(page, "first-visit")

    # 3. the system is still opening
    page.route("**/api/capabilities", lambda route: route.fulfill(json={**real, "ready": False}))
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem açılıyor")
    shot(page, "system-opening")
    page.unroute("**/api/capabilities")
    open_page(page, base_url)

    # 4. a file is being sent: the request is held until the shot is taken
    held = []

    def hold(route):
        if route.request.method == "POST":
            held.append(route)
        else:
            route.fallback()

    page.route("**/api/collections/*/documents", hold)
    upload_text(page, "ocak.md")
    row = page.locator("#document-list li").filter(has_text="ocak.md")
    expect(row.locator(".doc-status")).to_have_text("Yükleniyor…")
    shot(page, "sending")

    # 5. the server is preparing the document: the job stays at its longest stage
    page.route(
        "**/api/jobs/*",
        lambda route: route.fulfill(
            json={"state": "embedding", "error": None, "document_id": "pending"}
        ),
    )
    held[0].continue_()
    page.unroute("**/api/collections/*/documents")
    expect(row.locator(".doc-status")).to_have_text("Hazırlanıyor…")
    shot(page, "preparing")
    page.unroute("**/api/jobs/*")

    # 6. the document is ready
    expect(row.locator(".doc-status")).to_have_text("Kullanıma hazır", timeout=30000)
    shot(page, "ready")

    # 7. a file of the wrong type is refused and can be dismissed
    page.locator("#upload-files").set_input_files(
        [{"name": "x.exe", "mimeType": "application/octet-stream", "buffer": b"MZ"}]
    )
    refused = page.locator("#document-list li").filter(has_text="x.exe")
    expect(refused.locator(".doc-status")).to_contain_text("Okunamadı:")
    shot(page, "failed-upload")
    refused.get_by_role("button", name="x.exe satırını kapat").click()

    # 8. an example question fills the box
    page.get_by_role("button", name=EXAMPLE).click()
    expect(page.get_by_label("Sorunuz", exact=True)).to_have_value(EXAMPLE)
    shot(page, "question-typed")

    # 9. the answer, with its source closed
    _ask(page, "Stok modülü")
    expect(page.locator("#result-title")).to_be_visible()
    shot(page, "answer")

    # 10. the source passage opened
    page.locator("#cite-1").get_by_role("button", name="Kaynağın metnini göster").click()
    shot(page, "answer-source-open")

    # 11. an answer written by the AI mode, scrolled to its sources
    _ask(page, "Stok modülü", method=AI_METHOD)
    expect(page.locator(".answer-card .meta")).to_have_text(f"Kullanılan yöntem: {AI_METHOD}")
    page.locator("#cite-1").scroll_into_view_if_needed()
    shot(page, "answer-ai")

    # 12. nothing in the documents answers the question
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(
            json={"answer": None, "citations": [], "trace": [], "preset": "L2", "latency_ms": 1}
        ),
    )
    _ask(page, "Bilinmeyen")
    expect(page.locator(".notfound-card")).to_be_visible()
    shot(page, "not-found")
    page.unroute("**/api/collections/*/ask")

    # 13. the store is unreachable while answering
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(status=503, json={"detail": "vector_store_unavailable"}),
    )
    _ask(page, "Stok modülü")
    expect(page.locator(".error-card")).to_be_visible()
    shot(page, "error")
    page.unroute("**/api/collections/*/ask")

    # 14. no AI is configured: the AI mode is shown disabled, with the reason
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    open_advanced(page)
    shot(page, "advanced-open")
    page.unroute("**/api/capabilities")

    # 15. the dark colour scheme, after an answer
    dark = make_page(width=width, height=height, color_scheme="dark")
    collection_with_document(dark, base_url)
    _ask(dark, "Stok modülü")
    expect(dark.locator("#result-title")).to_be_visible()
    shot(dark, "dark")
