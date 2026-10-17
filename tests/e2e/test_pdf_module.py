"""Browser tests of the pdf.js wrapper: opening, paging, text highlights and selections."""

import base64
from pathlib import Path

import pytest
from pdf_fixtures import Block, write_pdf
from ui_helpers import run_js

pytestmark = pytest.mark.e2e

PAGES: list[list[Block]] = [
    [("h1", "Giriş"), ("p", "Alpha one begins here.\nThe word hyphen-\nated continues here.")],
    [("p", "Gamma three is here.\nNothing else matches.")],
    [("p", "istanbul Şehri ziyareti notu.")],
]
ONE_PAGE: list[list[Block]] = [[("p", "Only page here.")]]

# A test page with the viewer's host element and a viewer that reports its selections and pages.
SETUP = r"""
const { createPdfViewer } = await import('/js/viewer/pdf.js');
const link = document.createElement('link');
link.rel = 'stylesheet';
link.href = '/vendor/pdfjs/pdf_viewer.css';
document.head.append(link);
const host = document.createElement('div');
host.style.width = '800px';
host.style.height = '600px';
document.body.append(host);
const selections = [];
const pageChanges = [];
const viewer = await createPdfViewer(host, {
  onSelection: (info) => selections.push(info),
  onPage: (number) => pageChanges.push(number),
});
const waitFor = async (check) => {
  for (let i = 0; i < 400; i++) {
    if (check()) return true;
    await new Promise((resolve) => setTimeout(resolve, 25));
  }
  return false;
};
const toUrl = (b64) => URL.createObjectURL(
  new Blob([Uint8Array.from(atob(b64), (c) => c.charCodeAt(0))], { type: 'application/pdf' }),
);
const marked = () => [...document.querySelectorAll('.pdf-highlight')].map((n) => n.textContent);
const canvasOf = (number) => document.querySelector(`.pdf-page[data-page="${number}"] canvas`);
const settle = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
"""


def _pdf_base64(path: Path, pages: list[list[Block]] = PAGES) -> str:
    write_pdf(path, pages)
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _run(page, base_url, body: str, pdf_b64: str, second_b64: str = "") -> object:
    """Run the setup, then ``body``, with the base64 of the sample PDF in place of ``__B64__``
    and of a second PDF in place of ``__B64_2__``."""
    code = body.replace("__B64_2__", second_b64).replace("__B64__", pdf_b64)
    return run_js(page, base_url, SETUP + code)


def test_open_reports_the_page_count(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(page, base_url, "return (await viewer.open(toUrl('__B64__'))).pageCount;", pdf)
    assert result == 3


def test_go_to_page_sets_the_current_page(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(2);
        return viewer.currentPage();
        """,
        pdf,
    )
    assert result == 2


def test_highlight_on_a_later_page_scrolls_there_and_makes_it_current(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        await waitFor(() => viewer.currentPage() === 2);
        const span = document.querySelector('.pdf-highlight');
        const pageNode = span.closest('.pdf-page');
        const spanBox = span.getBoundingClientRect();
        const pageBox = pageNode.getBoundingClientRect();
        return {
          page: pageNode.dataset.page,
          inside: spanBox.top >= pageBox.top && spanBox.bottom <= pageBox.bottom,
          scrolled: host.scrollTop > 0,
          current: viewer.currentPage(),
        };
        """,
        pdf,
    )
    assert result == {"page": "2", "inside": True, "scrolled": True, "current": 2}


SAME_SENTENCE_PAGES: list[list[Block]] = [
    [("p", "Same sentence here.")],
    [("p", "Nothing here.")],
    [("p", "Same sentence here.")],
]


def test_highlight_on_the_requested_page_marks_that_page_not_an_earlier_copy(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "same.pdf", SAME_SENTENCE_PAGES)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(3);
        const found = await viewer.highlight('Same sentence here.', { page: 3 });
        await waitFor(() => viewer.currentPage() === 3);
        return {
          found,
          marked: [...document.querySelectorAll('.pdf-highlight')].map(
            (n) => n.closest('.pdf-page').dataset.page,
          ),
          current: viewer.currentPage(),
        };
        """,
        pdf,
    )
    assert result == {"found": True, "marked": ["3"], "current": 3}


def test_highlight_finds_a_sentence_on_the_page_after_the_requested_one(page, base_url, tmp_path):
    pages: list[list[Block]] = [
        [("p", "Filler on one.")],
        [("p", "Filler on two.")],
        [("p", "Filler on three.")],
        [("p", "Only on four here.")],
    ]
    pdf = _pdf_base64(tmp_path / "four.pdf", pages)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(3);
        const found = await viewer.highlight('Only on four here.', { page: 3 });
        const pages = [...new Set([...document.querySelectorAll('.pdf-highlight')].map(
          (n) => n.closest('.pdf-page').dataset.page,
        ))];
        return { found, pages };
        """,
        pdf,
    )
    assert result == {"found": True, "pages": ["4"]}


def test_highlight_on_the_requested_page_without_the_text_finds_the_next_page(
    page, base_url, tmp_path
):
    pages: list[list[Block]] = [
        [("p", "Filler on one.")],
        [("p", "Target sentence here.")],
        [("p", "Target sentence here.")],
    ]
    pdf = _pdf_base64(tmp_path / "next.pdf", pages)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('Target sentence here.', { page: 1 });
        const markedPages = [...new Set([...document.querySelectorAll('.pdf-highlight')].map(
          (n) => n.closest('.pdf-page').dataset.page,
        ))];
        return { found, marked: markedPages };
        """,
        pdf,
    )
    assert result == {"found": True, "marked": ["2"]}


def test_highlight_marks_exactly_the_matching_spans(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('gamma three');
        await waitFor(() => marked().length > 0);
        return [found, marked()];
        """,
        pdf,
    )
    assert result == [True, ["Gamma three is here."]]


def test_highlight_ignores_case_with_turkish_letters(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('İSTANBUL şehri');
        await waitFor(() => marked().length > 0);
        return [found, marked()];
        """,
        pdf,
    )
    assert result == [True, ["istanbul Şehri ziyareti notu."]]


def test_highlight_joins_a_word_split_by_a_line_end_hyphen(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('hyphenated continues');
        await waitFor(() => marked().length > 0);
        return [found, marked()];
        """,
        pdf,
    )
    assert result == [True, ["The word hyphen-", "ated continues here."]]


