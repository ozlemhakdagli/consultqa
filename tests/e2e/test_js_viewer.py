"""Browser tests of the viewer view, its actions and the document rows, with fake viewers and API."""

import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e

# Builds the ids of the viewer pane and of the document list, as index.html has them.
BUILD = """
const node = (tag, id, attrs = {}) => {
  const created = document.createElement(tag);
  created.id = id;
  for (const [name, value] of Object.entries(attrs)) created.setAttribute(name, value);
  document.body.append(created);
  return created;
};
node('h2', 'viewer-title');
node('div', 'viewer-toolbar');
node('input', 'viewer-page', { type: 'number' });
node('span', 'viewer-page-count');
node('button', 'viewer-zoom-out');
node('button', 'viewer-zoom-in');
node('button', 'viewer-fit');
node('div', 'viewer-canvas');
node('pre', 'viewer-text');
node('p', 'viewer-empty');
node('p', 'viewer-message');
node('button', 'selection-ask');
node('h2', 'documents-title');
node('p', 'documents-empty');
node('ul', 'document-list');
node('p', 'documents-message');
node('p', 'documents-live');
const byId = (id) => document.getElementById(id);
const settle = () => new Promise((resolve) => setTimeout(resolve, 30));
const { createStore, INITIAL_STATE } = await import('/js/state.js');
const { createApi } = await import('/js/api.js');
const { createViewerActions } = await import('/js/actions/viewer.js');
const { mountViewerView } = await import('/js/views/viewer.js');
const { mountDocumentsView } = await import('/js/views/documents.js');
const { t } = await import('/js/i18n.js');
const text = (answer) => ({ ok: true, text: async () => answer });
const json = (body) => ({ ok: true, json: async () => body });
const passagesOf = (pages) => ({ ok: true, json: async () => ({ pages }) });
// A fake viewer factory: every call of the viewer is logged in order. A behaviour can be a value or
// a function (open, highlight) or a count of failing creations (createFailures).
function fakeFactory(log, behaviour = {}) {
  const created = [];
  let failures = behaviour.createFailures ?? 0;
  const factory = async (container, options) => {
    log.push(['create']);
    if (failures > 0) {
      failures -= 1;
      throw new Error('create_failed');
    }
    const viewer = {
      options,
      page: 1,
      zoomValue: 'fit',
      scaleValue: behaviour.scale ?? 1,
      async open(url) {
        log.push(['open', url]);
        if (behaviour.open) return behaviour.open(url);
        if (behaviour.openError) throw new Error('load_failed');
        return { pageCount: 3 };
      },
      goToPage(number) { log.push(['goToPage', number]); this.page = number; },
      currentPage() { return this.page; },
      setZoom(value) {
        log.push(['setZoom', value]);
        this.zoomValue = value;
        if (value !== 'fit') this.scaleValue = value;
      },
      zoom() { return this.zoomValue; },
      scale() { return this.scaleValue; },
      highlightArgs: [],
      async highlight(sentence, args) {
        log.push(['highlight', sentence]);
        this.highlightArgs.push(args);
        const outcome = behaviour.highlight ?? true;
        return typeof outcome === 'function' ? outcome(sentence) : outcome;
      },
      clearHighlight() { log.push(['clearHighlight']); },
      destroy() { log.push(['destroy']); },
    };
    // An older viewer has no scale(); the view must still work.
    if (behaviour.noScale) delete viewer.scale;
    created.push(viewer);
    return viewer;
  };
  return { factory, created };
}
const DOCUMENTS = [
  { id: 'd1', filename: 'a.pdf', kind: 'pdf', has_original: true, page_count: 3 },
  { id: 'd2', filename: 'old.pdf', kind: 'pdf', has_original: false, page_count: 2 },
  { id: 't1', filename: 'notes.txt', kind: 'text', has_original: true, page_count: null },
  { id: 't2', filename: 'broken.txt', kind: 'text', has_original: true, page_count: null },
];
"""


