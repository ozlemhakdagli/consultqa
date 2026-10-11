"""The two page dictionaries: same keys, no empty value, same placeholders, plain words."""

import re

from frontend_strings import EN_JS, FRONTEND, TR_JS, keys, placeholders, values
from plain_words import find_forbidden_en

ROOT = FRONTEND.parent
TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")
# Values that are the same in both languages on purpose: names and a pattern.
SAME_IN_BOTH = {"documents.listTitle", "documents.announce", "language.tr", "language.en"}


def test_both_dictionaries_have_the_same_keys():
    assert keys(TR_JS) == keys(EN_JS)
    assert len(keys(TR_JS)) >= 138


# The strings of the folder list and of its deletion, in both dictionaries.
FOLDER_DELETE_KEYS = {
    "collection.listTitle",
    "collection.documentCount",
    "collection.delete",
    "collection.deleteLabel",
    "collection.deleteConfirm",
    "collection.deleted",
    "error.collection_busy",
}


def test_the_folder_delete_strings_exist_in_both_dictionaries():
    for path in (TR_JS, EN_JS):
        assert FOLDER_DELETE_KEYS <= keys(path), (path.name, FOLDER_DELETE_KEYS - keys(path))


def test_no_value_is_empty():
    for path in (TR_JS, EN_JS):
        read = values(path)
        assert len(read) == len(keys(path)), path.name  # every key line is read
        assert all(value.strip() for value in read.values()), path.name


def test_placeholders_match_between_languages():
    tr, en = values(TR_JS), values(EN_JS)
    for key in tr:
        assert placeholders(tr[key]) == placeholders(en[key]), key


def test_english_has_no_turkish_letters_except_the_language_name():
    for key, value in values(EN_JS).items():
        if key != "language.tr":
            assert not TURKISH_LETTERS.search(value), key


def test_no_english_value_repeats_the_turkish_one_except_names_and_patterns():
    tr, en = values(TR_JS), values(EN_JS)
    same = sorted(key for key in tr if tr[key] == en[key])
    assert same == sorted(SAME_IN_BOTH)


def test_english_strings_contain_no_technical_word():
    found = {key: find_forbidden_en(value) for key, value in values(EN_JS).items()}
    assert {key: words for key, words in found.items() if words} == {}


def test_the_english_word_scanner_catches_the_forbidden_words_and_spares_plain_ones():
    for bad in (
        "Pick a collection",
        "text chunks",
        "L4+llm",
        "the language model",
        "PageRank",
        "knowledge graph",
        "the server is down",
        "the vector store",
        "rerank them",
    ):
        assert find_forbidden_en(bad), bad
    for good in (
        "paragraph",
        "photograph",
        "Fast and accurate",
        "Answer written by AI",
        "My documents",
        "Document Q&A",
    ):
        assert find_forbidden_en(good) == [], good


def test_every_reason_code_has_copy_in_both_languages():
    routes = (ROOT / "src" / "consultqa" / "api" / "routes.py").read_text(encoding="utf-8")
    code = re.search(r'LLM_NOT_CONFIGURED = "([^"]+)"', routes)
    assert code is not None
    for path in (TR_JS, EN_JS):
        assert {f"method.reason.{code.group(1)}", "method.reason.unknown"} <= keys(path), path.name


def test_method_notes_quote_the_recommended_label_in_each_language():
    for path in (TR_JS, EN_JS):
        read = values(path)
        label = read["method.fast.label"]
        for key in (
            "method.recheck.note",
            "method.headings.note",
            "method.related.note",
            "method.paper.note",
            "advanced.methodHelp",
        ):
            assert f"“{label}”" in read[key], (path.name, key)


def test_the_registry_lists_exactly_the_two_languages():
    text = (FRONTEND / "js" / "strings.js").read_text(encoding="utf-8")
    assert re.search(r"DICTIONARIES\s*=\s*Object\.freeze\(\{\s*tr:\s*TR,\s*en:\s*EN\s*\}\)", text)