def test_highlight_without_a_match_returns_false_and_marks_nothing(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('not in the file');
        return [found, marked().length];
        """,
        pdf,
    )
    assert result == [False, 0]


def test_clear_highlight_removes_the_marks(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        await waitFor(() => marked().length > 0);
        viewer.clearHighlight();
        return marked().length;
        """,
        pdf,
    )
    assert result == 0


def test_zoom_reports_what_was_set(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const start = viewer.zoom();
        viewer.setZoom(1.5);
        const zoomed = viewer.zoom();
        viewer.setZoom('fit');
        return [start, zoomed, viewer.zoom()];
        """,
        pdf,
    )
    assert result == ["fit", 1.5, "fit"]


def test_drawn_pages_each_have_a_canvas_and_a_filled_text_layer(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        // A page that comes near the view while the highlight scrolls gets its text layer before its
        // canvas, so the wait is for every text layer to have a canvas and its spans.
        await waitFor(() => {
          const layers = [...document.querySelectorAll('.pdf-page .textLayer')];
          const canvases = [...document.querySelectorAll('.pdf-page canvas')];
          return layers.length >= 2 && layers.length === canvases.length
            && layers.every((layer) => layer.querySelector('span'));
        });
        const pagesWithCanvas = [...document.querySelectorAll('.pdf-page')].filter((n) => n.querySelector('canvas'));
        const layers = [...document.querySelectorAll('.pdf-page .textLayer')];
        return {
          canvases: pagesWithCanvas.length,
          layers: layers.length,
          spans: layers.map((layer) => layer.querySelectorAll('span').length),
        };
        """,
        pdf,
    )
    assert result["canvases"] == result["layers"] >= 2
    assert all(count > 0 for count in result["spans"])


def test_pages_far_below_the_viewport_are_not_drawn(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => document.querySelector('.pdf-page canvas') !== null);
        return [...document.querySelectorAll('.pdf-page')].map((n) => n.querySelector('canvas') !== null);
        """,
        pdf,
    )
    assert result[0] is True
    assert result[2] is False


def test_on_page_follows_go_to_page_and_scrolling(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(3);
        const afterGoTo = pageChanges[pageChanges.length - 1];
        host.scrollTop = 0;
        await waitFor(() => pageChanges[pageChanges.length - 1] === 1);
        return [pageChanges.includes(1), afterGoTo, pageChanges[pageChanges.length - 1]];
        """,
        pdf,
    )
    assert result == [True, 3, 1]


def test_open_twice_quickly_keeps_only_the_second_document(page, base_url, tmp_path):
    first = _pdf_base64(tmp_path / "sample.pdf")
    second = _pdf_base64(tmp_path / "one.pdf", ONE_PAGE)
    result = _run(
        page,
        base_url,
        """
        const firstOutcome = viewer.open(toUrl('__B64__')).then(
          () => 'resolved',
          (error) => error.message,
        );
        const opened = await viewer.open(toUrl('__B64_2__'));
        return [await firstOutcome, opened.pageCount, document.querySelectorAll('.pdf-page').length];
        """,
        first,
        second,
    )
    assert result == ["superseded", 1, 1]


def test_highlight_while_open_is_loading_is_false_and_does_not_poison_later_highlights(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const loading = viewer.open(toUrl('__B64__'));
        const early = await viewer.highlight('gamma three');
        await loading;
        const later = await viewer.highlight('gamma three');
        return [early, later, marked()];
        """,
        pdf,
    )
    assert result == [False, True, ["Gamma three is here."]]


def test_destroy_during_open_leaves_nothing_behind(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const loading = viewer.open(toUrl('__B64__')).then(
          () => 'resolved',
          (error) => error.message,
        );
        viewer.destroy();
        const outcome = await loading;
        await new Promise((resolve) => setTimeout(resolve, 300));
        return [outcome, host.childElementCount, document.querySelectorAll('canvas, .pdf-page').length];
        """,
        pdf,
    )
    assert result == ["superseded", 0, 0]


def test_open_of_garbage_bytes_rejects_with_load_failed(page, base_url):
    garbage = base64.b64encode(b"this is not a pdf").decode("ascii")
    result = _run(
        page,
        base_url,
        """
        try {
          await viewer.open(toUrl('__B64__'));
          return 'resolved';
        } catch (error) {
          return error.message;
        }
        """,
        garbage,
    )
    assert result == "load_failed"


