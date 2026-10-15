"""The layout: three panes side by side on wide screens, one pane at a time under the tabs."""

import pytest
from playwright.sync_api import expect
from ui_helpers import collection_with_document, open_advanced, open_page

pytestmark = pytest.mark.e2e
ASK = "Cevabı bul"
PANES = ("pane-documents", "pane-viewer", "pane-chat")
TABS = (
    ("tab-documents", "pane-documents"),
    ("tab-viewer", "pane-viewer"),
    ("tab-chat", "pane-chat"),
)


def _boxes(page):
    return [page.locator(f"#{name}").bounding_box() for name in PANES]


@pytest.mark.parametrize("width", [1280, 1920])
def test_wide_screens_use_the_full_width_in_three_panes(make_page, base_url, width):
    page = make_page(width=width, height=900)
    open_page(page, base_url)
    expect(page.locator("#pane-tabs")).to_be_hidden()
    assert page.locator(".workspace").bounding_box()["width"] >= 0.9 * width
    docs, viewer, chat = _boxes(page)
    assert viewer["x"] >= docs["x"] + docs["width"]
    assert chat["x"] >= viewer["x"] + viewer["width"]
    assert abs(docs["y"] - viewer["y"]) <= 2
    assert abs(viewer["y"] - chat["y"]) <= 2
    assert chat["x"] + chat["width"] <= width
    # The question form is the dock at the bottom of the chat pane.
    form = page.locator("#ask-form").bounding_box()
    assert form["y"] >= chat["y"] + chat["height"] / 2
    assert form["y"] + form["height"] <= chat["y"] + chat["height"] + 1
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # The advanced options sit inside the documents pane, not over the next one.
    open_advanced(page)
    advanced = page.locator("#advanced").bounding_box()
    assert advanced["x"] >= docs["x"] - 1
    assert advanced["x"] + advanced["width"] <= docs["x"] + docs["width"] + 1


@pytest.mark.parametrize(("width", "height"), [(390, 844), (768, 1024), (991, 800)])
def test_narrow_screens_show_one_pane_under_the_tabs(make_page, base_url, width, height):
    page = make_page(width=width, height=height)
    open_page(page, base_url)
    expect(page.locator("#pane-tabs")).to_be_visible()
    tabs = [page.locator(f"#{tab}").bounding_box() for tab, _ in TABS]
    assert len({round(box["y"]) for box in tabs}) == 1
    assert tabs[0]["x"] < tabs[1]["x"] < tabs[2]["x"]
    for tab, pane in TABS:
        page.locator(f"#{tab}").click()
        expect(page.locator(f"#{pane}")).to_be_visible()
        for _, other in TABS:
            if other != pane:
                expect(page.locator(f"#{other}")).to_be_hidden()
        box = page.locator(f"#{pane}").bounding_box()
        assert box["y"] >= tabs[0]["y"] + tabs[0]["height"] - 1
        # The visible pane and the tab row share one left edge.
        assert abs(box["x"] - tabs[0]["x"]) <= 1
        assert box["width"] >= 0.85 * width
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_the_answer_stays_in_view_beside_the_form(make_page, base_url):
    page = make_page(width=1280, height=600, fast_jobs=True)
    collection_with_document(page, base_url)
    open_advanced(page)
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#result .answer-card")).to_be_visible()
    expect(page.locator("#result .answer-card").last).to_be_in_viewport()
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    # The page does not scroll on a wide screen: the panes fit the window, so the chat pane and
    # its question form stay in view when the answer arrives.
    assert page.evaluate("document.documentElement.scrollHeight <= window.innerHeight")
    assert page.evaluate("window.scrollY") == 0
    chat = page.locator("#pane-chat").bounding_box()
    assert 0 <= chat["y"] and chat["y"] + chat["height"] <= 600
    form = page.locator("#ask-form").bounding_box()
    assert 0 <= form["y"] and form["y"] + form["height"] <= 600


def test_a_tall_answer_scrolls_inside_its_panel(make_page, base_url):
    page = make_page(width=1280, height=700, fast_jobs=True)
    collection_with_document(page, base_url)
    text = " ".join(f"Cümle {n} burada yer alır." for n in range(1, 80))
    body = {
        "answer": "Cümle 40 burada yer alır.",
        "trace": [],
        "preset": "L2",
        "latency_ms": 1.0,
        "citations": [
            {"number": 1, "chunk_id": "x", "doc_id": "d", "heading_path": ["B"], "text": text}
        ],
    }
    page.route("**/api/collections/*/ask", lambda route: route.fulfill(json=body))
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#result .answer-card")).to_be_visible()
    scroll_height, client_height, overflow = page.locator("#step-answer").evaluate(
        "el => [el.scrollHeight, el.clientHeight, getComputedStyle(el).overflowY]"
    )
    assert scroll_height > client_height and overflow == "auto"
    page.locator("#step-answer").evaluate("el => el.scrollTo(0, el.scrollHeight)")
    expect(page.locator(".source-passage")).to_be_in_viewport()
    box = page.locator("#step-answer").bounding_box()
    assert box["y"] + box["height"] <= 700


def test_on_a_wide_screen_the_answer_does_not_move_the_page(make_page, base_url):
    page = make_page(width=1280, height=600, fast_jobs=True)
    collection_with_document(page, base_url)
    open_advanced(page)
    # The question is typed first: filling a box that is out of view scrolls it into view, and that
    # scroll is not the jump under test. The reference position is taken after it.
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.evaluate("document.getElementById('ask-submit').scrollIntoView({block: 'center'})")
    before = page.evaluate("window.scrollY")
    box = page.get_by_role("button", name=ASK).bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    expect(page.locator("#result .answer-card")).to_be_visible()
    page.wait_for_timeout(300)
    assert abs(page.evaluate("window.scrollY") - before) <= 1
