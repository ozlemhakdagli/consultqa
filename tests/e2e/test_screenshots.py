"""Full-page screenshots of every page state, for the visual review.

Runs only when DOCRAG_SHOTS_DIR names an existing folder; the files are named {device}-{n}-{state}.
"""

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from ui_helpers import (
    caps_without_llm,
    create_collection,
    mock_empty_collections,
    open_page,
    unique,
    upload_text,
)

SHOTS = os.environ.get("DOCRAG_SHOTS_DIR")
DEVICES = {"phone": (390, 844), "desktop": (1280, 900)}
ASK = "Cevabı bul"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not SHOTS, reason="set DOCRAG_SHOTS_DIR to save the screenshots"),
]


def _shooter(device: str) -> Callable[[Page, str], None]:
    """Return a shot function that numbers the files of one device in call order."""
    folder = Path(SHOTS)
    folder.mkdir(parents=True, exist_ok=True)
    count = {"n": 0}

    def shot(page: Page, state: str) -> None:
        count["n"] += 1
        page.screenshot(path=str(folder / f"{device}-{count['n']}-{state}.png"), full_page=True)

    return shot


def _ask(page: Page, question: str, method: str | None = None) -> None:
    if method:
        page.get_by_role("radio", name=method, exact=True).check()
    page.get_by_label("Sorunuz").fill(question)
    page.get_by_role("button", name=ASK).click()


@pytest.mark.parametrize("device", list(DEVICES))
def test_every_state_is_captured(make_page, base_url, device):
    width, height = DEVICES[device]
    page = make_page(width=width, height=height)
    shot = _shooter(device)
    real = page.request.get(base_url + "/api/capabilities").json()

    # 1. first visit: no collections yet
    mock_empty_collections(page)
    open_page(page, base_url)
    shot(page, "first-visit")
    page.unroute("**/api/collections")

    # 2. the models are still loading
    page.route("**/api/capabilities", lambda route: route.fulfill(json={**real, "ready": False}))
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Modeller yükleniyor")
    shot(page, "loading")
    page.unroute("**/api/capabilities")
    open_page(page, base_url)

    # 3. a collection is created
    name = unique("Ekran")
    create_collection(page, name)
    shot(page, "collection-created")

    # 4. an upload in progress: the job stays at the longest stage while the shot is taken
    page.route(
        "**/api/jobs/*",
        lambda route: route.fulfill(
            json={"state": "embedding", "error": None, "document_id": "pending"}
        ),
    )
    upload_text(page, "ocak.md")
    row = page.locator("#upload-list li").filter(has_text="ocak.md")
    expect(row).to_contain_text("aranabilir hale getiriliyor")
    shot(page, "upload-progress")
    page.unroute("**/api/jobs/*")
    expect(row).to_contain_text("Hazır.", timeout=30000)

    # 5. the document list
    expect(page.locator("#document-list li")).to_have_count(1)
    shot(page, "documents")

    # 6. an answer with the standard method
    _ask(page, "Stok modülü")
    expect(page.locator("#result-title")).to_be_visible()
    shot(page, "answer")

    # 7. an answer written by the LLM method, scrolled to its sources
    _ask(page, "Stok modülü", method="Dil modeli ile yaz (başlık bağlamlı)")
    expect(page.locator(".answer-card .note")).to_contain_text("Bu cevabı bir dil modeli yazdı.")
    page.locator("#result .sources").scroll_into_view_if_needed()
    shot(page, "answer-llm")

    # 8. the answer is not in the documents
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(
            json={
                "answer": None,
                "citations": [],
                "trace": [],
                "preset": "L4+llm",
                "latency_ms": 12.0,
            }
        ),
    )
    _ask(page, "Bilinmeyen bir konu")
    expect(page.locator("#result-title")).to_have_text("Belgelerde bu soruya cevap bulunamadı")
    shot(page, "not-found")
    page.unroute("**/api/collections/*/ask")

    # 9. the LLM is down, with the search details still shown
    trace = [
        {
            "stage": "pool",
            "chunk_id": "c1",
            "rank": 1,
            "score": 0.5,
            "score_type": "rrf",
            "channel": "rrf",
        }
    ]
    page.route(
        "**/api/collections/*/ask",
        lambda route: route.fulfill(status=503, json={"detail": "llm_unavailable", "trace": trace}),
    )
    _ask(page, "Stok modülü")
    expect(page.locator(".error-card")).to_contain_text("Dil modeli şu anda yanıt vermiyor.")
    shot(page, "error")
    page.unroute("**/api/collections/*/ask")

    # 10. no LLM is configured: the LLM methods are shown disabled with the reason
    page.route(
        "**/api/capabilities", lambda route: route.fulfill(json=caps_without_llm(page, base_url))
    )
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    shot(page, "methods-no-llm")
    page.unroute("**/api/capabilities")

    # 11. the dark colour scheme, after an answer
    dark = make_page(width=width, height=height, color_scheme="dark")
    open_page(dark, base_url)
    dark.locator("#collection-select").select_option(label=name)
    _ask(dark, "Stok modülü")
    expect(dark.locator("#result-title")).to_be_visible()
    shot(dark, "dark")
