"""Screenshots of the page states at phone and desktop width, in both colour schemes.

Runs only when CONSULTQA_SHOTS_DIR names a folder; the files are named {device}-{scheme}-{n}-{state}.png.
"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_helpers import (
    caps_without_llm,
    choose_method,
    new_library,
    open_advanced,
    open_page,
    upload_text,
)

SHOTS = os.environ.get("CONSULTQA_SHOTS_DIR")
DEVICES = {"phone": (390, 844), "desktop": (1280, 800)}
SCHEMES = ("light", "dark")
ASK = "Cevabı bul"
AI_METHOD = "Yapay zekâ ile yazılmış cevap"
PASSAGE = (
    "Birinci satırda genel bilgi verilir. Stok modülü performans iyileştirmesi yapıldı. "
    "Son cümle burada biter."
)
MARKED_REPLY = {
    "answer": "performans iyileştirmesi yapıldı",
    "trace": [],
    "preset": "L2",
    "latency_ms": 1.0,
    "citations": [
        {"number": 1, "chunk_id": "c", "doc_id": "yok", "heading_path": ["Stok"], "text": PASSAGE}
    ],
}
NOT_FOUND_REPLY = {"answer": None, "citations": [], "trace": [], "preset": "L2", "latency_ms": 1.0}

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not SHOTS, reason="set CONSULTQA_SHOTS_DIR to save the screenshots"),
]


def _shooter(device: str, scheme: str) -> Callable[..., None]:
    """Return a shot function that numbers the files of one device and scheme in call order."""
    folder = Path(SHOTS)
    folder.mkdir(parents=True, exist_ok=True)
    count = {"n": 0}

    def shot(page: Page, state: str, full_page: bool = True) -> None:
        count["n"] += 1
        name = f"{device}-{scheme}-{count['n']}-{state}.png"
        page.screenshot(path=str(folder / name), full_page=full_page)

    return shot


def _ask(page: Page, question: str, method: str | None = None) -> None:
    if method:
        choose_method(page, method)
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def _reply_with(page: Page, body: dict) -> None:
    page.route("**/api/collections/*/ask", lambda route: route.fulfill(json=body))


def _capabilities_are(page: Page, caps: dict) -> None:
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))


@pytest.mark.parametrize("device", DEVICES)
def test_screenshots_of_every_state(device, make_page, base_url):
    width, height = DEVICES[device]
    for scheme in SCHEMES:
        page = make_page(width=width, height=height, color_scheme=scheme, fast_jobs=True)
        shot = _shooter(device, scheme)

        # 1. what a person sees first, from the top and then the whole page
        new_library(page, base_url)
        open_page(page, base_url)
        shot(page, "first-screen", full_page=False)
        shot(page, "first-visit")

        # 2. a document is ready; the answer shows its source with the sentence marked
        upload_text(page, "ocak.md")
        row = page.locator("#document-list li").filter(has_text="ocak.md")
        expect(row).to_contain_text("Kullanıma hazır")
        _reply_with(page, MARKED_REPLY)
        _ask(page, "Stok modülü")
        expect(page.locator("#cite-1-text mark")).to_be_visible()
        shot(page, "answer-marked")
        page.unroute("**/api/collections/*/ask")

        # 3. the AI mode, from the stub
        _ask(page, "Stok modülü", method=AI_METHOD)
        expect(page.locator(".answer-card .note")).to_contain_text("Bu cevabı yapay zekâ yazdı.")
        shot(page, "answer-ai")

        # 4. nothing in the documents answers the question
        _reply_with(page, NOT_FOUND_REPLY)
        _ask(page, "Bilinmeyen")
        expect(page.locator(".notfound-card")).to_be_visible()
        shot(page, "not-found")
        page.unroute("**/api/collections/*/ask")

        # 5. the search fails
        page.route(
            "**/api/collections/*/ask",
            lambda route: route.fulfill(status=503, json={"detail": "vector_store_unavailable"}),
        )
        _ask(page, "Stok modülü")
        expect(page.locator(".error-card")).to_be_visible()
        shot(page, "error")
        page.unroute("**/api/collections/*/ask")

        # 6. no AI mode is configured: the notice shows in the answer panel
        _capabilities_are(page, caps_without_llm(page, base_url))
        open_page(page, base_url)
        expect(page.locator("#llm-notice")).to_be_visible()
        shot(page, "ai-off")
        page.unroute("**/api/capabilities")

        # 7. the advanced options, open
        open_advanced(page)
        shot(page, "advanced-open")

        # 8. on a light system, the dark theme chosen explicitly
        if scheme == "light":
            page.get_by_role("radio", name="Koyu", exact=True).check()
            shot(page, "theme-forced-dark")
