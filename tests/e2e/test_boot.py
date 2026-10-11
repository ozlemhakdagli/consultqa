"""The page does not jump while it loads, and it still appears when its script fails."""

import pytest
from playwright.sync_api import expect
from ui_helpers import open_page

pytestmark = pytest.mark.e2e


@pytest.mark.parametrize("width", [1280, 390])
def test_the_page_does_not_jump_while_it_loads(make_page, base_url, width):
    page = make_page(width=width, height=800)
    page.add_init_script(
        "window.__shift = 0;"
        "new PerformanceObserver((list) => { for (const e of list.getEntries())"
        " if (!e.hadRecentInput) window.__shift += e.value; })"
        ".observe({ type: 'layout-shift', buffered: true });"
    )
    open_page(page, base_url)
    page.wait_for_timeout(1000)
    assert page.evaluate("window.__shift") <= 0.1
    assert page.evaluate("document.body.classList.contains('booting')") is False


def test_the_page_appears_by_itself_when_its_script_fails(make_page, base_url):
    page = make_page()
    page.route("**/js/main.js", lambda route: route.abort())
    page.goto(base_url + "/")
    expect(page.locator("#step-documents")).to_be_hidden()
    expect(page.locator("#step-documents")).to_be_visible(timeout=5000)
