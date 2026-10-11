"""Browser tests of the frontend's plain modules, imported one by one in headless Chrome."""

import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e


def test_t_fills_placeholders_and_falls_back_to_the_key(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { t, has } = await import('/js/i18n.js');
        return [t('collection.created', { name: 'Kılavuzlar' }), t('no.such.key'),
                has('app.title'), has('no.such.key')];
    """,
    )
    assert result == [
        "“Kılavuzlar” koleksiyonu oluşturuldu. Şimdi 2. adımda belge yükleyebilirsiniz.",
        "no.such.key",
        True,
        False,
    ]


def test_apply_static_text_sets_text_and_placeholders(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { applyStaticText } = await import('/js/i18n.js');
        const root = document.createElement('div');
        const heading = document.createElement('h1');
        heading.setAttribute('data-text', 'app.title');
        const input = document.createElement('input');
        input.setAttribute('data-placeholder', 'ask.questionPlaceholder');
        root.append(heading, input);
        applyStaticText(root);
        return [heading.textContent, input.placeholder];
    """,
    )
    assert result == ["Belge Soru-Cevap", "Örneğin: Bu belgede garanti süresi kaç yıl?"]


def test_el_never_parses_html_and_by_id_fails_loudly(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { el, byId, setVisible } = await import('/js/dom.js');
        const node = el('p', { text: '<img src=x onerror=1>', class: 'a', attrs: { id: 'p1' } }, '<b>x</b>');
        document.body.append(node);
        setVisible(node, false);
        let message = '';
        try { byId('nope'); } catch (error) { message = error.message; }
        return [node.children.length, node.textContent, node.hidden, byId('p1') === node, message];
    """,
    )
    assert result == [0, "<img src=x onerror=1><b>x</b>", True, True, "missing element #nope"]


def test_show_message_sets_text_class_and_visibility(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { el, showMessage } = await import('/js/dom.js');
        const node = el('p');
        showMessage(node, { kind: 'error', text: 'Hata' });
        const shown = [node.textContent, node.className, node.hidden];
        showMessage(node, null);
        return [shown, node.hidden];
    """,
    )
    assert result == [["Hata", "message message-error", False], True]


def test_error_message_maps_codes_and_falls_back(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { errorMessage, ApiError } = await import('/js/errors.js');
        const error = new ApiError('busy', 429, { detail: 'busy' });
        return [errorMessage('collection_exists'), errorMessage('nope'),
                error.code, error.status, error instanceof Error];
    """,
    )
    assert result == [
        "Bu adda bir koleksiyon zaten var. Başka bir ad yazın veya listeden onu seçin.",
        "Beklenmeyen bir hata oluştu.",
        "busy",
        429,
        True,
    ]


def test_split_markers_handles_lists_and_ignores_array_indexes(page, base_url):
    parts = run_js(
        page,
        base_url,
        """
        const { splitMarkers } = await import('/js/markers.js');
        return splitMarkers('Stok [1, 2] var; arr[3] değil. Son [2].');
    """,
    )
    assert parts == [
        {"type": "text", "value": "Stok "},
        {"type": "marker", "numbers": [1, 2]},
        {"type": "text", "value": " var; arr[3] değil. Son "},
        {"type": "marker", "numbers": [2]},
        {"type": "text", "value": "."},
    ]


def test_split_markers_without_markers_and_empty_text(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { splitMarkers } = await import('/js/markers.js');
        return [splitMarkers('Cevap'), splitMarkers('')];
    """,
    )
    assert result == [[{"type": "text", "value": "Cevap"}], []]


def test_format_helpers_use_turkish_conventions(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const f = await import('/js/format.js');
        return [f.formatSeconds(420), f.formatSeconds(1234), f.formatScore(0.5),
                f.formatMegabytes(20),
                f.formatDateTime('2026-10-11T10:30:00+00:00').includes('2026'),
                f.formatDateTime('not a date')];
    """,
    )
    assert result == ["0,42", "1,23", "0,5000", "20", True, ""]


def test_store_notifies_only_watchers_of_changed_keys(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore } = await import('/js/state.js');
        const store = createStore({ a: 1, b: 1 });
        const seen = [];
        store.subscribe((state) => seen.push(['a', state.a]), ['a']);
        store.set({ b: 2 });
        store.set({ a: 2 });
        store.set({ a: 2 });
        return [seen, store.get().b];
    """,
    )
    assert result == [[["a", 1], ["a", 2]], 2]


