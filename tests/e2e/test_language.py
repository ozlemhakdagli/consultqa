"""Browser tests of the language switch: the page opens in the browser language, one switch
changes every visible text at once, and the choice is remembered."""

import pytest
from frontend_strings import EN_JS, TR_JS, placeholders, values
from playwright.sync_api import expect
from ui_helpers import (
    collection_with_document,
    mock_collections_unavailable,
    open_advanced,
    open_page,
)

pytestmark = pytest.mark.e2e

WORDS = """() => {
  const attributes = ['aria-label', 'placeholder', 'title', 'alt'];
  const own = [...document.querySelectorAll('*')]
    .flatMap((node) => attributes.map((name) => node.getAttribute(name)).filter(Boolean));
  return document.body.textContent + ' ' + own.join(' ');
}"""
# Values that are the same in both languages on purpose, or too short to mean anything.
EXEMPT = {"documents.listTitle", "documents.announce", "language.tr", "language.en"}
ASK = "Cevabı bul"


def _radio(page, name: str):
    return page.get_by_role("radio", name=name, exact=True)


def _leftovers(page, language: str) -> list[str]:
    """The strings of the other language's dictionary that still show on the page."""
    other = values(TR_JS if language == "en" else EN_JS)
    text = page.evaluate(WORDS)
    return sorted(
        value
        for key, value in other.items()
        if key not in EXEMPT and not placeholders(value) and len(value) >= 8 and value in text
    )


def _ask(page, question: str) -> None:
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


@pytest.mark.parametrize(
    ("locale", "language", "title", "chip"),
    [
        ("tr-TR", "tr", "Belge Soru-Cevap", "Sistem hazır"),
        ("tr", "tr", "Belge Soru-Cevap", "Sistem hazır"),
        ("en-US", "en", "Document Q&A", "System ready"),
        ("en-GB", "en", "Document Q&A", "System ready"),
        ("de-DE", "en", "Document Q&A", "System ready"),
        ("fr-FR", "en", "Document Q&A", "System ready"),
    ],
)
def test_the_page_opens_in_the_browser_language(make_page, base_url, locale, language, title, chip):
    page = make_page(locale=locale)
    open_page(page, base_url, library=False)
    assert page.evaluate("document.documentElement.lang") == language
    assert page.title() == title
    expect(page.locator("h1")).to_have_text(title)
    expect(page.locator("#system-chip")).to_have_text(chip)
    expect(page.locator(f"#language-switch input[value={language}]")).to_be_checked()


def test_the_switch_changes_every_visible_text_and_is_remembered(page, base_url):
    collection_with_document(page, base_url)
    _ask(page, "Stok modülü")
    expect(page.locator(".answer-card .note")).to_be_visible()
    open_advanced(page)
    _radio(page, "English").check()

    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(page).to_have_title("Document Q&A")
    expect(page.locator("h2")).to_have_text(
        ["1 Add your documents", "2 Type your question", "3 Answer"]
    )
    expect(page.locator("#system-chip")).to_have_text("System ready")
    expect(page.locator("#document-list li")).to_contain_text("Ready to use")
    expect(page.locator(".answer-card .note")).to_contain_text("This answer was taken from")
    # The answer and the document's own text stay in the language of the document.
    expect(page.locator("#result-title")).to_have_text(
        "Stok modülü performans iyileştirmesi yapıldı."
    )
    expect(page.locator("#cite-1")).to_contain_text("Document: ocak.md")
    expect(page.locator("#cite-1")).to_contain_text("Section: Stok")
    expect(page.locator("#cite-1")).to_contain_text("Text in the document")
    expect(page.get_by_role("radio", name="Fast and accurate", exact=True)).to_be_visible()
    expect(page.locator("#library-notice")).to_contain_text(
        "To return to the default folder, choose “My documents” under Advanced options."
    )
    expect(page.locator("#example-list button")).to_have_text(
        [
            "How long is the warranty period?",
            "Which documents are needed to apply?",
            "How long does delivery take?",
        ]
    )
    assert page.evaluate("localStorage.getItem('consultqa.language')") == "en"

    page.reload()
    open_page(page, base_url, library=False)
    expect(page).to_have_title("Document Q&A")
    _radio(page, "Türkçe").check()
    expect(page.locator("h1")).to_have_text("Belge Soru-Cevap")
    expect(page.locator("html")).to_have_attribute("lang", "tr")