def test_selecting_text_reports_it_to_on_selection(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('alpha one');
        await waitFor(() => host.querySelector('.textLayer span') !== null);
        const span = [...host.querySelectorAll('.textLayer span')].find(
          (node) => node.textContent.includes('Alpha one'),
        );
        const range = document.createRange();
        range.selectNodeContents(span);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        await waitFor(() => selections.some((info) => info !== null));
        const last = selections.filter((info) => info !== null).pop();
        return last ? last.text : null;
        """,
        pdf,
    )
    assert result == "Alpha one begins here."


# The matching helpers, tested directly on the module (no PDF needed).
MATCH_SETUP = (
    "const m = await import('/js/viewer/match.js');\n"
    "const pageOf = (str) => m.normalizeItems([{ str, eol: false }]);\n"
    "const find = (list, query, page) =>\n"
    "  m.findMatch(async (i) => list[i], query, m.pageOrder(list.length, page));\n"
)


def _match(page, base_url, body: str) -> object:
    return run_js(page, base_url, MATCH_SETUP + body)


def test_match_uses_the_first_sixty_characters_when_the_whole_text_is_not_on_the_page(
    page, base_url
):
    result = _match(
        page,
        base_url,
        """
        return await find([pageOf('a'.repeat(100))], 'a'.repeat(60) + ' not here');
        """,
    )
    assert result == {"page": 0, "start": 0, "end": 60}


def test_match_falls_back_to_the_first_thirty_characters(page, base_url):
    result = _match(
        page,
        base_url,
        """
        return await find([pageOf('a'.repeat(100))], 'a'.repeat(30) + 'b'.repeat(40));
        """,
    )
    assert result == {"page": 0, "start": 0, "end": 30}


def test_match_prefers_a_whole_text_match_on_a_later_page(page, base_url):
    result = _match(
        page,
        base_url,
        """
        const p = 'p'.repeat(60);
        return await find([pageOf(p + ' other'), pageOf(p + ' end')], p + ' end');
        """,
    )
    assert result == {"page": 1, "start": 0, "end": 64}


def test_match_folds_turkish_i_both_ways_and_keeps_dotted_and_dotless_apart(page, base_url):
    result = _match(
        page,
        base_url,
        """
        return [
          pageOf('ISTANBUL').text,
          pageOf('İstanbul').text,
          await find([pageOf('yalnız ıstanbul')], 'ISTANBUL') !== null,
          await find([pageOf('ISTANBUL')], 'ıstanbul') !== null,
          await find([pageOf('İstanbul')], 'Istanbul') === null,
        ];
        """,
    )
    assert result == ["ıstanbul", "istanbul", True, True, True]


def test_match_joins_a_line_end_hyphen_in_the_query(page, base_url):
    result = _match(
        page,
        base_url,
        """
        return [
          m.needlesFor('hyphen-\\n  ated word'),
          await find([pageOf('a hyphenated word')], 'hyphen-\\nated word'),
        ];
        """,
    )
    assert result == [["hyphenated word"], {"page": 0, "start": 2, "end": 17}]


def test_page_order_starts_at_the_requested_page_then_the_next_then_the_rest(page, base_url):
    result = _match(
        page,
        base_url,
        """
        return {
          requested: m.pageOrder(4, 3),
          first: m.pageOrder(4, 1),
          last: m.pageOrder(3, 3),
          none: m.pageOrder(3, null),
          outside: m.pageOrder(3, 9),
        };
        """,
    )
    assert result == {
        "requested": [2, 3, 0, 1],
        "first": [0, 1, 2, 3],
        "last": [2, 0, 1],
        "none": [0, 1, 2],
        "outside": [0, 1, 2],
    }


def test_find_match_reads_only_the_pages_it_needs_in_the_order_given(page, base_url):
    result = _match(
        page,
        base_url,
        """
        const pages = [pageOf('gamma'), pageOf('alpha beta'), pageOf('alpha beta')];
        const reads = [];
        const found = await m.findMatch(
          async (i) => { reads.push(i); return pages[i]; },
          'alpha beta',
          [2, 1, 0],
        );
        return { found, reads };
        """,
    )
    assert result == {"found": {"page": 2, "start": 0, "end": 10}, "reads": [2]}


def test_find_match_tries_the_whole_text_on_every_ordered_page_before_a_prefix(page, base_url):
    result = _match(
        page,
        base_url,
        """
        const p = 'p'.repeat(60);
        return await find([pageOf(p + ' other'), pageOf(p + ' end')], p + ' end', 1);
        """,
    )
    assert result == {"page": 1, "start": 0, "end": 64}


def test_a_sentence_on_the_requested_page_wins_over_the_same_sentence_on_an_earlier_one(
    page, base_url
):
    result = _match(
        page,
        base_url,
        """
        return await find([pageOf('same one'), pageOf('same one')], 'same one', 2);
        """,
    )
    assert result == {"page": 1, "start": 0, "end": 8}


def test_items_in_range_reports_the_items_the_characters_came_from(page, base_url):
    result = _match(
        page,
        base_url,
        """
        const { origins } = m.normalizeItems([
          { str: 'ab', eol: false },
          { str: 'cd', eol: true },
          { str: 'ef', eol: false },
        ]);
        return [
          [...m.itemsInRange(origins, 1, 3)],
          [...m.itemsInRange(origins, 4, 6)],
          [...m.itemsInRange(origins, 2, 2)],
        ];
        """,
    )
    assert result == [[0, 1], [1, 2], []]


A4_WIDTH = 595.2756


def test_scale_is_the_fit_scale_and_then_the_zoom_number(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const fit = viewer.scale();
        const pageWidth = document.querySelector('.pdf-page').getBoundingClientRect().width;
        viewer.setZoom(1.5);
        return [fit, pageWidth, viewer.scale()];
        """,
        pdf,
    )
    fit, page_width, zoomed = result
    assert abs(fit - page_width / A4_WIDTH) < 0.01
    assert abs(zoomed - 1.5) < 0.01


def test_highlight_superseded_while_its_text_layer_builds_resolves_false(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const lib = await import('/vendor/pdfjs/pdf.min.mjs');
        const originalRender = lib.TextLayer.prototype.render;
        let armed = false;
        let delayed = false;
        lib.TextLayer.prototype.render = function (...args) {
          if (armed && !delayed) {
            delayed = true;
            return new Promise((resolve) => setTimeout(() => resolve(originalRender.apply(this, args)), 300));
          }
          return originalRender.apply(this, args);
        };
        try {
          await viewer.open(toUrl('__B64__'));
          await new Promise((resolve) => setTimeout(resolve, 500));
          armed = true;
          const pending = viewer.highlight('istanbul şehri');
          await waitFor(() => delayed);
          viewer.destroy();
          return await pending.then((value) => value, (error) => 'rejected: ' + error.message);
        } finally {
          lib.TextLayer.prototype.render = originalRender;
        }
        """,
        pdf,
    )
    assert result is False


def test_clear_highlight_cancels_a_highlight_in_flight(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const pending = viewer.highlight('gamma three');
        viewer.clearHighlight();
        const found = await pending;
        return [found, marked().length];
        """,
        pdf,
    )
    assert result == [False, 0]


def test_a_failed_page_draw_is_retried_when_the_page_comes_back(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        const originalContext = HTMLCanvasElement.prototype.getContext;
        let failures = 1;
        HTMLCanvasElement.prototype.getContext = function (...args) {
          if (failures > 0 && !this.isConnected) {
            failures -= 1;
            throw new Error('render failed');
          }
          return originalContext.apply(this, args);
        };
        try {
          await viewer.open(toUrl('__B64__'));
          const failed = await waitFor(() => failures === 0);
          // Leave the draw margin but stay inside the release margin, so the failed draw is not
          // dropped by a release; then come back, which must draw the canvas again.
          const page1 = document.querySelector('.pdf-page[data-page="1"]');
          host.scrollTop = page1.offsetTop + page1.offsetHeight + 1.5 * host.clientHeight;
          await new Promise((resolve) => setTimeout(resolve, 300));
          viewer.goToPage(1);
          const back = await waitFor(() => canvasOf(1) !== null && canvasOf(1).width > 0);
          return [failed, back];
        } finally {
          HTMLCanvasElement.prototype.getContext = originalContext;
        }
        """,
        pdf,
    )
    assert result == [True, True]


def test_two_highlights_in_flight_leave_only_the_latest_marked(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const first = viewer.highlight('gamma three');
        const second = viewer.highlight('alpha one');
        const results = await Promise.all([first, second]);
        return [results, marked()];
        """,
        pdf,
    )
    assert result == [[False, True], ["Alpha one begins here."]]


