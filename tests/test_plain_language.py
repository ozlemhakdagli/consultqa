"""Static plain-language checks: no technical word in what the page shows."""

import re
from pathlib import Path

from plain_words import find_forbidden

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
LINE = re.compile(r'^\s*"([^"]+)":\s*"(.*)",\s*$')


def _values() -> dict[str, str]:
    lines = (FRONTEND / "js" / "strings.js").read_text(encoding="utf-8").splitlines()
    return {m.group(1): m.group(2) for line in lines if (m := LINE.match(line))}


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
    text = (FRONTEND / "js" / "strings.js").read_text(encoding="utf-8")
    keys = set(re.findall(r'^\s*"([A-Za-z0-9_.+-]+)":', text, re.MULTILINE))
    assert keys == set(_values())


def test_no_visible_string_contains_a_technical_word():
    found = {key: find_forbidden(value) for key, value in _values().items()}
    assert {key: words for key, words in found.items() if words} == {}


def test_the_html_shell_contains_no_technical_word():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert find_forbidden(re.sub(r"<[^>]+>", " ", html)) == []
