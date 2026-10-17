"""The workspace vocabulary of the frontend: the state keys, the API client calls, the document
selector and the strings the document viewer and the thread need, in both languages."""

import pytest
from frontend_strings import EN_JS, TR_JS, placeholders, values
from ui_helpers import run_js

# The strings of the document workspace: key -> (Turkish, English), copied from the task brief.
WORKSPACE_STRINGS = {
    "panes.legend": ("Bölümler", "Sections"),
    "panes.documents": ("Belgeler", "Documents"),
    "panes.viewer": ("Belge", "Document"),
    "panes.chat": ("Sohbet", "Chat"),
    "viewer.empty": (
        "Kaynağı görmek için bir belge açın ya da bir cevaptaki sayfa düğmesine basın.",
        "Open a document, or press a page button in an answer, to see the source.",
    ),
    "viewer.pageLabel": ("Sayfa", "Page"),
    "viewer.pageOf": ("/ {count}", "/ {count}"),
    "viewer.zoomIn": ("Yakınlaştır", "Zoom in"),
    "viewer.zoomOut": ("Uzaklaştır", "Zoom out"),
    "viewer.fitWidth": ("Genişliğe sığdır", "Fit width"),
    "viewer.loading": ("Belge açılıyor…", "Opening the document…"),
    "viewer.cantShow": (
        "Bu dosya gösterilemiyor, yalnızca metni var.",
        "This file can't be shown, only its text.",
    ),
    "viewer.oldDocument": (
        "Bu belge görüntüleyiciden önce eklendi. Burada görmek için dosyayı yeniden ekleyin.",
        "This document was added before the viewer existed. Add the file again to see it here.",
    ),
    "viewer.pageDivider": ("Sayfa {page}", "Page {page}"),
    "viewer.noHighlight": (
        "Sayfa açıldı, ama cevap cümlesi sayfada işaretlenemedi.",
        "The page is open, but the answer sentence could not be marked on it.",
    ),
    "viewer.selectionAsk": ("Bu metni soru olarak yaz", "Use this text as a question"),
    "documents.open": ("{name} belgesini aç", "Open {name}"),
    "scope.legend": ("Soru nerede aransın?", "Where should the question look?"),
    "scope.document": ("Bu belgede", "In this document"),
    "scope.folder": ("Tüm klasörde", "In the whole folder"),
    "scope.noDocument": (
        "Açık belge yok, bu yüzden tüm klasörde aranır.",
        "No document is open, so the whole folder is searched.",
    ),
    "thread.independent": (
        "Her soru ayrı cevaplanır, önceki sorular hatırlanmaz.",
        "Each question is answered on its own. Earlier questions are not remembered.",
    ),
    "thread.scopeDocument": ("{document} içinde", "In {document}"),
    "thread.scopeFolder": ("Tüm klasörde", "In the whole folder"),
    "result.pageButton": ("Sayfa {page}", "Page {page}"),
    "result.pageButtonLabel": (
        "Sayfa {page}: {document} belgesinde göster",
        "Page {page}: show it in {document}",
    ),
    "result.relatedTitle": ("İlgili sayfalar", "Related pages"),
    "result.relatedLabel": ("Sayfa {page}: {document}", "Page {page}: {document}"),
    "result.sourcePage": ("Sayfa: {page}", "Page: {page}"),
    "error.file_not_found": ("Bu dosya bulunamadı.", "This file could not be found."),
    "error.document_not_found": (
        "Bu belge artık yok. Liste yenilendi.",
        "This document no longer exists. The list has been refreshed.",
    ),
}


def test_every_workspace_string_exists_in_both_languages_with_the_same_placeholders():
    tr, en = values(TR_JS), values(EN_JS)
    for key, (turkish, english) in WORKSPACE_STRINGS.items():
        assert tr.get(key) == turkish, key
        assert en.get(key) == english, key
        assert placeholders(tr[key]) == placeholders(en[key]), key


