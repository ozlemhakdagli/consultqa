"""The page against the running Docker stack. It creates nothing except that the first visit
creates the default library "Belgelerim", and it uploads nothing. The page opens on "Belgelerim";
test_live_ask_on_an_existing_collection selects another folder through the advanced section and
only reads (it asks one question).

Needs DOCRAG_LIVE_URL (for example http://127.0.0.1:8000). The ask test also needs
DOCRAG_LIVE_COLLECTION (a collection label) and DOCRAG_LIVE_QUESTION.
"""

import os
from pathlib import Path

import pytest
from playwright.sync_api import expect
from ui_helpers import open_advanced

LIVE_URL = os.environ.get("DOCRAG_LIVE_URL")
COLLECTION = os.environ.get("DOCRAG_LIVE_COLLECTION")
QUESTION = os.environ.get("DOCRAG_LIVE_QUESTION")
SHOTS = os.environ.get("DOCRAG_SHOTS_DIR")
# The presets the page offers; the graph LLM preset stays hidden.
OFFERED = {"L2", "L3", "L4", "L5", "L4+llm", "paper"}

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(not LIVE_URL, reason="set DOCRAG_LIVE_URL")]


def test_live_page_agrees_with_the_servers_capabilities(page):
    page.goto(LIVE_URL + "/")
    caps = page.request.get(LIVE_URL + "/api/capabilities").json()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır", timeout=600_000)
    open_advanced(page)
    offered = [p for p in caps["presets"] if p["name"] in OFFERED]
    radios = page.locator("#method-list input[type=radio]")
    expect(radios).to_have_count(len(offered))
    unavailable = [p for p in offered if not p["available"]]
    expect(page.locator("#method-list input[type=radio]:disabled")).to_have_count(len(unavailable))
    if not caps["llm_configured"]:
        expect(page.locator("#method-list")).to_contain_text(
            "Bu özellik bu sistemde henüz açık değil."
        )
    if SHOTS:
        folder = Path(SHOTS)
        folder.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(folder / "live-desktop.png"), full_page=True)


@pytest.mark.skipif(
    not (COLLECTION and QUESTION), reason="set DOCRAG_LIVE_COLLECTION and DOCRAG_LIVE_QUESTION"
)
def test_live_ask_on_an_existing_collection(page):
    page.goto(LIVE_URL + "/")
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır", timeout=600_000)
    open_advanced(page)
    page.locator("#collection-select").select_option(label=COLLECTION)
    page.get_by_label("Sorunuz", exact=True).fill(QUESTION)
    page.get_by_role("button", name="Cevabı bul").click()
    expect(page.locator("#result-title")).to_be_visible(timeout=120_000)
    expect(page.locator(".error-card")).to_have_count(0)