def test_pdf_document_is_opened_from_its_file_url(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        store.set({ openDocId: 'd1' });
        await settle();
        return {
          log,
          status: store.get().viewerStatus,
          toolbarHidden: byId('viewer-toolbar').hidden,
          pageCount: byId('viewer-page-count').textContent,
          title: byId('viewer-title').textContent,
          created: created.length,
        };
        """,
    )
    assert result["log"][:2] == [["create"], ["open", "/api/collections/c1/documents/d1/file"]]
    assert result["status"] == "ready"
    assert result["toolbarHidden"] is False
    assert result["pageCount"].endswith("3")
    assert result["title"] == "a.pdf"


def test_open_page_moves_to_the_page_then_marks_the_sentence(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openPage({ docId: 'd1', page: 3, text: 'x' });
        await settle();
        actions.viewer.openPage({ docId: 'd1', page: 2, text: null });
        await settle();
        return { log: log.slice(2), activePane: store.get().activePane, highlight: store.get().highlight };
        """,
    )
    assert result["log"] == [
        ["goToPage", 3],
        ["highlight", "x"],
        ["goToPage", 2],
        ["clearHighlight"],
    ]
    assert result["activePane"] == "viewer"
    assert result["highlight"] is None


def test_a_sentence_is_searched_from_the_page_it_was_cited_on(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openPage({ docId: 'd1', page: 3, text: 'x' });
        await settle();
        return { args: created[0].highlightArgs };
        """,
    )
    assert result == {"args": [{"page": 3}]}


def test_a_related_page_opened_again_after_the_reader_scrolled_away_moves_again(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openPage({ docId: 'd1', page: 2, text: null });
        await settle();
        // The reader scrolls to page 3; the viewer reports it.
        created[0].page = 3;
        created[0].options.onPage(3);
        const before = log.length;
        actions.viewer.openPage({ docId: 'd1', page: 2, text: null });
        await settle();
        return { added: log.slice(before), page: byId('viewer-page').value };
        """,
    )
    assert result["added"] == [["goToPage", 2], ["clearHighlight"]]
    assert result["page"] == "2"


def test_opening_the_open_document_again_goes_back_to_its_first_page(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        created[0].page = 3;
        created[0].options.onPage(3);
        const before = log.length;
        actions.viewer.openDocument('d1');
        await settle();
        return { added: log.slice(before), page: byId('viewer-page').value };
        """,
    )
    assert result["added"] == [["goToPage", 1], ["clearHighlight"]]
    assert result["page"] == "1"


def test_sentence_that_cannot_be_marked_shows_the_message(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log, { highlight: false });
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openPage({ docId: 'd1', page: 1, text: 'olmayan cümle' });
        await settle();
        return { shown: byId('viewer-message').textContent, hidden: byId('viewer-message').hidden,
          expected: t('viewer.noHighlight') };
        """,
    )
    assert result["shown"] == result["expected"]
    assert result["hidden"] is False


def test_old_document_without_original_creates_no_viewer(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => json({ pages: [{ page: null, text: 'Eski metin' }] }) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d2');
        await settle();
        return { created: created.length, log, status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent, expected: t('viewer.oldDocument') };
        """,
    )
    assert result["created"] == 0
    assert result["log"] == []
    assert result["status"] == "old"
    assert result["shown"] == result["expected"]


def test_rejected_pdf_open_shows_that_the_file_cannot_be_shown(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        return { status: store.get().viewerStatus, shown: byId('viewer-message').textContent,
          expected: t('viewer.cantShow') };
        """,
    )
    assert result["status"] == "failed"
    assert result["shown"] == result["expected"]


def test_text_document_is_shown_as_text_never_as_markup(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('Merhaba <b>dünya</b>') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('t1');
        await settle();
        const pre = byId('viewer-text');
        return { created: created.length, shown: pre.textContent, elements: pre.children.length,
          hidden: pre.hidden, status: store.get().viewerStatus };
        """,
    )
    assert result["created"] == 0
    assert result["shown"] == "Merhaba <b>dünya</b>"
    assert result["elements"] == 0
    assert result["hidden"] is False
    assert result["status"] == "text"


def test_text_fetch_failure_of_any_kind_shows_that_the_file_cannot_be_shown(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log);
        // A connection that drops mid-body rejects with a plain TypeError, not an ApiError.
        const api = createApi({ fetchImpl: async () => ({ ok: true, text: async () => { throw new TypeError('dropped'); } }) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('t2');
        await settle();
        return { status: store.get().viewerStatus, shown: byId('viewer-message').textContent,
          expected: t('viewer.cantShow') };
        """,
    )
    assert result["status"] == "failed"
    assert result["shown"] == result["expected"]


