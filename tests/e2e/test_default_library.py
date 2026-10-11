"""The default library: one stored name in every language, a localized label, reserved names."""

import pytest
from playwright.sync_api import expect
from ui_helpers import open_advanced, open_page, run_js

pytestmark = pytest.mark.e2e


def test_library_helpers(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        const libs = await import('/js/libraries.js');
        const def = { id: 'a', name: 'Belgelerim' };
        const other = { id: 'b', name: 'Reports' };
        const tr = [libs.isDefaultLibrary(def), libs.isDefaultLibrary(other),
                    libs.isDefaultLibrary(null), libs.libraryLabel(def),
                    libs.libraryLabel(other), libs.libraryLabel(null)];
        i18n.setLanguage('en');
        const en = [libs.libraryLabel(def), libs.libraryLabel(other)];
        const reserved = ['belgelerim', 'BELGELERIM', 'BELGELERİM', 'My documents',
                          '  my DOCUMENTS ', 'Belgelerim 2', '', 'Reports']
                          .map(libs.isReservedLibraryName);
        return [tr, en, reserved];
        """,
    )
    assert result == [
        [True, False, False, "Belgelerim", "Reports", ""],
        ["My documents", "Reports"],
        [True, True, True, True, True, False, False, False],
    ]


def test_the_default_library_keeps_its_stored_name_in_english_and_is_never_created_twice(
    page, base_url
):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createCollectionActions } = await import('/js/actions/collections.js');
        i18n.setLanguage('en');
        function make(list) {
          const created = [];
          const api = {
            listCollections: async () => list.map((c) => ({ ...c })),
            createCollection: async (name) => {
              created.push(name);
              const row = { id: 'n1', name };
              list.push(row);
              return row;
            },
          };
          const store = createStore({ ...INITIAL_STATE, lang: 'en' });
          const actions = createCollectionActions(
            { api, store, documents: { loadDocuments: async () => {} } });
          return { created, store, actions };
        }
        const empty = make([]);
        await empty.actions.loadCollections();
        const existing = make([{ id: 'x', name: 'Belgelerim' }, { id: 'y', name: 'Reports' }]);
        await existing.actions.loadCollections();
        return [empty.created, empty.store.get().selectedCollectionId,
                existing.created, existing.store.get().selectedCollectionId];
        """,
    )
    assert result == [["Belgelerim"], "n1", [], "x"]


def test_creating_a_reserved_name_is_refused_before_any_request(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const { createCollectionActions } = await import('/js/actions/collections.js');
        const out = [];
        for (const [language, name] of [['tr', 'BELGELERIM'], ['en', 'my documents']]) {
          i18n.setLanguage(language);
          let requests = 0;
          const api = {
            listCollections: async () => { requests += 1; return []; },
            createCollection: async () => { requests += 1; return { id: 'z' }; },
          };
          const store = createStore({ ...INITIAL_STATE, lang: language });
          const actions = createCollectionActions(
            { api, store, documents: { loadDocuments: async () => {} } });
          const outcome = await actions.createCollection(name);
          out.push([outcome, requests, store.get().collectionMessage]);
        }
        return out;
        """,
    )
    assert result == [
        [
            False,
            0,
            {
                "kind": "error",
                "text": "Bu ad varsayılan klasör için ayrılmıştır. Lütfen başka bir ad yazın.",
            },
        ],
        [
            False,
            0,
            {
                "kind": "error",
                "text": "This name is kept for the default folder. Please choose another name.",
            },
        ],
    ]


def test_an_english_first_visit_creates_belgelerim_and_shows_my_documents(make_page, fresh_server):
    page = make_page(locale="en-US")
    open_page(page, fresh_server)

    def names() -> list[str]:
        return [c["name"] for c in page.request.get(fresh_server + "/api/collections").json()]

    assert names() == ["Belgelerim"]
    expect(page.locator("#collection-select option:checked")).to_have_text("My documents")
    page.reload()
    open_page(page, fresh_server)
    assert names() == ["Belgelerim"]


def test_an_existing_install_with_belgelerim_is_recognised_in_english(make_page, fresh_server):
    turkish = make_page()  # the owner's install was first used by a Turkish browser
    cid = turkish.request.post(
        fresh_server + "/api/collections", data={"name": "Belgelerim"}
    ).json()["id"]
    upload = turkish.request.post(
        f"{fresh_server}/api/collections/{cid}/documents",
        multipart={
            "file": {
                "name": "eski.md",
                "mimeType": "text/markdown",
                "buffer": b"# Eski\n\nEski belge metni.\n",
            }
        },
    )
    assert upload.status == 202

    english = make_page(locale="en-US")
    open_page(english, fresh_server)
    row = english.locator("#document-list li").filter(has_text="eski.md")
    expect(row).to_contain_text("Ready to use")
    expect(english.locator("#collection-select option:checked")).to_have_text("My documents")
    names = [c["name"] for c in english.request.get(fresh_server + "/api/collections").json()]
    assert names == ["Belgelerim"]


@pytest.mark.parametrize(
    ("locale", "name", "message"),
    [
        (
            "tr-TR",
            "belgelerim",
            "Bu ad varsayılan klasör için ayrılmıştır. Lütfen başka bir ad yazın.",
        ),
        (
            "en-US",
            "my documents",
            "This name is kept for the default folder. Please choose another name.",
        ),
    ],
)
def test_a_reserved_name_is_refused_in_the_page_in_both_languages(
    make_page, base_url, locale, name, message
):
    page = make_page(locale=locale)
    open_page(page, base_url)
    open_advanced(page)
    page.locator("#collection-name").fill(name)
    page.locator("#collection-create").click()
    expect(page.locator("#collection-message")).to_have_text(message)