def test_highlight_in_flight_during_an_open_of_another_document_resolves_false(
    page, base_url, tmp_path
):
    first = _pdf_base64(tmp_path / "sample.pdf")
    second = _pdf_base64(tmp_path / "one.pdf", ONE_PAGE)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const pending = viewer.highlight('gamma three');
        const opened = viewer.open(toUrl('__B64_2__'));
        const outcome = await Promise.race([
          pending.then((value) => value, (error) => 'rejected: ' + error.message),
          new Promise((resolve) => setTimeout(() => resolve('hung'), 3000)),
        ]);
        await opened;
        return [outcome, marked().length];
        """,
        first,
        second,
    )
    assert result == [False, 0]


def test_highlight_after_opening_another_document_finds_the_new_text(page, base_url, tmp_path):
    first = _pdf_base64(tmp_path / "sample.pdf")
    second = _pdf_base64(tmp_path / "one.pdf", ONE_PAGE)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        await viewer.open(toUrl('__B64_2__'));
        const found = await viewer.highlight('Only page');
        return [found, marked()];
        """,
        first,
        second,
    )
    assert result == [True, ["Only page here."]]


def test_reopening_another_document_sizes_and_draws_its_pages(page, base_url, tmp_path):
    first = _pdf_base64(tmp_path / "sample.pdf")
    second = _pdf_base64(tmp_path / "one.pdf", ONE_PAGE)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => canvasOf(1) !== null);
        await viewer.open(toUrl('__B64_2__'));
        const drawn = await waitFor(() => canvasOf(1) !== null);
        const node = document.querySelector('.pdf-page[data-page="1"]');
        return [drawn, node.style.width !== ''];
        """,
        first,
        second,
    )
    assert result == [True, True]


def test_text_layer_is_scaled_by_the_page_scale(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const firstSpanSize = async () => {
          await waitFor(() => document.querySelector('.pdf-page[data-page="1"] .textLayer span') !== null);
          const span = document.querySelector('.pdf-page[data-page="1"] .textLayer span');
          return parseFloat(getComputedStyle(span).fontSize);
        };
        await viewer.open(toUrl('__B64__'));
        const fitScale = viewer.scale();
        const fitSize = await firstSpanSize();
        viewer.setZoom(2);
        const zoomedSize = await firstSpanSize();
        return [zoomedSize / fitSize, 2 / fitScale];
        """,
        pdf,
    )
    ratio, expected = result
    assert abs(ratio - expected) < 0.05


PAGES_12: list[list[Block]] = [[("p", f"Page {number} marker text.")] for number in range(1, 13)]
# At the fit width of the test container a page is about 1050 px tall and the container 600 px.
# A canvas is held only while its page is within three viewport heights of the view, which at
# this size is about two pages either side of the viewed page. The test measured at most three
# canvases while it scrolled, so six is a bound with room for a page still being released; a
# page that never releases would reach twelve.
MAX_CANVASES = 6


def test_far_pages_release_their_canvas_and_keep_their_text_layer(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const canvases = () => document.querySelectorAll('.pdf-page canvas').length;
        let most = 0;
        for (let number = 1; number <= 12; number += 1) {
          viewer.goToPage(number);
          await waitFor(() => document.querySelector(`.pdf-page[data-page="${number}"] canvas`) !== null);
          await new Promise((resolve) => setTimeout(resolve, 100));
          most = Math.max(most, canvases());
        }
        await waitFor(() => [...document.querySelectorAll('.pdf-page .textLayer')].every((layer) => layer.querySelector('span')));
        return {
          most,
          textLayers: [...document.querySelectorAll('.pdf-page .textLayer')].map((layer) => layer.querySelectorAll('span').length),
        };
        """,
        pdf,
    )
    assert result["most"] <= MAX_CANVASES
    assert result["most"] < 12
    assert len(result["textLayers"]) == 12
    assert all(count > 0 for count in result["textLayers"])


def test_scrolling_back_redraws_a_released_page(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => canvasOf(1) !== null);
        viewer.goToPage(12);
        await waitFor(() => canvasOf(1) === null);
        const released = canvasOf(1) === null;
        viewer.goToPage(1);
        await waitFor(() => canvasOf(1) !== null && canvasOf(1).width > 0);
        return [released, canvasOf(1) ? canvasOf(1).width : 0];
        """,
        pdf,
    )
    assert result[0] is True
    assert result[1] > 0


def test_highlight_on_a_released_page_keeps_its_mark_and_redraws(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        const firstFound = await viewer.highlight('page 1 marker');
        viewer.goToPage(12);
        await waitFor(() => canvasOf(1) === null);
        const afterRelease = [document.querySelectorAll('.pdf-highlight').length, canvasOf(1) === null];
        const found = await viewer.highlight('page 1 marker');
        await waitFor(() => viewer.currentPage() === 1);
        const redrawn = await waitFor(() => canvasOf(1) !== null);
        return [firstFound, afterRelease, found, viewer.currentPage(), redrawn];
        """,
        pdf,
    )
    assert result == [True, [1, True], True, 1, True]


# A hook on the first canvas that is not in the page yet (mid-draw): the action runs while that
# canvas is being drawn, so a later layout, scroll or release overtakes the draw deterministically.
CANVAS_HOOK = """
const hook = { fired: false };
const originalContext = HTMLCanvasElement.prototype.getContext;
const installHook = (action) => {
  HTMLCanvasElement.prototype.getContext = function (...args) {
    if (!hook.fired && !this.isConnected) {
      hook.fired = true;
      action();
    }
    return originalContext.apply(this, args);
  };
};
const removeHook = () => { HTMLCanvasElement.prototype.getContext = originalContext; };
"""


def test_a_rapid_pair_of_highlights_leaves_no_canvas_on_the_superseded_far_page(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('alpha one');
        // The first highlight passes its search and starts on page 12; a tick later a second one
        // supersedes it. Page 12 must not keep a canvas, since the view never scrolled there.
        const first = viewer.highlight('page 12 marker');
        await new Promise((resolve) => setTimeout(resolve, 0));
        const second = viewer.highlight('page 2 marker');
        const found = await second;
        await first;
        await new Promise((resolve) => setTimeout(resolve, 1000));
        return [found, canvasOf(12) === null];
        """,
        pdf,
    )
    assert result == [True, True]