def test_prefs_survive_blocked_storage(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { getPref, setPref } = await import('/js/prefs.js');
        setPref('collection', 'abc');
        const stored = getPref('collection');
        const original = Storage.prototype.getItem;
        Storage.prototype.getItem = () => { throw new Error('blocked'); };
        const blocked = getPref('collection');
        Storage.prototype.getItem = original;
        return [stored, blocked, getPref('never-set')];
    """,
    )
    assert result == ["abc", "", ""]


API_SETUP = """
    const { createApi } = await import('/js/api.js');
    const { ApiError } = await import('/js/errors.js');
    const reply = (status, body) => async () => ({ ok: status < 400, status, json: async () => body });
    const failure = async (fetchImpl) => {
      try { await createApi({ fetchImpl }).listCollections(); return null; }
      catch (error) { return [error instanceof ApiError, error.code, error.status]; }
    };
"""


def test_api_returns_json_and_raises_api_errors(page, base_url):
    result = run_js(
        page,
        base_url,
        API_SETUP
        + """
        const ok = await createApi({ fetchImpl: reply(200, [{ id: 'c1', name: 'A' }]) }).listCollections();
        return [
          ok,
          await failure(reply(409, { detail: 'collection_exists' })),
          await failure(async () => ({ ok: false, status: 502, json: async () => { throw new SyntaxError('x'); } })),
          await failure(async () => { throw new TypeError('Failed to fetch'); }),
          await failure(reply(503, { detail: 'llm_unavailable', trace: [1] })),
        ];
    """,
    )
    assert result == [
        [{"id": "c1", "name": "A"}],
        [True, "collection_exists", 409],
        [True, "internal_error", 502],
        [True, "network_error", 0],
        [True, "llm_unavailable", 503],
    ]


def test_api_ask_posts_json_and_keeps_the_trace_of_a_failed_answer(page, base_url):
    result = run_js(
        page,
        base_url,
        API_SETUP
        + """
        const calls = [];
        const fetchImpl = async (url, init) => {
          calls.push([url, init.method, JSON.parse(init.body)]);
          return { ok: false, status: 503, json: async () => ({ detail: 'llm_unavailable', trace: [{ rank: 1 }] }) };
        };
        try { await createApi({ fetchImpl }).ask('c 1', 'Soru?', 'L2'); }
        catch (error) { return [calls, error.code, error.body.trace]; }
    """,
    )
    assert result == [
        [["/api/collections/c%201/ask", "POST", {"question": "Soru?", "preset": "L2"}]],
        "llm_unavailable",
        [{"rank": 1}],
    ]


def test_api_delete_accepts_an_empty_204(page, base_url):
    result = run_js(
        page,
        base_url,
        API_SETUP
        + """
        const fetchImpl = async () => ({ ok: true, status: 204, json: async () => { throw new SyntaxError('empty'); } });
        return await createApi({ fetchImpl }).deleteDocument('c1', 'd1');
    """,
    )
    assert result == {}


def test_block_reasons_follow_the_order_of_the_steps(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { askBlockReason, uploadBlockReason } = await import('/js/selectors.js');
        const presets = [
          { name: 'L2', available: true, reason: null, uses_llm: false },
          { name: 'L4+llm', available: false, reason: 'llm_not_configured', uses_llm: true },
        ];
        const ok = { status: 'ready', selectedCollectionId: 'c', documents: [{ id: 'd' }],
                     documentsLoaded: true, selectedPreset: 'L2', capabilities: { presets } };
        return [
          askBlockReason(ok),
          askBlockReason({ ...ok, selectedCollectionId: '', status: 'loading' }),
          askBlockReason({ ...ok, status: 'loading' }),
          askBlockReason({ ...ok, documents: [] }),
          askBlockReason({ ...ok, selectedPreset: 'L4+llm' }),
          uploadBlockReason(ok),
          uploadBlockReason({ ...ok, selectedCollectionId: '' }),
          uploadBlockReason({ ...ok, status: 'loading' }),
        ];
    """,
    )
    assert result == [
        None,
        "Önce 1. adımda bir koleksiyon seçin.",
        "Sistem hazır olana kadar soru sorulamaz. Sayfanın üstündeki durum bilgisine bakın.",
        "Bu koleksiyonda belge yok. Önce 2. adımda en az bir belge yükleyin.",
        "Seçili yöntem kullanılamıyor. Başka bir yöntem seçin.",
        None,
        "Önce 1. adımda bir koleksiyon seçin veya oluşturun.",
        "Sistem hazır olana kadar belge yüklenemez. Sayfanın üstündeki durum bilgisine bakın.",
    ]