@pytest.mark.e2e
def test_initial_state_has_the_workspace_keys_and_no_result(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { INITIAL_STATE } = await import('/js/state.js');
        return {
          openDocId: INITIAL_STATE.openDocId,
          openPage: INITIAL_STATE.openPage,
          highlight: INITIAL_STATE.highlight,
          viewerStatus: INITIAL_STATE.viewerStatus,
          scope: INITIAL_STATE.scope,
          thread: INITIAL_STATE.thread,
          draft: INITIAL_STATE.draft,
          activePane: INITIAL_STATE.activePane,
          hasResult: Object.hasOwn(INITIAL_STATE, 'result'),
        };
        """,
    )
    assert result == {
        "openDocId": "",
        "openPage": 1,
        "highlight": None,
        "viewerStatus": "idle",
        "scope": "document",
        "thread": [],
        "draft": None,
        "activePane": "documents",
        "hasResult": False,
    }


@pytest.mark.e2e
def test_ask_sends_doc_id_only_when_given(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createApi } = await import('/js/api.js');
        const sent = [];
        const fetchImpl = async (path, init) => {
          sent.push({ path, body: JSON.parse(init.body) });
          return new Response(JSON.stringify({ ok: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          });
        };
        const api = createApi({ fetchImpl });
        await api.ask('c1', 'Soru?', 'fast');
        await api.ask('c1', 'Soru?', 'fast', 'd1');
        return sent;
        """,
    )
    assert result == [
        {"path": "/api/collections/c1/ask", "body": {"question": "Soru?", "preset": "fast"}},
        {
            "path": "/api/collections/c1/ask",
            "body": {"question": "Soru?", "preset": "fast", "doc_id": "d1"},
        },
    ]


@pytest.mark.e2e
def test_document_file_url_encodes_both_ids(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createApi } = await import('/js/api.js');
        const api = createApi({ fetchImpl: async () => new Response('{}') });
        return api.documentFileUrl('a b', 'd1');
        """,
    )
    assert result == "/api/collections/a%20b/documents/d1/file"


@pytest.mark.e2e
def test_document_text_returns_the_body_and_rejects_with_the_code(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createApi } = await import('/js/api.js');
        const ok = createApi({ fetchImpl: async () => new Response('Merhaba metin') });
        const text = await ok.documentText('c1', 'd1');
        const missing = createApi({
          fetchImpl: async () =>
            new Response(JSON.stringify({ detail: 'file_not_found' }), {
              status: 404,
              headers: { 'Content-Type': 'application/json' },
            }),
        });
        let code = '';
        let status = 0;
        try {
          await missing.documentText('c1', 'd1');
        } catch (error) {
          code = error.code;
          status = error.status;
        }
        return [text, code, status];
        """,
    )
    assert result == ["Merhaba metin", "file_not_found", 404]


@pytest.mark.e2e
def test_document_passages_return_the_pages_and_reject_with_the_code(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createApi } = await import('/js/api.js');
        const body = { pages: [{ page: 2, text: 'Metin' }] };
        const ok = createApi({
          fetchImpl: async () =>
            new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } }),
        });
        const got = await ok.documentPassages('c1', 'd1');
        const missing = createApi({
          fetchImpl: async () =>
            new Response(JSON.stringify({ detail: 'document_not_found' }), {
              status: 404,
              headers: { 'Content-Type': 'application/json' },
            }),
        });
        let code = '';
        let status = 0;
        try {
          await missing.documentPassages('c1', 'd1');
        } catch (error) {
          code = error.code;
          status = error.status;
        }
        const broken = createApi({
          fetchImpl: async () => {
            throw new TypeError('offline');
          },
        });
        let networkCode = '';
        try {
          await broken.documentPassages('c1', 'd1');
        } catch (error) {
          networkCode = error.code;
        }
        return [got, code, status, networkCode];
        """,
    )
    assert result == [
        {"pages": [{"page": 2, "text": "Metin"}]},
        "document_not_found",
        404,
        "network_error",
    ]


@pytest.mark.e2e
def test_document_info_reads_kind_pages_and_original_from_the_documents(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { documentInfo } = await import('/js/selectors.js');
        const state = {
          documents: [
            { id: 'd1', filename: 'a.pdf', kind: 'pdf', page_count: 3, has_original: true },
            { id: 'd2', filename: 'b.txt', kind: 'text', page_count: null },
          ],
        };
        const info = documentInfo(state);
        return [info instanceof Map, [...info.keys()], info.get('d1'), info.get('d2')];
        """,
    )
    assert result == [
        True,
        ["d1", "d2"],
        {"filename": "a.pdf", "kind": "pdf", "pageCount": 3, "hasOriginal": True},
        {"filename": "b.txt", "kind": "text", "pageCount": None, "hasOriginal": False},
    ]
