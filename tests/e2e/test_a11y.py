import re

import pytest
from playwright.sync_api import expect
from ui_helpers import collection_with_document, new_library, open_advanced, open_page

pytestmark = pytest.mark.e2e
ASK_BUTTON = "Cevabı bul"


def _chat_tab_on_a_narrow_screen(page):
    """Below 1000 px only one pane shows; the chat pane is chosen with its tab, as a person would."""
    if page.viewport_size["width"] < 1000:
        page.locator("#tab-chat").click()


@pytest.mark.usefixtures("fast_job_polling")
def test_every_control_has_an_accessible_name(page, base_url):
    collection_with_document(page, base_url)
    open_advanced(page)
    snapshot = page.locator("body").aria_snapshot()
    unnamed = re.findall(
        r'^\s*- (?:textbox|button|combobox|radio|checkbox)\b(?! ")[^\n]*', snapshot, re.M
    )
    assert unnamed == [], unnamed
    for name in ("Sorunuz", "Kullanılan klasör", "Yeni klasör adı", "Dosya seçin"):
        assert f'"{name}"' in snapshot, name


@pytest.mark.usefixtures("fast_job_polling")
def test_the_ask_form_works_with_the_keyboard_alone(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_label("Sorunuz", exact=True).focus()
    page.keyboard.type("Stok modülü")
    for _ in range(15):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "ask-submit":
            break
    else:
        pytest.fail("the submit button cannot be reached with Tab")
    page.keyboard.press("Enter")
    expect(page.locator(".result-title")).to_be_focused()


# Review Focus 5
def test_no_horizontal_scroll_on_a_phone(make_page, base_url):
    page = make_page(width=360, height=740, fast_jobs=True)
    long_name = "x" * 100 + ".md"
    collection_with_document(
        page,
        base_url,
        filename=long_name,
        content="# " + "y" * 120 + "\n\n" + "z" * 150 + " Stok.\n",
    )
    # The long file name is in the documents tab, which is the one shown first.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    _chat_tab_on_a_narrow_screen(page)
    page.get_by_label("Sorunuz", exact=True).fill("Stok")
    page.get_by_role("button", name="Cevabı bul").click()
    expect(page.locator(".result-title")).to_be_visible()
    # The answer area is its own scroller below 1000 px: it must not scroll sideways either.
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    assert page.locator("#step-answer").evaluate("el => el.scrollWidth <= el.clientWidth")
    page.locator("#tab-viewer").click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_the_first_screen_on_a_phone_shows_what_to_do(make_page, base_url):
    page = make_page(width=390, height=844)
    new_library(page, base_url)
    open_page(page, base_url)
    button = page.get_by_text("Dosya seçin", exact=True).bounding_box()
    assert button["y"] + button["height"] <= 844  # visible without scrolling


@pytest.mark.usefixtures("fast_job_polling")
def test_touch_targets_are_at_least_44_pixels_high(page, base_url):
    collection_with_document(page, base_url)
    for locator in (
        page.get_by_role("button", name=ASK_BUTTON),
        page.get_by_text("Dosya seçin", exact=True),
        page.locator("#example-list button").first,
    ):
        assert locator.bounding_box()["height"] >= 44


def test_dark_scheme_uses_the_dark_tokens(make_page, base_url):
    page = make_page(color_scheme="dark")
    open_page(page, base_url)
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(20, 23, 28)"