def test_pick_preset_and_document_names(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { pickPreset, documentNames } = await import('/js/selectors.js');
        const caps = { default_preset: 'L2', presets: [
          { name: 'L2', available: true }, { name: 'L3', available: true },
          { name: 'L4+llm', available: false } ] };
        return [pickPreset(caps, 'L3'), pickPreset(caps, 'L4+llm'), pickPreset(caps, ''),
                pickPreset(null, 'L2'), [...documentNames({ documents: [{ id: 'd1', filename: 'a.md' }] })]];
    """,
    )
    assert result == ["L3", "L2", "L2", "", [["d1", "a.md"]]]


def test_watch_until_ready_polls_through_loading_and_unreachable(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createSystemActions } = await import('/js/actions/system.js');
        const { ApiError } = await import('/js/errors.js');
        const caps = (ready) => ({ ready, default_preset: 'L2',
          presets: [{ name: 'L2', available: true, reason: null, uses_llm: false }] });
        const outcomes = [() => caps(false), () => { throw new ApiError('network_error'); }, () => caps(true)];
        const api = { capabilities: async () => outcomes.shift()() };
        const store = createStore({ ...INITIAL_STATE });
        const seen = [];
        store.subscribe((s) => seen.push(s.status), ['status']);
        let sleeps = 0;
        await createSystemActions({ api, store, sleep: async () => { sleeps += 1; } }).watchUntilReady();
        return [seen, sleeps, store.get().selectedPreset];
    """,
    )
    assert result == [["checking", "loading", "unreachable", "ready"], 2, "L2"]


def test_create_collection_selects_it_and_reports_errors(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createCollectionActions } = await import('/js/actions/collections.js');
        const { ApiError } = await import('/js/errors.js');
        let list = [];
        let fail = null;
        const api = {
          listCollections: async () => list,
          createCollection: async (name) => { if (fail) throw fail; const row = { id: 'c9', name }; list = [row]; return row; },
        };
        const loaded = [];
        const documents = { loadDocuments: async () => { loaded.push(store.get().selectedCollectionId); } };
        const store = createStore({ ...INITIAL_STATE });
        const actions = createCollectionActions({ api, store, documents });
        const blank = await actions.createCollection('   ');
        const blankMessage = store.get().collectionMessage;
        fail = new ApiError('collection_exists', 409, {});
        const duplicate = await actions.createCollection('Yeni');
        const duplicateMessage = store.get().collectionMessage;
        fail = null;
        const created = await actions.createCollection('Yeni');
        return [blank, blankMessage, duplicate, duplicateMessage, created,
                store.get().collectionMessage, store.get().selectedCollectionId, loaded];
    """,
    )
    assert result == [
        False,
        {"kind": "error", "text": "Lütfen koleksiyon için bir ad yazın."},
        False,
        {
            "kind": "error",
            "text": "Bu adda bir koleksiyon zaten var. Başka bir ad yazın veya listeden onu seçin.",
        },
        True,
        {
            "kind": "info",
            "text": "“Yeni” koleksiyonu oluşturuldu. Şimdi 2. adımda belge yükleyebilirsiniz.",
        },
        "c9",
        ["c9"],
    ]


def test_documents_of_a_previous_collection_never_overwrite_the_current_one(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createDocumentActions } = await import('/js/actions/documents.js');
        let release;
        const slow = new Promise((resolve) => { release = resolve; });
        const api = { listDocuments: async (cid) => {
          if (cid === 'a') { await slow; return [{ id: 'da', filename: 'a.md' }]; }
          return [{ id: 'db', filename: 'b.md' }];
        } };
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'a' });
        const actions = createDocumentActions({ api, store });
        const first = actions.loadDocuments();
        store.set({ selectedCollectionId: 'b' });
        await actions.loadDocuments();
        release();
        await first;
        return store.get().documents.map((d) => d.id);
    """,
    )
    assert result == ["db"]


