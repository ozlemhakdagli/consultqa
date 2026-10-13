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


def test_the_page_boots_with_its_three_panes_and_no_console_errors(page, base_url):
    # make_page fails the test on any console or page error; the panes must exist after boot.
    open_page(page, base_url)
    # At 1280 px the three panes are shown side by side and the tab row is hidden.
    for pane in ("pane-documents", "pane-viewer", "pane-chat"):
        expect(page.locator(f"#{pane}")).to_be_visible()
    expect(page.locator("#pane-tabs")).to_have_count(1)
    assert page.evaluate("document.body.classList.contains('booting')") is False


def test_a_workspace_view_that_cannot_mount_leaves_the_page_and_the_language_working(
    browser, base_url
):
    # A page that lacks one element of the pane view: that view throws while it mounts. The page
    # must still show, and the theme and language switches, mounted before, must still work.
    context = browser.new_context(locale="tr-TR", timezone_id="Europe/Istanbul")
    page = context.new_page()
    page.set_default_timeout(10_000)
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def without_pane_tabs(route):
        response = route.fetch()
        body = response.text().replace('id="pane-tabs"', 'id="pane-tabs-missing"')
        assert body != response.text()
        route.fulfill(status=200, content_type="text/html; charset=utf-8", body=body)

    page.route(base_url + "/", without_pane_tabs)
    try:
        page.goto(base_url + "/")
        expect(page.locator("#language-switch")).to_be_visible()
        assert page.evaluate("document.body.classList.contains('booting')") is False
        for _ in range(50):
            if errors:
                break
            page.wait_for_timeout(100)
        assert any("missing element #pane-tabs" in message for message in errors), errors
        page.get_by_role("radio", name="English", exact=True).check()
        expect(page.locator("h1")).to_have_text("Document Q&A")
    finally:
        context.close()


def test_the_page_appears_by_itself_when_its_script_fails(make_page, base_url):
    page = make_page()
    page.route("**/js/main.js", lambda route: route.abort())
    page.goto(base_url + "/")
    expect(page.locator("#step-documents")).to_be_hidden()
    expect(page.locator("#step-documents")).to_be_visible(timeout=5000)
