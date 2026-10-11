# tests/test_text.py
import random
import re

import pytest

from consultqa.models import Chunk
from consultqa.text import (
    casefold_neutral,
    casefold_tr,
    document_folds,
    has_turkish_letters,
    normalize_answer,
    tokenize,
    tokenize_tr,
)


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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Invoice", "invoice"),
        ("INVOICE", "invoice"),
        ("İstanbul", "istanbul"),
        ("Isparta", "isparta"),
        ("ısı", "ısı"),
        ("İ", "i"),  # I plus a combining dot is one letter after NFC
    ],
)
def test_casefold_neutral(text, expected):
    assert casefold_neutral(text) == expected


def test_english_words_differ_under_the_turkish_fold_but_match_under_the_neutral_fold():
    # The measured finding that motivates the language-aware keyword channel (Design, section 2).
    assert casefold_tr("Invoice") == "ınvoice" != casefold_tr("invoice")
    assert casefold_neutral("Invoice") == casefold_neutral("invoice") == "invoice"
    assert tokenize_tr("Invoices are paid", 5) == ["ınvoi", "are", "paid"]
    assert tokenize("Invoices are paid", 5, fold=casefold_neutral) == ["invoi", "are", "paid"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Invoice", False),
        ("Stok modülü", True),
        ("ISPARTA", False),
        ("ışık", True),
        ("ç", True),  # c plus a combining cedilla is ç after NFC
        ("", False),
    ],
)
def test_has_turkish_letters(text, expected):
    assert has_turkish_letters(text) is expected


def _old_tokenize_tr(text, prefix=None):
    # The implementation before the language-aware change, copied verbatim.
    tokens = [token for token in re.split(r"[\W_]+", casefold_tr(text)) if token]
    if prefix is not None:
        tokens = [token[:prefix] for token in tokens]
    return tokens


def test_tokenize_with_the_turkish_fold_equals_the_old_tokenize_tr():
    samples = ["", "Sipariş modülü", "İSTANBUL'da ISPARTA", "Invoice IT API", "a_b-c.d",
               "é İ", "ışık 123 V4.24.06.26"]  # fmt: skip
    for text in samples:
        for prefix in (None, 3, 5):
            old = _old_tokenize_tr(text, prefix)
            assert tokenize_tr(text, prefix) == old
            assert tokenize(text, prefix, fold=casefold_tr) == old


def test_document_folds_choose_the_turkish_rule_per_document():
    chunks = [
        Chunk("t#0", "t", 0, (), "Merhaba"),
        Chunk("t#1", "t", 1, (), "Işık yandı"),
        Chunk("e#0", "e", 0, (), "Invoices are paid"),
        Chunk("e#1", "e", 1, (), "Within 30 days"),
    ]
    folds = document_folds(chunks)
    assert folds["t"] is casefold_tr and folds["e"] is casefold_neutral
    assert document_folds([]) == {}


def test_the_two_folds_give_equal_token_counts():
    rng = random.Random(0)  # noqa: S311 (a reproducible test input, not a secret)
    alphabet = "IıİiçÇğĞöÖşŞüÜ ABab.-_/̇"
    for _ in range(2000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
        turkish = tokenize(text, 5, fold=casefold_tr)
        neutral = tokenize(text, 5, fold=casefold_neutral)
        assert len(turkish) == len(neutral), text


# Canonically equivalent spellings casefold to the same text.
def test_casefold_normalises_to_nfc_first():
    assert casefold_tr("İ") == casefold_tr("İ") == "i"
    assert casefold_tr("é") == casefold_tr("é")