def test_delete_needs_confirmation_and_reloads(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createDocumentActions } = await import('/js/actions/documents.js');
        let docs = [{ id: 'd1', filename: 'a.md', created_at: '2026-10-11T10:00:00+00:00' }];
        const deleted = [];
        const api = {
          listDocuments: async () => docs,
          deleteDocument: async (cid, id) => { deleted.push(id); docs = []; return {}; },
        };
        const store = createStore({ ...INITIAL_STATE, selectedCollectionId: 'c1', documents: docs });
        const actions = createDocumentActions({ api, store });
        actions.requestDelete('d1');
        const asked = store.get().confirmDeleteId;
        actions.cancelDelete();
        const cancelled = [store.get().confirmDeleteId, deleted.length];
        actions.requestDelete('d1');
        await actions.confirmDelete('d1');
        return [asked, cancelled, deleted, store.get().documents, store.get().confirmDeleteId,
                store.get().documentsMessage];
    """,
    )
    assert result == ["d1", ["", 0], ["d1"], [], "", {"kind": "info", "text": "“a.md” silindi."}]


UPLOAD_SETUP = """
    const { createStore, INITIAL_STATE } = await import('/js/state.js');
    const { createUploadActions } = await import('/js/actions/uploads.js');
    const { ApiError } = await import('/js/errors.js');
    const caps = { max_upload_mb: 1, extensions: ['.md', '.txt'] };
    const make = (api, extra = {}) => {
      const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1', capabilities: caps });
      const reloads = [];
      const documents = { loadDocuments: async () => { reloads.push(store.get().selectedCollectionId); } };
      const actions = createUploadActions({ api, store, documents, sleep: async () => {}, ...extra });
      return { store, actions, reloads };
    };
    const rowOf = (store) => store.get().uploads.map((r) => [r.phase, r.errorCode]);
"""


def test_upload_runs_through_the_job_states_and_reloads_documents(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        const states = ['queued', 'parsing', 'embedding', 'graph', 'done'];
        const api = {
          uploadDocument: async (cid, file, onProgress) => { onProgress(50, 100); return { job_id: 'j1', document_id: 'd1' }; },
          getJob: async () => ({ state: states.shift(), error: null, document_id: 'd1' }),
        };
        const { store, actions, reloads } = make(api);
        const phases = [];
        const percents = [];
        store.subscribe((s) => {
          const phase = s.uploads.map((r) => r.phase).join(',');
          if (phases.at(-1) !== phase) phases.push(phase);
          if (s.uploads[0]) percents.push(s.uploads[0].percent);
        }, ['uploads']);
        await actions.uploadFiles([new File(['x'], 'a.md')]);
        return [phases, percents.includes(50), store.get().uploads[0].name, reloads];
    """,
    )
    assert result == [
        ["", "sending", "queued", "parsing", "embedding", "graph", "done"],
        True,
        "a.md",
        ["c1"],
    ]


def test_upload_reports_a_duplicate_and_a_server_failure(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        const jobs = [{ state: 'done', error: null, document_id: 'other' },
                      { state: 'failed', error: 'parse_failed', document_id: 'd1' }];
        const api = {
          uploadDocument: async () => ({ job_id: 'j', document_id: 'd1' }),
          getJob: async () => jobs.shift(),
        };
        const { store, actions, reloads } = make(api);
        await actions.uploadFiles([new File(['x'], 'a.md'), new File(['y'], 'b.md')]);
        return [rowOf(store), reloads];
    """,
    )
    assert result == [[["duplicate", None], ["failed", "parse_failed"]], ["c1"]]


def test_upload_refuses_bad_files_before_sending(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        let sent = 0;
        const api = { uploadDocument: async () => { sent += 1; return { job_id: 'j', document_id: 'd' }; } };
        const { store, actions } = make(api);
        await actions.uploadFiles([
          new File(['x'], 'virus.exe'), new File([], 'bos.md'),
          new File([new Uint8Array(1.5 * 1024 * 1024)], 'buyuk.md'),
        ]);
        await actions.uploadFiles([]);
        return [rowOf(store), sent, store.get().documentsMessage];
    """,
    )
    assert result == [
        [["failed", "unsupported_type"], ["failed", "file_empty"], ["failed", "file_too_large"]],
        0,
        {"kind": "error", "text": "Lütfen yüklenecek en az bir dosya seçin."},
    ]


def test_upload_turns_an_api_error_into_a_failed_row(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        const api = { uploadDocument: async () => { throw new ApiError('not_ready', 503, {}); } };
        const { store, actions } = make(api);
        await actions.uploadFiles([new File(['x'], 'a.md')]);
        return rowOf(store);
    """,
    )
    assert result == [["failed", "not_ready"]]


def test_upload_gives_up_on_a_job_that_never_finishes(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        let clock = 0;
        const api = {
          uploadDocument: async () => ({ job_id: 'j', document_id: 'd' }),
          getJob: async () => ({ state: 'parsing', error: null, document_id: 'd' }),
        };
        const { store, actions } = make(api, { now: () => (clock += 400000) });
        await actions.uploadFiles([new File(['x'], 'a.md')]);
        return rowOf(store);
    """,
    )
    assert result == [["failed", "job_timeout"]]


