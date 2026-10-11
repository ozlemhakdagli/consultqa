"""Browser tests of the language module: detection, the saved choice and the current language."""

import pytest
from ui_helpers import run_js

pytestmark = pytest.mark.e2e


def test_detect_language_from_the_browser_and_the_saved_choice(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { detectLanguage } = await import('/js/i18n.js');
        return [detectLanguage('tr-TR', ''), detectLanguage('tr', ''), detectLanguage('TR', ''),
                detectLanguage('tr_TR', ''), detectLanguage('en-US', ''), detectLanguage('de-DE', ''),
                detectLanguage('', ''), detectLanguage(null, ''), detectLanguage('tr-TR', 'en'),
                detectLanguage('en-US', 'tr'), detectLanguage('en-US', 'fr')];
        """,
    )
    assert result == ["tr", "tr", "tr", "tr", "en", "en", "en", "en", "en", "tr", "en"]


def test_set_language_updates_html_lang_title_and_static_text(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        const out = [i18n.currentLanguage()];
        i18n.setLanguage('en');
        out.push(i18n.currentLanguage(), document.documentElement.lang, document.title,
                 i18n.t('app.title'), i18n.has('app.title'));
        const root = document.createElement('div');
        const heading = document.createElement('h1');
        heading.setAttribute('data-text', 'ask.submit');
        root.append(heading);
        i18n.applyStaticText(root);
        out.push(heading.textContent);
        i18n.setLanguage('xx');
        out.push(i18n.currentLanguage());
        i18n.setLanguage('tr');
        out.push(document.documentElement.lang, document.title,
                 i18n.t('collection.created', { name: 'A' }));
        return out;
        """,
    )
    assert result == [
        "tr",
        "en",
        "en",
        "Document Q&A",
        "Document Q&A",
        True,
        "Find the answer",
        "en",
        "tr",
        "Belge Soru-Cevap",
        "“A” klasörü oluşturuldu ve seçildi.",
    ]


def test_a_chosen_language_is_saved_and_beats_the_browser_language(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        localStorage.clear();
        const first = await import('/js/i18n.js?first');
        first.chooseLanguage('en');
        const saved = localStorage.getItem('consultqa.language');
        const second = await import('/js/i18n.js?second');
        return [saved, second.currentLanguage(), second.detectLanguage('tr-TR')];
        """,
    )
    assert result == ["en", "en", "en"]


def test_t_follows_the_current_language_and_unknown_keys_stay_keys(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        i18n.setLanguage('en');
        return [
            i18n.t('collection.created', { name: 'Reports' }),
            i18n.t('no.such.key'),
            i18n.t('documents.hint', { types: 'MD, PDF', mb: '0.5' }),
        ];
        """,
    )
    assert result == [
        "The folder “Reports” was created and selected.",
        "no.such.key",
        "Supported files: MD, PDF. Largest file size: 0.5 MB.",
    ]


def test_blocked_storage_does_not_break_the_language(make_page, base_url):
    page = make_page(locale="en-US")
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });"
    )
    result = run_js(
        page,
        base_url,
        """
        const { chooseLanguage, currentLanguage, detectLanguage } = await import('/js/i18n.js');
        chooseLanguage('tr');
        return [currentLanguage(), detectLanguage('en-US')];
        """,
    )
    assert result == ["tr", "en"]


def test_an_english_browser_gets_english_text_from_the_start(make_page, base_url):
    page = make_page(locale="en-US")
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        return [i18n.currentLanguage(), i18n.t('app.title')];
        """,
    )
    assert result == ["en", "Document Q&A"]


def test_a_language_change_notifies_every_watcher(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const { createStore, INITIAL_STATE } = await import('/js/state.js');
        const store = createStore({ ...INITIAL_STATE, lang: 'tr' });
        const calls = [];
        store.subscribe(() => calls.push('a'), ['asking']);
        store.subscribe(() => calls.push('b'), ['result']);
        calls.length = 0;
        store.set({ asking: false });
        store.set({ lang: 'tr' });
        store.set({ lang: 'en' });
        store.set({ asking: true });
        return [calls, INITIAL_STATE.lang];
        """,
    )
    assert result == [["a", "b", "a"], ""]


def test_formatters_follow_the_language(page, base_url):
    result = run_js(
        page,
        base_url,
        """
        const i18n = await import('/js/i18n.js');
        const f = await import('/js/format.js');
        const tr = [f.formatSeconds(420), f.formatMegabytes(0.5)];
        i18n.setLanguage('en');
        const en = [f.formatSeconds(420), f.formatSeconds(1234), f.formatMegabytes(0.5),
                    f.formatDateTime('2026-10-11T10:30:00+00:00').includes('2026')];
        return [tr, en];
        """,
    )
    assert result == [["0,42", "0,5"], ["0.42", "1.23", "0.5", True]]
