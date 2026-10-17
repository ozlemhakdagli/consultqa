"""Browser tests of the question thread: turns, scope, answer sources and the draft of a question."""

import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e

# A store with a ready folder, one document and one method, and a fake api that records requests.
SETUP = """
    const { createStore, INITIAL_STATE } = await import('/js/state.js');
    const { createAskActions } = await import('/js/actions/ask.js');
    const presets = [{ name: 'L2', available: true, reason: null, uses_llm: false }];
    const make = (api, patch = {}) => {
      const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
        selectedPreset: 'L2', documentsLoaded: true,
        documents: [{ id: 'd1', filename: 'ocak.md' }, { id: 'd2', filename: 'nisan.md' }],
        capabilities: { presets, default_preset: 'L2' }, ...patch });
      return { store, actions: createAskActions({ api, store }) };
    };
    const ANSWER = { answer: 'Cevap', citations: [], trace: [], preset: 'L2', latency_ms: 1, related: [] };
    const fresh = (tag, id) => { const node = document.createElement(tag); node.id = id; return node; };
"""

PAGE_TEXT = "Birinci cümle. Stok modülü performans iyileştirmesi yapıldı. Üçüncü cümle."


def _mount_result_area():
    """The answer area and the ask form, built in the page with the ids of the DOM contract."""
    return """
    const area = fresh('section', 'step-answer');
    const notice = fresh('p', 'llm-notice'); notice.hidden = true;
    const empty = fresh('p', 'result-empty');
    const loading = fresh('p', 'result-loading'); loading.hidden = true;
    const result = fresh('div', 'result');
    area.append(notice, empty, loading, result);
    document.body.append(area);
    const scopeSwitch = fresh('fieldset', 'scope-switch');
    for (const value of ['document', 'folder']) {
      const radio = fresh('input', `scope-${value}`);
      radio.type = 'radio'; radio.name = 'scope'; radio.value = value;
      scopeSwitch.append(radio);
    }
    const scopeNote = fresh('p', 'scope-note'); scopeNote.hidden = true;
    document.body.append(scopeSwitch, scopeNote);
    """


def test_ask_appends_a_pending_turn_then_fills_it(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const seen = [];
        const api = { ask: async () => { seen.push(store.get().thread.map((t) => t.pending)); await gate; return ANSWER; } };
        const { store, actions } = make(api);
        const running = actions.askQuestion('  Soru bir?  ');
        seen.push(store.get().thread.map((t) => t.question));
        release();
        await running;
        const [turn] = store.get().thread;
        return [seen, turn.question, turn.pending, turn.result.kind, turn.result.answer, turn.docId];
        """,
    )
    assert result == [
        [[True], ["Soru bir?"]],
        "Soru bir?",
        False,
        "answer",
        "Cevap",
        "",
    ]


def test_a_question_in_document_scope_carries_the_open_document(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        const sent = [];
        const api = { ask: async (cid, question, preset, docId) => { sent.push([cid, question, preset, docId]); return ANSWER; } };
        const { store, actions } = make(api, { openDocId: 'd2' });
        await actions.askQuestion('Birinci soru');
        actions.setScope('folder');
        await actions.askQuestion('İkinci soru');
        return [sent, store.get().thread.map((t) => t.docId)];
        """,
    )
    assert result == [
        [["c1", "Birinci soru", "L2", "d2"], ["c1", "İkinci soru", "L2", ""]],
        ["d2", ""],
    ]


def test_each_question_adds_a_turn_in_order(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        const api = { ask: async () => ANSWER };
        const { store, actions } = make(api);
        await actions.askQuestion('Bir');
        await actions.askQuestion('İki');
        const turns = store.get().thread;
        return [turns.map((t) => t.question), turns.map((t) => t.pending), turns[0].id !== turns[1].id];
        """,
    )
    assert result == [["Bir", "İki"], [False, False], True]


def test_setdraft_fills_the_question_box_and_does_not_submit(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountAskView } = await import('/js/views/ask-form.js');
        const form = fresh('form', 'ask-form');
        const question = fresh('textarea', 'question');
        const submit = fresh('button', 'ask-submit');
        const reason = fresh('p', 'ask-reason'); reason.hidden = true;
        const message = fresh('p', 'ask-message'); message.hidden = true;
        const examples = fresh('div', 'example-list');
        form.append(question, submit, reason, message, examples);
        document.body.append(form);
        let asked = 0;
        const api = { ask: async () => { asked += 1; return ANSWER; } };
        const { store, actions } = make(api);
        mountAskView(store, { ask: { ...actions, askQuestion: () => { asked += 1; } } });
        actions.setDraft('Garanti süresi ne kadar?');
        await new Promise((resolve) => requestAnimationFrame(() => resolve()));
        return [question.value, document.activeElement === question, asked];
        """,
    )
    assert result == ["Garanti süresi ne kadar?", True, 0]