def test_upload_tolerates_two_failed_polls_but_not_three(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        const outcomes = (n) => {
          const list = Array.from({ length: n }, () => () => { throw new ApiError('network_error'); });
          list.push(() => ({ state: 'done', error: null, document_id: 'd' }));
          return list;
        };
        const run = async (n) => {
          const queue = outcomes(n);
          const api = {
            uploadDocument: async () => ({ job_id: 'j', document_id: 'd' }),
            getJob: async () => queue.shift()(),
          };
          const { store, actions } = make(api);
          await actions.uploadFiles([new File(['x'], 'a.md')]);
          return rowOf(store)[0];
        };
        return [await run(2), await run(3)];
    """,
    )
    assert result == [["done", None], ["failed", "network_error"]]


def test_documents_are_reloaded_only_when_the_collection_is_still_selected(page, base_url):
    result = run_js(
        page,
        base_url,
        UPLOAD_SETUP
        + """
        let store;
        const api = {
          uploadDocument: async () => { store.set({ selectedCollectionId: 'c2' }); return { job_id: 'j', document_id: 'd' }; },
          getJob: async () => ({ state: 'done', error: null, document_id: 'd' }),
        };
        const made = make(api);
        store = made.store;
        await made.actions.uploadFiles([new File(['x'], 'a.md')]);
        return [made.reloads, store.get().uploads[0].collectionId];
    """,
    )
    assert result == [[], "c1"]


ASK_SETUP = """
    const { createStore, INITIAL_STATE } = await import('/js/state.js');
    const { createAskActions } = await import('/js/actions/ask.js');
    const { ApiError } = await import('/js/errors.js');
    const presets = [{ name: 'L2', available: true, reason: null, uses_llm: false },
                     { name: 'L4+llm', available: true, reason: null, uses_llm: true }];
    const make = (api) => {
      const store = createStore({ ...INITIAL_STATE, status: 'ready', selectedCollectionId: 'c1',
        selectedPreset: 'L2', documentsLoaded: true, documents: [{ id: 'd' }], capabilities: { presets } });
      return { store, actions: createAskActions({ api, store }) };
    };
"""


def test_ask_stores_an_answer_a_not_found_and_an_error(page, base_url):
    result = run_js(
        page,
        base_url,
        ASK_SETUP
        + """
        const replies = [
          () => ({ answer: 'Cevap [1]', citations: [{ number: 1 }], trace: [], preset: 'L4+llm', latency_ms: 420 }),
          () => ({ answer: null, citations: [], trace: [{ rank: 1 }], preset: 'L2', latency_ms: 10 }),
          () => { throw new ApiError('llm_unavailable', 503, { detail: 'llm_unavailable', trace: [{ rank: 1 }] }); },
          () => { throw new ApiError('busy', 429, { detail: 'busy' }); },
        ];
        const calls = [];
        const api = { ask: async (cid, question, preset) => { calls.push([cid, question, preset]); return replies.shift()(); } };
        const { store, actions } = make(api);
        const out = [];
        actions.selectPreset('L4+llm');
        await actions.askQuestion('  Soru bir?  ');
        out.push(store.get().result.kind, store.get().result.usesLlm, store.get().result.latencyMs);
        actions.selectPreset('L2');
        await actions.askQuestion('Soru iki?');
        out.push(store.get().result.kind);
        await actions.askQuestion('Soru üç?');
        out.push(store.get().result.kind, store.get().result.code, store.get().result.trace.length);
        await actions.askQuestion('Soru dört?');
        out.push(store.get().result.code, store.get().result.trace.length, store.get().asking);
        return [out, calls[0]];
    """,
    )
    assert result == [
        ["answer", True, 420, "notFound", "error", "llm_unavailable", 1, "busy", 0, False],
        ["c1", "Soru bir?", "L4+llm"],
    ]


def test_ask_ignores_a_blank_question_and_a_second_call_while_asking(page, base_url):
    result = run_js(
        page,
        base_url,
        ASK_SETUP
        + """
        let calls = 0;
        let release;
        const gate = new Promise((resolve) => { release = resolve; });
        const api = { ask: async () => { calls += 1; await gate; return { answer: null, citations: [], trace: [], preset: 'L2', latency_ms: 1 }; } };
        const { store, actions } = make(api);
        await actions.askQuestion('   ');
        const message = store.get().askMessage;
        const first = actions.askQuestion('Soru?');
        await actions.askQuestion('Soru?');
        release();
        await first;
        return [message, calls];
    """,
    )
    assert result == ["Lütfen bir soru yazın.", 1]
