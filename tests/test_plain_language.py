"""Static plain-language checks: no technical word in what the page shows."""

import re
from pathlib import Path

from frontend_strings import EN_JS, TR_JS, keys, values
from plain_words import find_forbidden, find_forbidden_en

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _values() -> dict[str, str]:
    return values(TR_JS)


def test_the_word_scanner_catches_the_forbidden_words_and_spares_plain_ones():
    for bad in (
        "Koleksiyon seçin",
        "belge parçaları",
        "L4+llm",
        "Dil modeli",
        "PageRank",
        "grafik",
    ):
        assert find_forbidden(bad), bad
    for good in (
        "paragraf",
        "fotoğraf",
        "Hızlı ve doğru",
        "Yapay zekâ ile yazılmış cevap",
        "Belgelerim",
    ):
        assert find_forbidden(good) == [], good


def test_every_line_of_strings_js_is_read_by_the_scanner():
    for path in (TR_JS, EN_JS):
        assert keys(path) == set(values(path)), path.name


def test_no_visible_string_contains_a_technical_word():
    found = {key: find_forbidden(value) for key, value in _values().items()}
    assert {key: words for key, words in found.items() if words} == {}


def test_the_html_shell_contains_no_technical_word():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    text = re.sub(r"<[^>]+>", " ", html)
    assert find_forbidden(text) == []
    assert find_forbidden_en(text) == []