def test_selection_offers_the_text_as_a_question(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const drafts = [];
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft: (value) => drafts.push(value) } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const button = byId('selection-ask');
        const rect = { left: 10, top: 10, bottom: 20, right: 50 };
        const before = button.hidden;
        created[0].options.onSelection({ text: 'Seçilen <i>metin</i>', rect });
        const shown = button.hidden === false;
        button.click();
        const afterClick = button.hidden;
        created[0].options.onSelection(null);
        return { before, shown, drafts, afterClick, hiddenAgain: button.hidden };
        """,
    )
    assert result["before"] is True
    assert result["shown"] is True
    assert result["drafts"] == ["Seçilen <i>metin</i>"]
    assert result["afterClick"] is True
    assert result["hiddenAgain"] is True


def test_document_rows_open_their_document_and_mark_the_open_one(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const opened = [];
        const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
          collections: [{ id: 'c1', name: 'Belgelerim', document_count: 2 }],
          documents: DOCUMENTS.slice(0, 2), documentsLoaded: true });
        const actions = { documents: {}, uploads: {}, viewer: { openDocument: (id) => opened.push(id) } };
        mountDocumentsView(store, actions);
        const buttons = [...document.querySelectorAll('.doc-open')];
        const labels = buttons.map((button) => button.textContent);
        buttons[1].click();
        store.set({ openDocId: 'd1' });
        const rows = [...document.querySelectorAll('#document-list li')];
        return {
          opened,
          labels,
          current: rows.map((row) => row.getAttribute('aria-current')),
          openRows: rows.map((row) => row.classList.contains('doc-row-open')),
          expected: [t('documents.open', { name: 'a.pdf' }), t('documents.open', { name: 'old.pdf' })],
        };
        """,
    )
    assert result["labels"] == result["expected"]
    assert result["opened"] == ["d2"]
    assert result["current"] == ["true", None]
    assert result["openRows"] == [True, False]


