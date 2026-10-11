"""The page must not jump while a question is asked or answered (the owner's "scrolls up and down")."""

import pytest
from playwright.sync_api import expect
from ui_helpers import collection_with_document

pytestmark = pytest.mark.e2e

ASK = "Cevabı bul"
DOC = (
    "# Stok\n\n"
    + " ".join(f"Stok modülü {n}. maddede performans iyileştirmesi yapıldı." for n in range(1, 5))
    + "\n"
)


def _click_with_mouse(page, locator):
    """click() scrolls the target into view first, which would hide the jump under test."""
    box = locator.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _answered_page(make_page, base_url, width, height):
    page = make_page(width=width, height=height)
    collection_with_document(page, base_url, content=DOC)
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#result .answer-card")).to_be_visible()
    return page


@pytest.mark.parametrize(("width", "height"), [(1280, 700), (390, 800)])
def test_asking_again_never_moves_the_page_up(make_page, base_url, width, height):
    page = _answered_page(make_page, base_url, width, height)
    page.evaluate("document.getElementById('ask-submit').scrollIntoView({block: 'start'})")
    before = page.evaluate("window.scrollY")
    assert before > 0
    held = []
    page.route("**/api/collections/*/ask", lambda route: held.append(route))
    _click_with_mouse(page, page.get_by_role("button", name=ASK))
    for _ in range(50):
        if held:
            break
        page.wait_for_timeout(100)
    assert len(held) == 1
    page.wait_for_timeout(300)
    assert page.evaluate("window.scrollY") == before  # nothing collapsed
    expect(page.locator("#result .answer-card")).to_be_visible()  # the old answer stays
    expect(page.locator("#result-loading")).to_have_text(
        "Belgelerinizde cevap aranıyor… Bu birkaç saniye sürebilir."
    )
    held[0].continue_()
    page.unroute("**/api/collections/*/ask")
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()
    assert page.evaluate("window.scrollY") >= before - 1


def test_a_new_answer_is_brought_into_view_on_a_phone(make_page, base_url):
    page = _answered_page(make_page, base_url, 390, 800)
    page.evaluate("document.getElementById('ask-submit').scrollIntoView({block: 'end'})")
    page.get_by_label("Sorunuz", exact=True).fill("performans")
    _click_with_mouse(page, page.get_by_role("button", name=ASK))
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()
    expect(page.locator("#result-title")).to_be_in_viewport()