def test_zoom_during_a_canvas_draw_leaves_one_canvas_at_the_new_scale(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        CANVAS_HOOK
        + """
        installHook(() => viewer.setZoom(2));
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => hook.fired);
        const drawn = await waitFor(() => {
          const canvas = canvasOf(1);
          const node = document.querySelector('.pdf-page[data-page="1"]');
          return canvas !== null && Math.abs(parseFloat(canvas.style.width) - parseFloat(node.style.width)) <= 1;
        });
        await settle(800);
        removeHook();
        const pages = [...document.querySelectorAll('.pdf-page')]
          .filter((node) => node.querySelector('canvas'))
          .map((node) => [
            node.dataset.page,
            node.querySelectorAll('canvas').length,
            Math.round(parseFloat(node.querySelector('canvas').style.width)),
            Math.round(parseFloat(node.style.width)),
          ]);
        return [drawn, pages];
        """,
        pdf,
    )
    drawn, result = result
    assert drawn is True
    for number, count, canvas_width, page_width in result:
        assert count == 1, (number, count)
        assert abs(canvas_width - page_width) <= 1, (number, canvas_width, page_width)


def test_scrolling_away_during_a_canvas_draw_leaves_no_far_canvas(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        CANVAS_HOOK
        + """
        installHook(() => { host.scrollTop = host.scrollHeight; });
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => hook.fired);
        await settle(800);
        removeHook();
        const box = host.getBoundingClientRect();
        return [...document.querySelectorAll('.pdf-page')]
          .filter((node) => node.querySelector('canvas'))
          .map((node) => {
            const r = node.getBoundingClientRect();
            return Math.max(box.top - r.bottom, r.top - box.bottom, 0) / box.height;
          })
          .filter((viewports) => viewports > 3);
        """,
        pdf,
    )
    assert result == []


def test_a_released_canvas_is_emptied_so_its_memory_is_freed(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => canvasOf(1) !== null && canvasOf(1).width > 0);
        const kept = canvasOf(1);
        viewer.goToPage(12);
        await waitFor(() => canvasOf(1) === null);
        return [kept.width, kept.height];
        """,
        pdf,
    )
    assert result == [0, 0]


def test_a_page_between_the_draw_and_release_margins_keeps_its_canvas(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(3);
        await waitFor(() => canvasOf(3) !== null);
        // Page 3 starts 2.5 viewport heights below the top of the view: beyond one viewport height
        // (not drawn for a new arrival) and within three (kept).
        const node3 = document.querySelector('.pdf-page[data-page="3"]');
        host.scrollTop = node3.offsetTop - 2.5 * host.clientHeight;
        await new Promise((resolve) => setTimeout(resolve, 800));
        return canvasOf(3) !== null;
        """,
        pdf,
    )
    assert result is True


def test_zoom_during_a_text_layer_build_keeps_later_highlights_working(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const lib = await import('/vendor/pdfjs/pdf.min.mjs');
        const originalRender = lib.TextLayer.prototype.render;
        let delayed = false;
        lib.TextLayer.prototype.render = function (...args) {
          if (!delayed) {
            delayed = true;
            viewer.setZoom(2);
            // This build is overtaken by the zoom; it finishes after the zoomed build did.
            return new Promise((resolve) => setTimeout(() => resolve(originalRender.apply(this, args)), 300));
          }
          return originalRender.apply(this, args);
        };
        try {
          await viewer.open(toUrl('__B64__'));
          await waitFor(() => delayed);
          await new Promise((resolve) => setTimeout(resolve, 800));
          const found = await viewer.highlight('alpha one');
          await new Promise((resolve) => setTimeout(resolve, 100));
          const again = await viewer.highlight('alpha one');
          return [found, again, document.querySelectorAll('.pdf-highlight').length];
        } finally {
          lib.TextLayer.prototype.render = originalRender;
        }
        """,
        pdf,
    )
    assert result == [True, True, 1]


def test_a_highlight_is_marked_again_after_a_zoom_on_the_same_page(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        viewer.setZoom(1.5);
        await waitFor(() => document.querySelectorAll('.pdf-highlight').length > 0);
        const spans = [...document.querySelectorAll('.pdf-highlight')];
        return {
          text: spans.map((node) => node.textContent),
          page: spans[0].closest('.pdf-page').dataset.page,
          current: viewer.currentPage(),
        };
        """,
        pdf,
    )
    assert result == {"text": ["Gamma three is here."], "page": "2", "current": 2}


def test_invalid_zoom_values_are_ignored_and_zoom_is_clamped(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        viewer.setZoom(2);
        const beforeOpen = viewer.scale();
        viewer.setZoom(NaN);
        viewer.setZoom(0);
        viewer.setZoom(-3);
        viewer.setZoom(Infinity);
        const afterInvalid = viewer.zoom();
        viewer.setZoom(10);
        const high = viewer.zoom();
        viewer.setZoom(0.1);
        return [beforeOpen, afterInvalid, high, viewer.zoom()];
        """,
        pdf,
    )
    assert result == [2, 2, 4, 0.25]


def test_open_after_destroy_rejects_and_touches_nothing(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        viewer.destroy();
        const outcome = await viewer.open(toUrl('__B64__')).then(
          () => 'resolved',
          (error) => error.message,
        );
        return [outcome, host.childElementCount];
        """,
        pdf,
    )
    assert result == ["destroyed", 0]