# The question form, built with the ids of the DOM contract; the test mounts the view on it.
ASK_FORM_ELEMENTS = """
    const { mountAskView } = await import('/js/views/ask-form.js');
    const form = fresh('form', 'ask-form');
    const question = fresh('textarea', 'question');
    const submit = fresh('button', 'ask-submit');
    const reason = fresh('p', 'ask-reason'); reason.hidden = true;
    const message = fresh('p', 'ask-message'); message.hidden = true;
    const examples = fresh('div', 'example-list');
    form.append(question, submit, reason, message, examples);
    document.body.append(form);
"""

# The viewer pane, built with the ids of the DOM contract (index.html).
VIEWER_ELEMENTS = """
    const viewerNode = (tag, id) => { const node = fresh(tag, id); document.body.append(node); return node; };
    viewerNode('h2', 'viewer-title'); viewerNode('div', 'viewer-toolbar');
    viewerNode('input', 'viewer-page'); viewerNode('span', 'viewer-page-count');
    viewerNode('button', 'viewer-zoom-out'); viewerNode('button', 'viewer-zoom-in');
    viewerNode('button', 'viewer-fit'); viewerNode('div', 'viewer-canvas');
    viewerNode('pre', 'viewer-text'); viewerNode('p', 'viewer-empty');
    viewerNode('p', 'viewer-message'); viewerNode('button', 'selection-ask');
"""


def test_setdraft_opens_the_chat_pane_on_a_narrow_screen(page, base_url):
    page.set_viewport_size({"width": 800, "height": 900})
    result = run_js(
        page,
        base_url,
        SETUP
        + ASK_FORM_ELEMENTS
        + """
        const { store, actions } = make({ ask: async () => ANSWER }, { activePane: 'viewer' });
        mountAskView(store, { ask: actions });
        actions.setDraft('Garanti süresi ne kadar?');
        await new Promise((resolve) => requestAnimationFrame(() => resolve()));
        return [store.get().activePane, store.get().draft.text, document.activeElement === question];
        """,
    )
    assert result == ["chat", "Garanti süresi ne kadar?", True]


def test_setdraft_does_not_switch_the_pane_on_a_wide_screen(page, base_url):
    page.set_viewport_size({"width": 1280, "height": 900})
    result = run_js(
        page,
        base_url,
        SETUP
        + ASK_FORM_ELEMENTS
        + VIEWER_ELEMENTS
        + """
        const { createViewerActions } = await import('/js/actions/viewer.js');
        const { mountViewerView } = await import('/js/views/viewer.js');
        const log = [];
        const factory = async () => ({
          page: 1, zoomValue: 'fit',
          async open() { log.push('open'); return { pageCount: 3 }; },
          goToPage(number) { this.page = number; },
          currentPage() { return this.page; },
          setZoom() { log.push('setZoom'); },
          zoom() { return this.zoomValue; },
          scale() { return 1; },
          async highlight() { return true; },
          clearHighlight() {},
          destroy() {},
        });
        const api = {
          documentFileUrl: () => '/file',
          documentText: async () => '',
        };
        const documents = [{ id: 'd1', filename: 'ocak.pdf', kind: 'pdf', has_original: true, page_count: 3 }];
        const { store, actions } = make({ ask: async () => ANSWER }, { activePane: 'viewer', documents });
        const viewer = createViewerActions({ api, store });
        mountAskView(store, { ask: actions });
        mountViewerView(store, { viewer, ask: actions }, { createViewer: factory, api });
        viewer.openPage({ docId: 'd1', page: 1, text: null });
        await new Promise((resolve) => setTimeout(resolve, 50));
        const before = log.length;
        actions.setDraft('Garanti süresi ne kadar?');
        await new Promise((resolve) => requestAnimationFrame(() => resolve()));
        const paneAfterDraft = store.get().activePane;
        viewer.openPage({ docId: 'd1', page: 2, text: null });
        await new Promise((resolve) => setTimeout(resolve, 50));
        return [paneAfterDraft, log.slice(before).filter((entry) => entry === 'setZoom').length];
        """,
    )
    assert result == ["viewer", 0]


