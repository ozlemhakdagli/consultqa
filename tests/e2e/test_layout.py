"""The layout: a top bar, two columns on wide screens, one column in reading order on phones."""

import pytest
from playwright.sync_api import expect
from ui_helpers import collection_with_document, open_advanced, open_page

pytestmark = pytest.mark.e2e
ASK = "Cevabı bul"
IDS = ("step-documents", "step-ask", "step-answer", "advanced")


def _boxes(page):
    return [page.locator(f"#{name}").bounding_box() for name in IDS]


@pytest.mark.parametrize("width", [1280, 1920])
def test_wide_screens_use_the_full_width_in_two_columns(make_page, base_url, width):
    page = make_page(width=width, height=900)
    open_page(page, base_url)
    assert page.locator(".workspace").bounding_box()["width"] >= 0.9 * width
    docs, ask, answer, advanced = _boxes(page)
    assert answer["x"] >= docs["x"] + docs["width"]
    assert abs(answer["y"] - docs["y"]) <= 2
    assert ask["y"] >= docs["y"] + docs["height"] - 1
    assert advanced["y"] >= ask["y"] + ask["height"] - 1
    assert round(docs["x"]) == round(ask["x"]) == round(advanced["x"])
    assert answer["x"] + answer["width"] <= width
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize(("width", "height"), [(390, 844), (768, 1024), (991, 800)])
def test_narrow_screens_stack_everything_in_reading_order(make_page, base_url, width, height):
    page = make_page(width=width, height=height)
    open_page(page, base_url)
    boxes = _boxes(page)
    for upper, lower in zip(boxes, boxes[1:], strict=False):
        assert lower["y"] >= upper["y"] + upper["height"] - 1
    assert len({round(box["x"]) for box in boxes}) == 1
    assert boxes[0]["width"] >= 0.85 * width


def test_the_answer_stays_in_view_beside_the_form(make_page, base_url):
    page = make_page(width=1280, height=600)
    collection_with_document(page, base_url)
    open_advanced(page)
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#result .answer-card")).to_be_visible()
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    assert page.evaluate("window.scrollY") > 0
    box = page.locator("#step-answer").bounding_box()
    assert 0 <= box["y"] <= 20 and box["y"] + box["height"] <= 600


def test_a_tall_answer_scrolls_inside_its_panel(make_page, base_url):
    page = make_page(width=1280, height=700)
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
    page = make_page(width=1280, height=600)
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