def test_no_selection_or_page_callback_arrives_after_destroy(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => host.querySelector('.textLayer span') !== null);
        const span = [...host.querySelectorAll('.textLayer span')].find((node) => node.textContent.includes('Alpha one'));
        const range = document.createRange();
        range.selectNodeContents(span);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        await waitFor(() => selections.some((info) => info !== null));
        const selectionsBefore = selections.length;
        const pagesBefore = pageChanges.length;
        viewer.destroy();
        selection.removeAllRanges();
        document.dispatchEvent(new Event('selectionchange'));
        host.dispatchEvent(new Event('scroll'));
        await new Promise((resolve) => setTimeout(resolve, 200));
        return [selections.length - selectionsBefore, pageChanges.length - pagesBefore];
        """,
        pdf,
    )
    assert result == [0, 0]


def test_a_document_opened_while_hidden_ends_on_the_highlighted_page_once_shown(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.display = 'none';
        await viewer.open(toUrl('__B64__'));
        host.style.display = '';
        viewer.setZoom(viewer.zoom());
        viewer.goToPage(2);
        const found = await viewer.highlight('gamma three');
        await waitFor(() => viewer.currentPage() === 2);
        await new Promise((resolve) => setTimeout(resolve, 300));
        return [found, viewer.currentPage(), pageChanges[pageChanges.length - 1]];
        """,
        pdf,
    )
    assert result == [True, 2, 2]


def test_a_highlight_right_after_a_zoom_ends_on_the_marked_page(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.setZoom(1.5);
        const found = await viewer.highlight('gamma three');
        await waitFor(() => viewer.currentPage() === 2);
        await new Promise((resolve) => setTimeout(resolve, 300));
        return [found, viewer.currentPage(), pageChanges[pageChanges.length - 1]];
        """,
        pdf,
    )
    assert result == [True, 2, 2]


def test_highlight_in_an_auto_height_container_scrolls_the_window_to_its_page(
    page, base_url, tmp_path
):
    # The narrow layout lets the viewer grow with its pages, so the page scrolls, not the container.
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.height = 'auto';
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('gamma three');
        const reached = await waitFor(() => viewer.currentPage() === 2);
        return [found, reached, viewer.currentPage(), pageChanges[pageChanges.length - 1], window.scrollY > 0];
        """,
        pdf,
    )
    assert result == [True, True, 2, 2, True]


def test_a_hidden_container_does_not_report_a_page_while_it_is_hidden(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.display = 'none';
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(2);
        await viewer.highlight('gamma three');
        return pageChanges.filter((number) => number === 3).length;
        """,
        pdf,
    )
    assert result == 0


def test_scrolling_the_window_of_an_auto_height_view_reports_the_page(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.height = 'auto';
        await viewer.open(toUrl('__B64__'));
        const node3 = document.querySelector('.pdf-page[data-page="3"]');
        window.scrollTo(0, node3.getBoundingClientRect().top + window.scrollY);
        const reached = await waitFor(() => viewer.currentPage() === 3);
        return [reached, pageChanges[pageChanges.length - 1]];
        """,
        pdf,
    )
    assert result == [True, 3]


def test_far_pages_release_their_canvas_when_the_window_scrolls(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        host.style.height = 'auto';
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => canvasOf(1) !== null);
        viewer.goToPage(12);
        const released = await waitFor(() => canvasOf(1) === null);
        const drawn = await waitFor(() => canvasOf(12) !== null);
        return [released, drawn];
        """,
        pdf,
    )
    assert result == [True, True]


def test_clear_highlight_forgets_the_text_so_a_zoom_does_not_mark_it_again(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        viewer.clearHighlight();
        viewer.setZoom(1.5);
        await settle(300);
        return marked().length;
        """,
        pdf,
    )
    assert result == 0


def test_reopening_a_document_forgets_the_highlight_so_a_zoom_does_not_mark_it(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        // The same text is in the second document, so only a forgotten highlight stays unmarked.
        await viewer.open(toUrl('__B64_2__'));
        viewer.setZoom(1.5);
        await settle(300);
        return marked().length;
        """,
        pdf,
        pdf,
    )
    assert result == 0


def test_a_zoom_marks_the_text_again_without_moving_the_reader_to_it(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        viewer.goToPage(3);
        viewer.setZoom(1.5);
        const remarked = await waitFor(() => marked().length === 1);
        await settle(300);
        return [remarked, marked(), viewer.currentPage()];
        """,
        pdf,
    )
    assert result == [True, ["Gamma three is here."], 3]


def test_go_to_page_ignores_values_that_are_not_numbers_and_clamps_the_rest(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(2);
        const outcomes = [];
        for (const value of [NaN, undefined, 'x']) {
          viewer.goToPage(value);
          outcomes.push(viewer.currentPage());
        }
        viewer.goToPage(2.4);
        outcomes.push(viewer.currentPage());
        viewer.goToPage(99);
        outcomes.push(viewer.currentPage());
        viewer.goToPage(-4);
        outcomes.push(viewer.currentPage());
        return outcomes;
        """,
        pdf,
    )
    assert result == [2, 2, 2, 2, 3, 1]


def test_a_failing_re_mark_after_a_zoom_is_not_an_unhandled_rejection(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const lib = await import('/vendor/pdfjs/pdf.min.mjs');
        const originalRender = lib.TextLayer.prototype.render;
        const unhandled = [];
        const onUnhandled = (event) => unhandled.push(String(event.reason));
        window.addEventListener('unhandledrejection', onUnhandled);
        try {
          await viewer.open(toUrl('__B64__'));
          await viewer.highlight('gamma three');
          lib.TextLayer.prototype.render = function () {
            return Promise.reject(new Error('layer failed'));
          };
          viewer.setZoom(1.5);
          await settle(300);
          return unhandled;
        } finally {
          lib.TextLayer.prototype.render = originalRender;
          window.removeEventListener('unhandledrejection', onUnhandled);
        }
        """,
        pdf,
    )
    assert result == []


def test_a_resize_that_changes_the_scroll_mode_moves_the_observer_root(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        """
        host.style.height = '600px';
        await viewer.open(toUrl('__B64__'));
        await waitFor(() => canvasOf(1) !== null);
        // The view grows with its pages: the window scrolls, so the far page must be released.
        host.style.height = 'auto';
        window.dispatchEvent(new Event('resize'));
        await settle(100);
        viewer.goToPage(12);
        const released = await waitFor(() => canvasOf(1) === null);
        return released;
        """,
        pdf,
    )
    assert result is True


