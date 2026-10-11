"""The colour theme: it follows the system until a choice is made, then the chosen one is kept."""

import pytest
from playwright.sync_api import expect
from ui_helpers import open_page

pytestmark = pytest.mark.e2e

BG = "getComputedStyle(document.body).backgroundColor"
LIGHT = "rgb(245, 246, 248)"
DARK = "rgb(20, 23, 28)"


def _radio(page, name):
    return page.get_by_role("radio", name=name, exact=True)


def test_the_theme_follows_the_system_until_a_choice_is_made(make_page, base_url):
    page = make_page(color_scheme="light")
    open_page(page, base_url)
    expect(_radio(page, "Otomatik")).to_be_checked()
    assert page.evaluate(BG) == LIGHT
    page.emulate_media(color_scheme="dark")
    assert page.evaluate(BG) == DARK


def test_an_explicit_choice_beats_the_system_and_is_remembered(make_page, base_url):
    page = make_page(color_scheme="light")
    open_page(page, base_url)
    _radio(page, "Koyu").check()
    assert page.evaluate(BG) == DARK
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    expect(_radio(page, "Koyu")).to_be_checked()
    assert page.evaluate(BG) == DARK
    _radio(page, "Açık").check()
    page.emulate_media(color_scheme="dark")
    assert page.evaluate(BG) == LIGHT
    _radio(page, "Otomatik").check()
    assert page.evaluate(BG) == DARK


def test_the_remembered_theme_is_applied_before_the_page_script_runs(make_page, base_url):
    page = make_page(color_scheme="light")
    page.add_init_script("try { localStorage.setItem('docrag.theme', 'dark'); } catch (e) {}")
    page.route("**/js/main.js", lambda route: route.abort())
    page.goto(base_url + "/")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert page.evaluate(BG) == DARK


def test_the_switch_works_when_storage_is_blocked(make_page, base_url):
    page = make_page(color_scheme="dark")
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });"
    )
    open_page(page, base_url)
    _radio(page, "Açık").check()
    assert page.evaluate(BG) == LIGHT
