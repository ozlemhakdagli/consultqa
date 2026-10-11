"""Tests for Turkish text utilities."""

from hybrid_qa.text import casefold_tr, reference_tokens, tokenize


def test_casefold_tr_maps_dotted_and_dotless_i():
    assert casefold_tr("İSTANBUL ISPARTA") == "istanbul ısparta"


def test_casefold_tr_keeps_turkish_lowercase():
    assert casefold_tr("şğüöç") == "şğüöç"


def test_tokenize_splits_punctuation_and_apostrophe():
    assert tokenize("Proje Aracı'nda, İşlem!") == ["proje", "aracı", "nda", "işlem"]


def test_tokenize_prefix_truncates_long_tokens():
    assert tokenize("Envanterlerinde işlem", prefix=5) == ["envan", "işlem"]


def test_tokenize_empty_and_punctuation_only():
    assert tokenize("") == [] and tokenize("?!.") == []


def test_reference_tokens_is_lower_split():
    assert reference_tokens("Foo BAR  baz") == ["foo", "bar", "baz"]