def test_a_failing_re_mark_after_a_zoom_is_handled_and_a_later_highlight_retries(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const lib = await import('/vendor/pdfjs/pdf.min.mjs');
        const probeDocument = await lib.getDocument({ url: toUrl('__B64__') }).promise;
        const pageProto = Object.getPrototypeOf(await probeDocument.getPage(1));
        const originalText = pageProto.getTextContent;
        let failing = true;
        pageProto.getTextContent = function (...args) {
          return failing ? Promise.reject(new Error('text failed')) : originalText.apply(this, args);
        };
        const unhandled = [];
        const onUnhandled = (event) => {
          unhandled.push(String(event.reason));
          event.preventDefault();
        };
        window.addEventListener('unhandledrejection', onUnhandled);
        try {
          await viewer.open(toUrl('__B64__'));
          const firstTry = await viewer.highlight('gamma three').then(() => 'marked', () => 'failed');
          viewer.setZoom(1.5);
          await settle(300);
          failing = false;
          const later = await viewer.highlight('gamma three').then((value) => value, () => 'failed');
          return [firstTry, unhandled, later, marked()];
        } finally {
          failing = false;
          pageProto.getTextContent = originalText;
          window.removeEventListener('unhandledrejection', onUnhandled);
        }
        """,
        pdf,
    )
    assert result == ["failed", [], True, ["Gamma three is here."]]


# Counts the layouts of the viewer: a layout clears the node of each page, so the node of page 1
# is cleared once per layout. The counter is removed again by stopCounting.
COUNT_LAYOUTS = r"""
const layoutCount = { n: 0 };
const nativeReplace = Element.prototype.replaceChildren;
Element.prototype.replaceChildren = function (...args) {
  if (this.classList.contains('pdf-page') && this.dataset.page === '1') layoutCount.n += 1;
  return nativeReplace.apply(this, args);
};
const stopCounting = () => { Element.prototype.replaceChildren = nativeReplace; };
const A4 = 595.2756;
"""


def test_widening_the_view_in_fit_zoom_relays_out_the_pages(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.width = '600px';
        await viewer.open(toUrl('__B64__'));
        viewer.goToPage(2);
        const before = viewer.scale();
        host.style.width = '900px';
        await waitFor(() => viewer.scale() > before * 1.2);
        const expected = (host.clientWidth - 64) / 595.2756;
        const pageNode = document.querySelector('.pdf-page[data-page="1"]');
        return {
          grew: viewer.scale() > before,
          proportion: Math.abs(viewer.scale() - expected) < 0.01,
          pageWidth: Math.abs(pageNode.getBoundingClientRect().width - viewer.scale() * 595.2756) < 1,
          current: viewer.currentPage(),
        };
        """,
        pdf,
    )
    assert result == {"grew": True, "proportion": True, "pageWidth": True, "current": 2}


