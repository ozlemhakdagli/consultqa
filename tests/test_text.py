# tests/test_text.py
import pytest

from docrag.text import casefold_tr, normalize_answer, tokenize_tr


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("İSTANBUL", "istanbul"),
        ("ISPARTA", "ısparta"),
        ("Irmak", "ırmak"),
        ("ırmak", "ırmak"),
        ("ıI", "ıı"),
    ],
)
def test_casefold_tr(text, expected):
    assert casefold_tr(text) == expected


def test_inflections_share_a_prefix():
    assert tokenize_tr("Siparişler", prefix=5) == ["sipar"]


# [R1] Dotted and dotless I in documents and questions match.
def test_turkish_queries_match_documents_regardless_of_dotted_i():
    assert tokenize_tr("İSTANBUL", prefix=5) == tokenize_tr("istanbul", prefix=5)
    assert tokenize_tr("ISPARTA", prefix=5) == tokenize_tr("Isparta", prefix=5)


def test_normalize_answer_ignores_trailing_punctuation():
    assert normalize_answer("V4.24.06.26)") == normalize_answer("V4.24.06.26") == "v4.24.06.26"


def test_normalize_answer_handles_none():
    assert normalize_answer(None) == ""
