import re

import pytest
from playwright.sync_api import expect
from ui_helpers import collection_with_document, open_page

pytestmark = pytest.mark.e2e


def test_every_control_has_an_accessible_name(page, base_url):
    collection_with_document(page, base_url)
    snapshot = page.locator("body").aria_snapshot()
    unnamed = re.findall(
        r'^\s*- (?:textbox|button|combobox|radio|checkbox)\b(?! ")[^\n]*', snapshot, re.M
    )
    assert unnamed == [], unnamed
    for name in ("Sorunuz", "Çalışılacak koleksiyon", "Yeni koleksiyon adı", "Yüklenecek dosyalar"):
        assert f'"{name}"' in snapshot, name


def test_the_ask_form_works_with_the_keyboard_alone(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_label("Sorunuz").focus()
    page.keyboard.type("Stok modülü")
    for _ in range(15):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "ask-submit":
            break
    else:
        pytest.fail("the submit button cannot be reached with Tab")
    page.keyboard.press("Enter")
    expect(page.locator("#result-title")).to_be_focused()


# Review Focus 5
def test_no_horizontal_scroll_on_a_phone(make_page, base_url):
    page = make_page(width=360, height=740)
    long_name = "x" * 100 + ".md"
    collection_with_document(
        page,
        base_url,
        filename=long_name,
        content="# " + "y" * 120 + "\n\n" + "z" * 150 + " Stok.\n",
    )
    page.get_by_label("Sorunuz").fill("Stok")
    page.get_by_role("button", name="Cevabı bul").click()
    expect(page.locator("#result-title")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_wide_screens_use_two_columns_and_phones_stack_the_steps(make_page, base_url):
    wide = make_page(width=1280, height=900)
    open_page(wide, base_url)
    left, right = (
        wide.locator("#step-collection").bounding_box(),
        wide.locator("#step-ask").bounding_box(),
    )
    assert right["x"] >= left["x"] + left["width"]
    narrow = make_page(width=390, height=844)
    open_page(narrow, base_url)
    top, bottom = (
        narrow.locator("#step-collection").bounding_box(),
        narrow.locator("#step-ask").bounding_box(),
    )
    assert bottom["y"] >= top["y"] + top["height"]


def test_dark_scheme_uses_the_dark_tokens(make_page, base_url):
    page = make_page(color_scheme="dark")
    open_page(page, base_url)
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(20, 23, 28)"