def test_a_highlight_is_marked_again_after_a_resize_without_moving_the_reader(
    page, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        host.style.width = '600px';
        await viewer.open(toUrl('__B64__'));
        await viewer.highlight('gamma three');
        await waitFor(() => marked().length > 0);
        host.style.width = '900px';
        await waitFor(() => viewer.scale() > 1.2);
        await waitFor(() => marked().length > 0);
        const span = document.querySelector('.pdf-highlight');
        const view = host.getBoundingClientRect();
        const pageNode = span.closest('.pdf-page');
        return {
          text: marked(),
          page: pageNode.dataset.page,
          current: viewer.currentPage(),
          // The page sits at the reading line of the view, as goToPage leaves it: a scroll to
          // the mark would have moved the page.
          pageAtReadingLine: Math.abs(
            pageNode.getBoundingClientRect().top - (view.top + view.height * 0.3)
          ) < 2,
        };
        """,
        pdf,
    )
    assert result == {
        "text": ["Gamma three is here."],
        "page": "2",
        "current": 2,
        "pageAtReadingLine": True,
    }


# The height feedback only: the view grows with its pages, so every layout changes the container's
# height, and the width stays the same in this host. A scrollbar that a layout makes appear is
# covered by the classic-scrollbar tests below, since the headless browser hides scrollbars here.
def test_height_feedback_from_a_layout_does_not_start_more_layouts(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "long.pdf", PAGES_12)
    result = _run(
        page,
        base_url,
        COUNT_LAYOUTS
        + """
        // The view grows with its pages, so every layout changes the container's height.
        host.style.height = 'auto';
        await viewer.open(toUrl('__B64__'));
        await settle(100);
        layoutCount.n = 0;
        host.style.width = '500px';
        await waitFor(() => Math.abs(viewer.scale() - (500 - 64) / A4) < 0.01);
        await settle(150);
        host.style.width = '700px';
        await waitFor(() => Math.abs(viewer.scale() - (700 - 64) / A4) < 0.01);
        await settle(150);
        stopCounting();
        return layoutCount.n;
        """,
        pdf,
    )
    assert result == 2


@pytest.fixture
def classic_browser(playwright_driver):
    """A browser whose scrollbars take layout width, as in the user's Chrome. The shared browser
    hides them, which hid a loop and a double layout on open; this one does not. Skips when no
    browser can be launched that way."""
    from playwright.sync_api import Error as PlaywrightError

    launched = None
    last_error = None
    for options in ({}, {"channel": "chrome"}):
        try:
            launched = playwright_driver.chromium.launch(
                ignore_default_args=["--hide-scrollbars"], **options
            )
            break
        except PlaywrightError as error:
            last_error = error
    if launched is None:
        pytest.skip(f"no browser with classic scrollbars can be launched: {last_error}")
    yield launched
    launched.close()


def _cold_run(browser, base_url, body: str, pdf_b64: str) -> object:
    """Run the body in a new page of the browser, so that nothing from an earlier run is kept."""
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    try:
        return _run(context.new_page(), base_url, body, pdf_b64)
    finally:
        context.close()


# In the band of heights below, a one-page document in an 800 px host gets a scrollbar with a
# layout, which narrows the host and makes the fit width change; the old code then relaid out
# again and again. Each open must end with at most two layouts and a stable scale.
BAND_HEIGHTS = [1035, 1040, 1050]


def test_a_real_scrollbar_in_the_band_of_heights_settles_after_at_most_two_layouts(
    classic_browser, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "one.pdf", ONE_PAGE)
    result = _cold_run(
        classic_browser,
        base_url,
        COUNT_LAYOUTS
        + """
        const outcomes = [];
        for (const height of __HEIGHTS__) {
          host.style.height = `${height}px`;
          layoutCount.n = 0;
          await viewer.open(toUrl('__B64__'));
          await settle(300);
          const scaleAfterOpen = viewer.scale();
          await settle(300);
          outcomes.push({
            layouts: layoutCount.n,
            stable: viewer.scale() === scaleAfterOpen,
            scrollbar: host.offsetWidth - host.clientWidth,
          });
        }
        stopCounting();
        return outcomes;
        """.replace("__HEIGHTS__", str(BAND_HEIGHTS)),
        pdf,
    )
    assert len(result) == len(BAND_HEIGHTS)
    for outcome in result:
        assert outcome["scrollbar"] >= 10, outcome
        assert outcome["layouts"] <= 2, outcome
        assert outcome["stable"] is True, outcome


def test_opening_a_three_page_document_with_a_real_scrollbar_lays_out_once(
    classic_browser, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _cold_run(
        classic_browser,
        base_url,
        COUNT_LAYOUTS
        + """
        host.style.height = '600px';
        layoutCount.n = 0;
        await viewer.open(toUrl('__B64__'));
        // The observer checks in a later frame: the settle lets any second layout happen first.
        await settle(300);
        stopCounting();
        return { layouts: layoutCount.n, scrollbar: host.offsetWidth - host.clientWidth };
        """,
        pdf,
    )
    assert result["scrollbar"] >= 10, result
    assert result["layouts"] == 1


def test_a_highlight_right_after_open_with_a_real_scrollbar_finds_its_page_every_time(
    classic_browser, base_url, tmp_path
):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    body = """
        host.style.height = '600px';
        await viewer.open(toUrl('__B64__'));
        const found = await viewer.highlight('gamma three', { page: 2 });
        await settle(300);
        return [found, viewer.currentPage(), host.offsetWidth - host.clientWidth];
        """
    # Each open is cold, in a new page: the race between the second layout and the highlight
    # showed in most cold runs, so three runs are made.
    results = [_cold_run(classic_browser, base_url, body, pdf) for _ in range(3)]
    for found, current, scrollbar in results:
        assert scrollbar >= 10
        assert found is True
        assert current == 2


def test_a_numeric_zoom_is_not_changed_by_a_resize(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        COUNT_LAYOUTS
        + """
        await viewer.open(toUrl('__B64__'));
        viewer.setZoom(1.5);
        await settle(100);
        layoutCount.n = 0;
        host.style.width = '500px';
        await settle(200);
        stopCounting();
        const numeric = { zoom: viewer.zoom(), scale: viewer.scale(), relayouts: layoutCount.n };
        // Once the zoom is "fit" again the same resize does relayout: the observer is in place.
        viewer.setZoom('fit');
        host.style.width = '400px';
        const fitFollows = await waitFor(
          () => Math.abs(viewer.scale() - (400 - 64) / A4) < 0.01,
        );
        return { ...numeric, fitFollows };
        """,
        pdf,
    )
    assert result == {"zoom": 1.5, "scale": 1.5, "relayouts": 0, "fitFollows": True}


def test_a_hidden_view_is_ignored_and_recovers_when_it_is_wide_again(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const A4 = 595.2756;
        await viewer.open(toUrl('__B64__'));
        const before = viewer.scale();
        host.style.width = '0px';
        await settle(150);
        const keptWhileHidden = viewer.scale() === before;
        host.style.width = '700px';
        const recovered = await waitFor(
          () => Math.abs(viewer.scale() - (700 - 64) / A4) < 0.01,
        );
        return { keptWhileHidden, recovered };
        """,
        pdf,
    )
    assert result == {"keptWhileHidden": True, "recovered": True}


def test_the_resize_observer_is_disconnected_by_destroy(page, base_url, tmp_path):
    pdf = _pdf_base64(tmp_path / "sample.pdf")
    result = _run(
        page,
        base_url,
        """
        const NativeObserver = window.ResizeObserver;
        const observers = [];
        class SpyObserver extends NativeObserver {
          constructor(callback) {
            super(callback);
            this.disconnects = 0;
            observers.push(this);
          }
          disconnect() {
            this.disconnects += 1;
            super.disconnect();
          }
        }
        window.ResizeObserver = SpyObserver;
        try {
          const own = document.createElement('div');
          own.style.width = '700px';
          own.style.height = '600px';
          document.body.append(own);
          const viewer2 = await createPdfViewer(own, {});
          await viewer2.open(toUrl('__B64__'));
          const made = observers.length;
          viewer2.destroy();
          own.style.width = '500px';
          await settle(150);
          return {
            made,
            allDisconnected: made > 0 && observers.every((o) => o.disconnects > 0),
          };
        } finally {
          window.ResizeObserver = NativeObserver;
        }
        """,
        pdf,
    )
    assert result == {"made": 1, "allDisconnected": True}


# The public members of the viewer, and nothing else: the helpers in pages.js and search.js are
# reached only through pdf.js, so a member added to the facade shows up here.
VIEWER_MEMBERS = sorted(
    [
        "open",
        "goToPage",
        "currentPage",
        "setZoom",
        "zoom",
        "scale",
        "highlight",
        "clearHighlight",
        "destroy",
    ]
)


def test_the_viewer_has_exactly_the_public_members(page, base_url):
    result = _run(page, base_url, "return Object.keys(viewer).sort();", "")
    assert result == VIEWER_MEMBERS


def test_the_split_modules_expose_their_named_exports(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const pages = await import('/js/viewer/pages.js');
        const search = await import('/js/viewer/search.js');
        return {
          createPageRenderer: typeof pages.createPageRenderer,
          newPage: typeof pages.newPage,
          createHighlighter: typeof search.createHighlighter,
        };
        """,
    )
    assert result == {
        "createPageRenderer": "function",
        "newPage": "function",
        "createHighlighter": "function",
    }