def test_no_interface_text_of_the_other_language_is_left(page, base_url):
    collection_with_document(page, base_url)
    _ask(page, "Stok modülü")
    expect(page.locator(".answer-card .note")).to_be_visible()
    open_advanced(page)
    _radio(page, "English").check()
    assert _leftovers(page, "en") == []
    _radio(page, "Türkçe").check()
    assert _leftovers(page, "tr") == []


def test_a_saved_choice_beats_the_browser_language(make_page, base_url):
    page = make_page(locale="tr-TR")
    page.add_init_script("try { localStorage.setItem('consultqa.language', 'en'); } catch (e) {}")
    open_page(page, base_url, library=False)
    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(_radio(page, "English")).to_be_checked()


def test_the_switch_works_when_storage_is_blocked(make_page, base_url):
    page = make_page(locale="en-US")
    page.add_init_script(
        "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } });"
    )
    open_page(page, base_url, library=False)
    _radio(page, "Türkçe").check()
    expect(page.locator("h1")).to_have_text("Belge Soru-Cevap")
    expect(page.locator("html")).to_have_attribute("lang", "tr")


def test_switching_clears_notices_and_cancels_an_open_delete_confirmation(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_label("Sorunuz", exact=True).fill("   ")
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#ask-message")).to_have_text("Lütfen bir soru yazın.")
    page.get_by_role("button", name="ocak.md belgesini sil").click()
    expect(page.locator(".doc-confirm")).to_be_visible()

    open_advanced(page)
    _radio(page, "English").check()
    expect(page.locator("#ask-message")).to_be_hidden()
    expect(page.locator(".doc-confirm")).to_have_count(0)
    expect(page.locator("#document-list li").filter(has_text="ocak.md")).to_contain_text(
        "Ready to use"
    )


def test_a_library_error_is_shown_again_in_the_new_language(page, base_url):
    mock_collections_unavailable(page)
    open_page(page, base_url, library=False)
    expect(page.locator("#documents-message")).to_have_text(
        "Bir sorun oluştu. Lütfen tekrar deneyin."
    )
    _radio(page, "English").check()
    expect(page.locator("#documents-message")).to_be_visible()
    expect(page.locator("#documents-message")).to_have_text(
        "Something went wrong. Please try again."
    )


def test_the_switch_is_accessible(make_page, base_url):
    page = make_page(locale="en-US")
    open_page(page, base_url, library=False)
    expect(page.get_by_role("group", name="Language", exact=True)).to_be_visible()
    expect(page.locator("#language-switch input[type=radio]")).to_have_count(2)
    langs = page.evaluate(
        "Array.from(document.querySelectorAll('#language-switch span')).map((s) => s.lang)"
    )
    assert langs == ["tr", "en"]
    page.locator("#language-switch input[value=en]").focus()
    page.keyboard.press("ArrowLeft")
    expect(page.locator("html")).to_have_attribute("lang", "tr")


def test_the_example_questions_follow_the_language(make_page, base_url):
    page = make_page(locale="en-US")
    open_page(page, base_url, library=False)
    examples = page.locator("#example-list button")
    expect(examples).to_have_text(
        [
            "How long is the warranty period?",
            "Which documents are needed to apply?",
            "How long does delivery take?",
        ]
    )
    question = page.get_by_label("Your question", exact=True)
    examples.first.click()
    expect(question).to_have_value("How long is the warranty period?")
    expect(question).to_have_attribute(
        "placeholder",
        "Type your question here. For example: How long is the warranty period?",
    )
    _radio(page, "Türkçe").check()
    expect(examples).to_have_text(
        [
            "Garanti süresi kaç yıldır?",
            "Başvuru için hangi belgeler gerekir?",
            "Teslimat ne kadar sürer?",
        ]
    )
    expect(page.get_by_label("Sorunuz", exact=True)).to_have_attribute(
        "placeholder", "Sorunuzu buraya yazın. Örneğin: Garanti süresi kaç yıldır?"
    )