def test_renderanswer_gives_a_page_button_that_opens_the_marked_sentence(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { renderAnswer } = await import('/js/views/answer.js');
        const calls = [];
        const names = new Map([['d1', 'ocak.md']]);
        const answer = {
          kind: 'answer', preset: 'L2', isRecommended: true, usesLlm: false,
          answer: 'performans iyileştirmesi yapıldı',
          citations: [{ number: 1, doc_id: 'd1', page: 2, heading_path: [], text: '"""
        + PAGE_TEXT
        + """' }],
          related: [],
        };
        const nodes = renderAnswer(answer, names, (args) => calls.push(args));
        const holder = document.createElement('div');
        holder.append(...nodes.filter(Boolean));
        document.body.append(holder);
        const button = holder.querySelector('.page-button');
        const label = button.textContent;
        const aria = button.getAttribute('aria-label');
        button.click();
        return [label, aria, calls];
        """,
    )
    assert result == [
        "Sayfa 2",
        "Sayfa 2: ocak.md belgesinde göster",
        [
            {
                "docId": "d1",
                "page": 2,
                "text": "Stok modülü performans iyileştirmesi yapıldı.",
            }
        ],
    ]


def test_renderanswer_gives_no_page_button_without_a_page(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { renderAnswer } = await import('/js/views/answer.js');
        const answer = {
          kind: 'answer', preset: 'L2', isRecommended: true, usesLlm: true,
          answer: 'Cevap', citations: [{ number: 1, doc_id: 'd1', page: null, heading_path: [], text: 'Metin' }],
          related: [],
        };
        const holder = document.createElement('div');
        holder.append(...renderAnswer(answer, new Map(), () => {}).filter(Boolean));
        return holder.querySelectorAll('.page-button').length;
        """,
    )
    assert result == 0


def test_related_pages_are_listed_once_per_page(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { renderAnswer } = await import('/js/views/answer.js');
        const calls = [];
        const names = new Map([['d1', 'ocak.md'], ['d2', 'nisan.md']]);
        const related = (doc_id, pageNo) => ({ chunk_id: 'x', doc_id, page: pageNo, heading_path: [] });
        const answer = (list) => ({
          kind: 'answer', preset: 'L5', isRecommended: true, usesLlm: true,
          answer: 'Cevap', citations: [], related: list,
        });
        const one = document.createElement('div');
        one.append(...renderAnswer(answer([related('d1', 3), related('d1', 3), related('d1', 4), related('d1', null)]),
          names, (args) => calls.push(args)).filter(Boolean));
        const many = document.createElement('div');
        many.append(...renderAnswer(answer([related('d1', 3), related('d2', 3)]),
          names, (args) => calls.push(args)).filter(Boolean));
        const oneButtons = [...one.querySelectorAll('.related-list .page-button')];
        const manyButtons = [...many.querySelectorAll('.related-list .page-button')];
        oneButtons[0].click();
        manyButtons[1].click();
        return [
          one.querySelector('.related-pages h3').textContent,
          oneButtons.map((b) => b.textContent),
          manyButtons.map((b) => b.textContent),
          calls,
        ];
        """,
    )
    assert result == [
        "İlgili sayfalar",
        ["Sayfa 3", "Sayfa 4"],
        ["Sayfa 3: ocak.md", "Sayfa 3: nisan.md"],
        [
            {"docId": "d1", "page": 3, "text": None},
            {"docId": "d2", "page": 3, "text": None},
        ],
    ]


def test_a_question_with_markup_is_shown_as_text(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const hostile = '<img src=x onerror=alert(1)>';
        const api = { ask: async () => ANSWER };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion(hostile);
        const container = document.getElementById('result');
        const question = container.querySelector('.turn-question');
        return [question.textContent, container.querySelectorAll('img').length];
        """,
    )
    assert result == ["<img src=x onerror=alert(1)>", 0]


def test_the_thread_shows_one_section_per_turn_with_its_scope(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const api = { ask: async () => ANSWER };
        const { store, actions } = make(api, { openDocId: 'd1' });
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion('Bir');
        actions.setScope('folder');
        await actions.askQuestion('İki');
        const turns = [...document.querySelectorAll('#result > section.turn')];
        return [
          turns.map((turn) => turn.querySelector('.turn-question').textContent),
          turns.map((turn) => turn.querySelector('.turn-scope').textContent),
        ];
        """,
    )
    assert result == [["Bir", "İki"], ["ocak.md içinde", "Tüm klasörde"]]


def test_scope_radios_follow_the_open_document(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountScopeView } = await import('/js/views/scope.js');
        const { store, actions } = make({ ask: async () => ANSWER });
        mountScopeView(store, { ask: actions });
        const document_ = document.getElementById('scope-document');
        const folder = document.getElementById('scope-folder');
        const note = document.getElementById('scope-note');
        const closed = [document_.disabled, folder.disabled, folder.checked, note.hidden];
        store.set({ openDocId: 'd1' });
        const open = [document_.disabled, document_.checked, folder.checked, note.hidden];
        folder.click();
        return [closed, open, store.get().scope];
        """,
    )
    assert result == [[True, False, True, False], [False, True, False, True], "folder"]


ASK_FORM = """
    const { mountAskView } = await import('/js/views/ask-form.js');
    const form = fresh('form', 'ask-form');
    const question = fresh('textarea', 'question');
    question.maxLength = 500;
    const submit = fresh('button', 'ask-submit');
    const reason = fresh('p', 'ask-reason'); reason.hidden = true;
    const message = fresh('p', 'ask-message'); message.hidden = true;
    const examples = fresh('div', 'example-list');
    form.append(question, submit, reason, message, examples);
    document.body.append(form);
    let asked = 0;
    const { store, actions } = make({ ask: async () => { asked += 1; return ANSWER; } });
    mountAskView(store, actions);
"""


def test_a_draft_longer_than_the_limit_is_cut_to_it(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + ASK_FORM
        + """
        actions.setDraft('a'.repeat(600));
        return [question.value.length, asked];
        """,
    )
    assert result == [500, 0]


def test_focus_moves_to_the_newest_answer_and_stays_on_unrelated_renders(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { store, actions } = make({ ask: async () => ANSWER });
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion('Soru');
        const title = document.querySelector('#result .turn:last-child .result-title');
        const focused = document.activeElement === title;
        store.set({ documents: store.get().documents.slice() });
        return [focused, document.activeElement === title, title.textContent];
        """,
    )
    assert result == [True, True, "Cevap"]


def test_the_newest_turn_is_kept_in_view(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        area.style.cssText = 'height:300px;overflow:auto;';
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        let slow = false;
        const api = { ask: async () => { if (slow) await gate; return ANSWER; } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        for (let i = 0; i < 5; i += 1) await actions.askQuestion('Soru ' + i);
        const inView = (node) => {
          const r = node.getBoundingClientRect();
          const a = area.getBoundingClientRect();
          return r.top >= a.top - 1 && r.bottom <= a.bottom + 1;
        };
        slow = true;
        const frames = async (count) => {
          for (let i = 0; i < count; i += 1) {
            await new Promise((resolve) => requestAnimationFrame(() => resolve()));
          }
        };
        const running = actions.askQuestion('Bekleyen');
        await frames(2);
        const busy = document.querySelector('#result .turn-busy');
        const busyText = busy.textContent.length > 0;
        const busyVisible = inView(busy);
        release();
        await running;
        await frames(2);
        const done = document.querySelector('#result .turn:last-child');
        return [area.scrollTop > 0, busyText, busyVisible, inView(done)];
        """,
    )
    assert result == [True, True, True, True]


def test_a_document_deleted_elsewhere_closes_the_viewer_and_reloads_the_list(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        const { ApiError } = await import('/js/errors.js');
        const { VIEWER_CLOSED } = await import('/js/state.js');
        const api = { ask: async () => { throw new ApiError('document_not_found', 404, {}); } };
        const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
          selectedPreset: 'L2', documentsLoaded: true, scope: 'document', openDocId: 'd1',
          documents: [{ id: 'd1', filename: 'ocak.md' }, { id: 'd2', filename: 'nisan.md' }],
          capabilities: { presets, default_preset: 'L2' } });
        let reloads = 0;
        const documents = { loadDocuments: async () => { reloads += 1; } };
        const actions = createAskActions({ api, store, documents });
        await actions.askQuestion('Soru');
        const state = store.get();
        return {
          openDocId: state.openDocId,
          viewerStatus: state.viewerStatus,
          closedKeys: Object.keys(VIEWER_CLOSED).every((key) => state[key] === VIEWER_CLOSED[key]),
          reloads,
          code: state.thread[0].result.code,
        };
        """,
    )
    assert result == {
        "openDocId": "",
        "viewerStatus": "idle",
        "closedKeys": True,
        "reloads": 1,
        "code": "document_not_found",
    }


def test_a_not_found_of_a_folder_question_keeps_the_open_document(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        const { ApiError } = await import('/js/errors.js');
        const api = { ask: async () => { throw new ApiError('document_not_found', 404, {}); } };
        const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
          selectedPreset: 'L2', documentsLoaded: true, scope: 'folder', openDocId: 'd2',
          documents: [{ id: 'd1', filename: 'ocak.md' }, { id: 'd2', filename: 'nisan.md' }],
          capabilities: { presets, default_preset: 'L2' } });
        let reloads = 0;
        const documents = { loadDocuments: async () => { reloads += 1; } };
        const actions = createAskActions({ api, store, documents });
        await actions.askQuestion('Soru');
        return [store.get().openDocId, reloads];
        """,
    )
    assert result == ["d2", 1]


def test_a_failed_request_shows_the_error_card(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { ApiError } = await import('/js/errors.js');
        const { errorMessage } = await import('/js/errors.js');
        const { t } = await import('/js/i18n.js');
        const api = { ask: async () => { throw new ApiError('busy', 429, { detail: 'busy' }); } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion('Soru');
        const card = document.querySelector('#result .error-card');
        return [
          card !== null,
          card.getAttribute('role'),
          card.textContent.includes(t('result.error.title')),
          card.textContent.includes(errorMessage('busy')),
          document.querySelector('#result .turn-busy'),
        ];
        """,
    )
    assert result == [True, "alert", True, True, None]


def test_an_unexpected_failure_ends_in_the_internal_error_card(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { errorMessage } = await import('/js/errors.js');
        const api = { ask: async () => { throw new TypeError('boom'); } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion('Soru').catch(() => {});
        const turn = store.get().thread[0];
        const card = document.querySelector('#result .error-card');
        return [turn.pending, turn.result.code, card.textContent.includes(errorMessage('internal_error'))];
        """,
    )
    assert result == [False, "internal_error", True]


def test_an_older_error_card_is_not_an_alert_and_is_not_rebuilt(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { ApiError } = await import('/js/errors.js');
        const replies = [
          () => { throw new ApiError('busy', 429, { detail: 'busy' }); },
          () => ANSWER,
        ];
        const api = { ask: async () => replies.shift()() };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        await actions.askQuestion('Birinci');
        const first = document.querySelector('#result .error-card');
        await actions.askQuestion('İkinci');
        return [
          document.querySelector('#result .error-card') === first,
          first.isConnected,
          first.getAttribute('role'),
          document.querySelectorAll('#result .turn').length,
        ];
        """,
    )
    assert result == [True, True, None, 2]


def test_the_pending_turn_shows_its_question_and_a_busy_line(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { t } = await import('/js/i18n.js');
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const api = { ask: async () => { await gate; return ANSWER; } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        const running = actions.askQuestion('Bekleyen soru');
        await new Promise((resolve) => requestAnimationFrame(() => resolve()));
        const busy = document.querySelector('#result .turn-busy');
        const out = [
          document.querySelector('#result .turn-question').textContent,
          busy.textContent === t('ask.loading'),
          busy.getAttribute('role'),
          document.querySelectorAll('#result .answer-card').length,
        ];
        release();
        await running;
        out.push(document.querySelectorAll('#result .turn-busy').length);
        return out;
        """,
    )
    assert result == ["Bekleyen soru", True, "status", 0, 0]


def test_the_empty_hint_and_the_loading_line_follow_the_state(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const api = { ask: async () => { await gate; return ANSWER; } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        const holder = document.getElementById('result');
        const out = [empty.hidden, loading.hidden];
        const running = actions.askQuestion('Soru');
        out.push(empty.hidden, loading.hidden, holder.getAttribute('aria-busy'));
        release();
        await running;
        out.push(empty.hidden, holder.getAttribute('aria-busy'));
        return out;
        """,
    )
    assert result == [False, True, True, True, None, True, None]


def test_the_busy_line_is_a_status_before_its_text_and_the_result_is_never_busy(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { t } = await import('/js/i18n.js');
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const api = { ask: async () => { await gate; return ANSWER; } };
        const { store, actions } = make(api);
        mountThreadView(store, { viewer: { openPage() {} } });
        const running = actions.askQuestion('Soru');
        const status = document.querySelector('#result .turn-busy');
        const before = [
          status !== null,
          status.getAttribute('role'),
          status.textContent,
          status.isConnected,
        ];
        await new Promise((resolve) => requestAnimationFrame(() => resolve()));
        const after = status.textContent === t('ask.loading');
        const busyLines = document.querySelectorAll('#result .turn-busy').length;
        const resultBusy = document.getElementById('result').getAttribute('aria-busy');
        release();
        await running;
        return [
          before,
          after,
          busyLines,
          resultBusy,
          document.getElementById('result').getAttribute('aria-busy'),
          document.getElementById('result-loading').textContent,
        ];
        """,
    )
    assert result == [[True, "status", "", True], True, 1, None, None, ""]


def test_the_llm_notice_shows_only_when_the_llm_is_off(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + _mount_result_area()
        + """
        const { mountThreadView } = await import('/js/views/thread.js');
        const { t } = await import('/js/i18n.js');
        const { store, actions } = make({ ask: async () => ANSWER });
        mountThreadView(store, { viewer: { openPage() {} } });
        const before = notice.hidden;
        store.set({ capabilities: { presets, default_preset: 'L2', llm_configured: false } });
        return [before, notice.hidden, notice.textContent === t('answer.llmOff')];
        """,
    )
    assert result == [True, False, True]


def test_a_second_question_while_one_is_in_flight_is_ignored(page, base_url):
    result = run_js(
        page,
        base_url,
        SETUP
        + """
        let calls = 0;
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const api = { ask: async () => { calls += 1; await gate; return ANSWER; } };
        const { store, actions } = make(api);
        const first = actions.askQuestion('Bir');
        await actions.askQuestion('İki');
        release();
        await first;
        return [calls, store.get().thread.map((turn) => turn.question)];
        """,
    )
    assert result == [1, ["Bir"]]


def test_the_page_button_name_starts_with_its_visible_text(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { renderAnswer } = await import('/js/views/answer.js');
        const answer = {
          kind: 'answer', preset: 'L2', isRecommended: true, usesLlm: true,
          answer: 'Cevap', citations: [{ number: 1, doc_id: 'd1', page: 2, heading_path: [], text: 'Metin' }],
          related: [{ chunk_id: 'x', doc_id: 'd1', page: 5, heading_path: [] }],
        };
        const holder = document.createElement('div');
        holder.append(...renderAnswer(answer, new Map([['d1', 'ocak.md']]), () => {}).filter(Boolean));
        const buttons = [...holder.querySelectorAll('button.page-button')];
        return [
          buttons.map((b) => b.getAttribute('aria-label').startsWith(b.textContent)),
          holder.querySelectorAll('[id]').length,
        ];
        """,
    )
    assert result == [[True, True], 0]