def test_late_mark_does_not_overwrite_an_old_document(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        let release;
        const { factory } = fakeFactory(log, {
          highlight: () => new Promise((resolve) => { release = resolve; }),
        });
        const api = createApi({ fetchImpl: async () => passagesOf([{ page: null, text: 'Eski metin' }]) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openPage({ docId: 'd1', page: 2, text: 'x' });
        await settle();
        actions.viewer.openDocument('d2');
        await settle();
        release(false);
        await settle();
        return {
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          hidden: byId('viewer-message').hidden,
          expected: t('viewer.oldDocument'),
        };
        """,
    )
    assert result["status"] == "old"
    assert result["hidden"] is False
    assert result["shown"] == result["expected"]


def test_late_pdf_result_never_overwrites_a_text_document_opened_after_it(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        let releaseOpen;
        const { factory } = fakeFactory(log, {
          open: () => new Promise((resolve) => { releaseOpen = resolve; }),
        });
        const api = createApi({ fetchImpl: async () => text('Metin') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        actions.viewer.openDocument('t1');
        await settle();
        releaseOpen({ pageCount: 3 });
        await settle();
        return {
          log,
          status: store.get().viewerStatus,
          text: byId('viewer-text').textContent,
          canvasHidden: byId('viewer-canvas').hidden,
          toolbarHidden: byId('viewer-toolbar').hidden,
          messageHidden: byId('viewer-message').hidden,
        };
        """,
    )
    assert result["status"] == "text"
    assert result["text"] == "Metin"
    assert result["canvasHidden"] is True
    assert result["toolbarHidden"] is True
    assert result["messageHidden"] is True
    assert ["goToPage", 1] not in result["log"]


def test_superseded_open_rejection_never_shows_cant_show(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        let rejectOpen;
        const { factory } = fakeFactory(log, {
          open: () => new Promise((resolve, reject) => { rejectOpen = reject; }),
        });
        const api = createApi({ fetchImpl: async () => text('Metin') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        actions.viewer.openDocument('t1');
        await settle();
        rejectOpen(new Error('superseded'));
        await settle();
        return {
          status: store.get().viewerStatus,
          messageHidden: byId('viewer-message').hidden,
          shown: byId('viewer-message').textContent,
          cantShow: t('viewer.cantShow'),
        };
        """,
    )
    assert result["status"] == "text"
    assert result["messageHidden"] is True
    assert result["shown"] != result["cantShow"]


def test_language_switch_keeps_the_reader_on_their_page(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        // The reader scrolls to page 7; the viewer reports it.
        created[0].page = 7;
        created[0].options.onPage(7);
        const before = log.length;
        const other = store.get().lang === 'en' ? 'tr' : 'en';
        store.set({ lang: other });
        await settle();
        return { added: log.slice(before), page: byId('viewer-page').value };
        """,
    )
    assert result["added"] == []
    assert result["page"] == "7"


def test_failed_viewer_creation_is_tried_again_on_the_next_open(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log, { createFailures: 1 });
        const api = createApi({ fetchImpl: async () => text('Metin') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const first = store.get().viewerStatus;
        const firstShown = byId('viewer-message').textContent;
        actions.viewer.openDocument('t1');
        await settle();
        actions.viewer.openDocument('d1');
        await settle();
        return {
          first,
          firstShown,
          cantShow: t('viewer.cantShow'),
          second: store.get().viewerStatus,
          created: created.length,
        };
        """,
    )
    assert result["first"] == "failed"
    assert result["firstShown"] == result["cantShow"]
    assert result["second"] == "ready"
    assert result["created"] == 1


def test_open_button_keeps_the_focus_after_the_list_is_redrawn(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
          collections: [{ id: 'c1', name: 'Belgelerim', document_count: 2 }],
          documents: DOCUMENTS.slice(0, 2), documentsLoaded: true });
        const { createViewerActions: makeViewer } = await import('/js/actions/viewer.js');
        const actions = { documents: {}, uploads: {}, viewer: makeViewer({ store }) };
        mountDocumentsView(store, actions);
        const button = [...document.querySelectorAll('.doc-open')][1];
        button.focus();
        button.click();
        const focused = document.activeElement;
        return {
          isOpenButton: focused.classList.contains('doc-open'),
          docId: focused.dataset.docId,
          rowCurrent: focused.closest('li').getAttribute('aria-current'),
        };
        """,
    )
    assert result == {"isOpenButton": True, "docId": "d2", "rowCurrent": "true"}


def open_pdf_with_zoom(page, base_url, body, behaviour):
    """Run ``body`` after a PDF is open in the view; ``behaviour`` configures the fake viewer."""
    return run_js(
        page,
        base_url,
        BUILD
        + f"""
        const log = [];
        const {{ factory }} = fakeFactory(log, {behaviour});
        const api = createApi({{ fetchImpl: async () => text('') }});
        const store = createStore({{ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS }});
        const actions = {{ viewer: createViewerActions({{ api, store }}), ask: {{ setDraft() {{}} }} }};
        mountViewerView(store, actions, {{ createViewer: factory, api }});
        actions.viewer.openDocument('d1');
        await settle();
        const zoomed = () => log.filter(([name]) => name === 'setZoom').map(([, value]) => value);
        {body}
        """,
    )


def test_zoom_in_starts_from_the_real_scale_when_the_zoom_is_fit(page, base_url):
    result = open_pdf_with_zoom(
        page,
        base_url,
        "byId('viewer-zoom-in').click(); await settle(); return zoomed();",
        "{ scale: 1.4 }",
    )
    assert result == [1.75]


def test_zoom_out_starts_from_the_real_scale_when_the_zoom_is_fit(page, base_url):
    result = open_pdf_with_zoom(
        page,
        base_url,
        "byId('viewer-zoom-out').click(); await settle(); return zoomed();",
        "{ scale: 1.4 }",
    )
    assert result == [1.25]


def test_zoom_steps_are_clamped_to_the_limits(page, base_url):
    low = open_pdf_with_zoom(
        page,
        base_url,
        "byId('viewer-zoom-out').click(); await settle(); return zoomed();",
        "{ scale: 0.25 }",
    )
    high = open_pdf_with_zoom(
        page,
        base_url,
        "byId('viewer-zoom-in').click(); await settle(); return zoomed();",
        "{ scale: 4 }",
    )
    assert low == [0.25]
    assert high == [4]


def test_zoom_survives_a_viewer_without_scale_by_starting_from_one(page, base_url):
    result = open_pdf_with_zoom(
        page,
        base_url,
        """
        byId('viewer-zoom-in').click();
        await settle();
        byId('viewer-fit').click();
        await settle();
        return zoomed();
        """,
        "{ noScale: true }",
    )
    assert result == [1.25, "fit"]


def test_page_input_moves_to_the_entered_page_within_the_document(page, base_url):
    result = open_pdf_with_zoom(
        page,
        base_url,
        """
        const input = byId('viewer-page');
        const moves = [];
        for (const value of ['2', '9', '0']) {
          input.value = value;
          input.dispatchEvent(new Event('change'));
          moves.push(input.value);
        }
        const pages = log.filter(([name]) => name === 'goToPage').map(([, number]) => number);
        input.value = '';
        input.dispatchEvent(new Event('change'));
        const restored = input.value;
        const afterInvalid = log.filter(([name]) => name === 'goToPage').length;
        return { pages, moves, restored, afterInvalid };
        """,
        "{}",
    )
    # The document has three pages: 9 is kept at 3 and 0 at 1.
    assert result["pages"] == [1, 2, 3, 1]
    assert result["moves"] == ["2", "3", "1"]
    # An empty entry puts back the page the reader is on (1, after the last move).
    assert result["restored"] == "1"
    assert result["afterInvalid"] == 4


def test_set_page_and_clear_highlight_change_only_the_state(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createViewerActions } = await import('/js/actions/viewer.js');
        const store = createStore({ ...INITIAL_STATE });
        const actions = createViewerActions({ store });
        actions.setPage(4);
        const afterSetPage = { page: store.get().openPage, highlight: store.get().highlight };
        actions.openPage({ docId: 'd1', page: 2, text: 'x' });
        const marked = store.get().highlight !== null;
        actions.clearHighlight();
        return {
          afterSetPage,
          marked,
          highlight: store.get().highlight,
          page: store.get().openPage,
          openDocId: store.get().openDocId,
        };
        """,
    )
    assert result["afterSetPage"] == {"page": 4, "highlight": None}
    assert result["marked"] is True
    assert result["highlight"] is None
    assert result["page"] == 2
    assert result["openDocId"] == "d1"


def test_showing_the_pane_lays_out_a_pdf_opened_while_hidden_once(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS,
          activePane: 'documents' });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        const relayouts = () => log.filter(([name]) => name === 'setZoom').length;
        // Opened while the pane is hidden: no layout yet.
        store.set({ openDocId: 'd1', openPage: 2, highlight: null });
        await settle();
        const hidden = relayouts();
        const status = store.get().viewerStatus;
        store.set({ activePane: 'viewer' });
        await settle();
        const shown = relayouts();
        store.set({ activePane: 'documents' });
        await settle();
        store.set({ activePane: 'chat' });
        await settle();
        const leaving = relayouts();
        return { hidden, status, shown, leaving, pages: log.filter(([name]) => name === 'goToPage').map(([, n]) => n) };
        """,
    )
    assert result["status"] == "ready"
    assert result["hidden"] == 0
    assert result["shown"] == 1
    assert result["leaving"] == 1
    assert result["pages"][-1] == 2


def test_mount_with_no_open_document_shows_only_the_empty_hint(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        await settle();
        const hidden = (id) => byId(id).hidden;
        return {
          toolbar: hidden('viewer-toolbar'),
          canvas: hidden('viewer-canvas'),
          text: hidden('viewer-text'),
          message: hidden('viewer-message'),
          selection: hidden('selection-ask'),
          empty: hidden('viewer-empty'),
          emptyText: byId('viewer-empty').textContent,
          expected: t('viewer.empty'),
          status: store.get().viewerStatus,
          log,
        };
        """,
    )
    assert result["toolbar"] is True
    assert result["canvas"] is True
    assert result["text"] is True
    assert result["message"] is True
    assert result["selection"] is True
    assert result["empty"] is False
    assert result["emptyText"] == result["expected"]
    assert result["status"] == "idle"
    assert result["log"] == []


def test_reset_to_no_document_returns_to_the_empty_state_and_destroys_the_pdf(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const shownPdf = { canvas: byId('viewer-canvas').hidden, toolbar: byId('viewer-toolbar').hidden };
        // The open document is deleted: nothing is open any more.
        store.set({ openDocId: '' });
        await settle();
        const afterReset = {
          canvas: byId('viewer-canvas').hidden,
          toolbar: byId('viewer-toolbar').hidden,
          text: byId('viewer-text').hidden,
          empty: byId('viewer-empty').hidden,
          status: store.get().viewerStatus,
          destroyed: log.some(([name]) => name === 'destroy'),
        };
        // A later open creates a viewer again and shows the new document.
        actions.viewer.openDocument('d1');
        await settle();
        return { shownPdf, afterReset, created: created.length, reopened: store.get().viewerStatus };
        """,
    )
    assert result["shownPdf"] == {"canvas": False, "toolbar": False}
    after = result["afterReset"]
    assert after["canvas"] is True
    assert after["toolbar"] is True
    assert after["text"] is True
    assert after["empty"] is False
    assert after["status"] == "idle"
    assert after["destroyed"] is True
    assert result["created"] == 2
    assert result["reopened"] == "ready"


def test_reset_after_a_text_document_hides_the_text(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('Metin') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('t1');
        await settle();
        const shownText = byId('viewer-text').hidden;
        store.set({ openDocId: '' });
        await settle();
        return { shownText, textHidden: byId('viewer-text').hidden, emptyHidden: byId('viewer-empty').hidden };
        """,
    )
    assert result == {"shownText": False, "textHidden": True, "emptyHidden": False}


def test_viewer_heading_is_never_empty(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const { setLanguage } = await import('/js/i18n.js');
        const log = [];
        const { factory } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => text('Metin') });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        const heading = () => byId('viewer-title').textContent;
        const seen = {};
        seen.idle = heading();
        seen.idleExpected = t('panes.viewer');
        actions.viewer.openDocument('d1');
        await settle();
        seen.open = heading();
        store.set({ openDocId: '' });
        await settle();
        seen.reset = heading();
        const other = store.get().lang === 'en' ? 'tr' : 'en';
        setLanguage(other);
        store.set({ lang: other });
        await settle();
        seen.language = heading();
        seen.languageExpected = t('panes.viewer');
        seen.languageBefore = seen.idle;
        return seen;
        """,
    )
    assert result["idle"] == result["idleExpected"] != ""
    assert result["open"] == "a.pdf"
    assert result["reset"] == result["idleExpected"]
    assert result["language"] == result["languageExpected"] != ""
    assert result["language"] != result["languageBefore"]


PASSAGES = """
const PAGES = [
  { page: 1, text: 'Birinci sayfa metni' },
  { page: 2, text: 'İkinci sayfa\\n\\nikinci paragraf' },
];
"""


def test_rejected_pdf_open_shows_the_note_and_the_passages_with_dividers(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + PASSAGES
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        const api = createApi({ fetchImpl: async () => passagesOf(PAGES) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const pre = byId('viewer-text');
        const expected = [
          `${t('viewer.pageDivider', { page: 1 })}\\nBirinci sayfa metni`,
          `${t('viewer.pageDivider', { page: 2 })}\\nİkinci sayfa\\n\\nikinci paragraf`,
        ].join('\\n\\n');
        return {
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.cantShow'),
          text: pre.textContent,
          expected,
          preHidden: pre.hidden,
          canvasHidden: byId('viewer-canvas').hidden,
          elements: pre.children.length,
        };
        """,
    )
    assert result["status"] == "failed"
    assert result["shown"] == result["expectedNote"]
    assert result["preHidden"] is False
    assert result["canvasHidden"] is True
    assert result["elements"] == 0
    assert result["text"] == result["expected"]


def test_old_document_shows_its_note_and_the_passages_without_dividers_for_null_pages(
    page, base_url
):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({ fetchImpl: async () => passagesOf([{ page: null, text: 'Eski metin' }]) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d2');
        await settle();
        const pre = byId('viewer-text');
        return {
          created: created.length,
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.oldDocument'),
          text: pre.textContent,
          preHidden: pre.hidden,
        };
        """,
    )
    assert result["created"] == 0
    assert result["status"] == "old"
    assert result["shown"] == result["expectedNote"]
    assert result["preHidden"] is False
    assert result["text"] == "Eski metin"


def test_failing_passages_request_shows_only_the_cant_show_message(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        const api = createApi({
          fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({ detail: 'internal_error' }) }),
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        return {
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.cantShow'),
          hidden: byId('viewer-message').hidden,
          text: byId('viewer-text').textContent,
          textHidden: byId('viewer-text').hidden,
        };
        """,
    )
    assert result["status"] == "failed"
    assert result["shown"] == result["expectedNote"]
    assert result["hidden"] is False
    assert result["text"] == ""
    assert result["textHidden"] is True


def test_document_without_passages_shows_only_the_cant_show_message(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        const api = createApi({ fetchImpl: async () => passagesOf([]) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        return { status: store.get().viewerStatus, shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.cantShow'),
          textHidden: byId('viewer-text').hidden };
        """,
    )
    assert result["status"] == "failed"
    assert result["shown"] == result["expectedNote"]
    assert result["textHidden"] is True


def test_passage_html_is_shown_as_text_never_as_markup(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        const hostile = "<img src=x onerror=\\"window.__ran = true\\"><b>kalın</b>";
        const api = createApi({ fetchImpl: async () => passagesOf([{ page: 1, text: hostile }]) });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const pre = byId('viewer-text');
        return { text: pre.textContent, elements: pre.querySelectorAll('*').length, ran: window.__ran === true,
          expected: `${t('viewer.pageDivider', { page: 1 })}\n${hostile}` };
        """,
    )
    assert result["text"] == result["expected"]
    assert result["elements"] == 0
    assert result["ran"] is False


def test_superseded_pdf_failure_never_overwrites_a_newer_view(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + PASSAGES
        + """
        const log = [];
        let rejectOpen;
        const { factory } = fakeFactory(log, {
          open: () => new Promise((resolve, reject) => { rejectOpen = reject; }),
        });
        const api = createApi({
          fetchImpl: async (url) => (String(url).endsWith('/text') ? passagesOf(PAGES) : text('Metin')),
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        actions.viewer.openDocument('t1');
        await settle();
        rejectOpen(new Error('late'));
        await settle();
        return {
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          messageHidden: byId('viewer-message').hidden,
          text: byId('viewer-text').textContent,
        };
        """,
    )
    assert result["status"] == "text"
    assert result["messageHidden"] is True
    assert result["text"] == "Metin"


def test_superseded_passages_never_overwrite_a_newer_view(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + PASSAGES
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        let releasePassages;
        const api = createApi({
          fetchImpl: async (url) => {
            if (String(url).endsWith('/text')) {
              return new Promise((resolve) => { releasePassages = () => resolve(passagesOf(PAGES)); });
            }
            return text('Metin');
          },
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        actions.viewer.openDocument('t1');
        await settle();
        releasePassages();
        await settle();
        return {
          status: store.get().viewerStatus,
          text: byId('viewer-text').textContent,
          shown: byId('viewer-message').textContent,
          messageHidden: byId('viewer-message').hidden,
        };
        """,
    )
    assert result["status"] == "text"
    assert result["text"] == "Metin"
    assert result["messageHidden"] is True


def test_old_document_whose_passages_fail_keeps_its_note_and_hides_the_text(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        const api = createApi({
          fetchImpl: async () => ({ ok: false, status: 500, json: async () => ({ detail: 'internal_error' }) }),
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d2');
        await settle();
        return {
          created: created.length,
          status: store.get().viewerStatus,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.oldDocument'),
          text: byId('viewer-text').textContent,
          textHidden: byId('viewer-text').hidden,
        };
        """,
    )
    assert result["created"] == 0
    assert result["status"] == "old"
    assert result["shown"] == result["expectedNote"]
    assert result["text"] == ""
    assert result["textHidden"] is True


def test_language_switch_redraws_the_dividers_without_refetching(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + PASSAGES
        + """
        const { setLanguage } = await import('/js/i18n.js');
        setLanguage('tr');
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        let fetches = 0;
        const api = createApi({
          fetchImpl: async () => {
            fetches += 1;
            return passagesOf(PAGES);
          },
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS, lang: 'tr' });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const before = byId('viewer-text').textContent;
        setLanguage('en');
        store.set({ lang: 'en' });
        await settle();
        return {
          fetches,
          before,
          after: byId('viewer-text').textContent,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.cantShow'),
          expectedDivider: t('viewer.pageDivider', { page: 1 }),
        };
        """,
    )
    assert result["fetches"] == 1
    assert result["before"].startswith("Sayfa 1")
    assert result["after"].startswith("Page 1\nBirinci")
    assert "Sayfa" not in result["after"]
    assert result["shown"] == result["expectedNote"]


def test_passages_are_fetched_once_across_a_pane_switch(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + PASSAGES
        + """
        const log = [];
        const { factory } = fakeFactory(log, { openError: true });
        let fetches = 0;
        const api = createApi({
          fetchImpl: async () => {
            fetches += 1;
            return passagesOf(PAGES);
          },
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS, activePane: 'viewer' });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d1');
        await settle();
        const first = byId('viewer-text').textContent;
        store.set({ activePane: 'chat' });
        await settle();
        store.set({ activePane: 'viewer' });
        await settle();
        return {
          fetches,
          first,
          after: byId('viewer-text').textContent,
          textHidden: byId('viewer-text').hidden,
        };
        """,
    )
    assert result["fetches"] == 1
    assert result["after"] == result["first"]
    assert result["textHidden"] is False


def test_text_file_that_cannot_be_read_shows_its_passages_with_the_cant_show_note(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const log = [];
        const { factory, created } = fakeFactory(log);
        // The file read drops; the passages of the same document are still there.
        const api = createApi({
          fetchImpl: async (url) => (String(url).endsWith('/text')
            ? passagesOf([{ page: 1, text: 'Pasaj bir' }])
            : (() => { throw new TypeError('dropped'); })()),
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} } };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('t1');
        await settle();
        return {
          created: created.length,
          status: store.get().viewerStatus,
          text: byId('viewer-text').textContent,
          textHidden: byId('viewer-text').hidden,
          shown: byId('viewer-message').textContent,
          expectedNote: t('viewer.cantShow'),
          expectedText: `${t('viewer.pageDivider', { page: 1 })}\nPasaj bir`,
        };
        """,
    )
    assert result["created"] == 0
    assert result["status"] == "failed"
    assert result["text"] == result["expectedText"]
    assert result["textHidden"] is False
    assert result["shown"] == result["expectedNote"]


def test_passages_answering_document_not_found_close_the_viewer_and_reload_the_list(page, base_url):
    result = run_js(
        page,
        base_url,
        BUILD
        + """
        const { VIEWER_CLOSED } = await import('/js/state.js');
        const log = [];
        const { factory } = fakeFactory(log);
        // The old document has no original, so its passages are the only request: the document is gone.
        const api = createApi({
          fetchImpl: async () => ({ ok: false, status: 404, json: async () => ({ detail: 'document_not_found' }) }),
        });
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: DOCUMENTS });
        let reloads = 0;
        const documents = { loadDocuments: async () => { reloads += 1; } };
        const actions = { viewer: createViewerActions({ api, store }), ask: { setDraft() {} }, documents };
        mountViewerView(store, actions, { createViewer: factory, api });
        actions.viewer.openDocument('d2');
        await settle();
        const state = store.get();
        return {
          openDocId: state.openDocId,
          viewerStatus: state.viewerStatus,
          closedKeys: Object.keys(VIEWER_CLOSED).every((key) => state[key] === VIEWER_CLOSED[key]),
          messageHidden: byId('viewer-message').hidden,
          reloads,
        };
        """,
    )
    assert result["openDocId"] == ""
    assert result["viewerStatus"] == "idle"
    assert result["closedKeys"] is True
    assert result["messageHidden"] is True
    assert result["reloads"] == 1
