# tests/test_metrics.py
import pytest

from consultqa.eval.metrics import (
    exact_match,
    lenient_match,
    recall_at_k,
    reciprocal_rank_at_k,
    set_f1,
    token_f1,
)


def test_token_f1_is_multiset():
    # prediction tokens [a, a, b] against gold [a, b]: overlap 2, precision 2/3, recall 1
    assert token_f1("a a b", ["a b"]) == pytest.approx(0.8)


def test_token_f1_takes_the_best_accepted_answer_and_handles_none():
    assert token_f1("Istanbul", ["Ankara", "Istanbul"]) == 1.0
    assert token_f1(None, ["Ankara"]) == 0.0


def test_token_f1_rejects_an_empty_accepted_list():
    with pytest.raises(ValueError):
        token_f1("a", [])


def test_reciprocal_rank_counts_the_first_gold_only():
    assert reciprocal_rank_at_k(["x", "g", "y"], {"g"}, k=10) == pytest.approx(0.5)
    assert reciprocal_rank_at_k(["x", "y"], {"g"}, k=10) == 0.0


def test_reciprocal_rank_ignores_ranks_beyond_k():
    assert reciprocal_rank_at_k(["x", "g"], {"g"}, k=1) == 0.0


def test_recall_at_k_checks_only_the_top_k():
    assert recall_at_k(["x", "g"], {"g"}, k=2) == 1.0
    assert recall_at_k(["x", "g"], {"g"}, k=1) == 0.0


def test_exact_match_uses_turkish_casefold_and_edge_punctuation():
    assert exact_match("ISPARTA.", ["Isparta"]) == 1.0
    assert exact_match("Ankara extra", ["Ankara"]) == 0.0
    assert exact_match(None, ["Ankara"]) == 0.0
    assert exact_match("", [""]) == 0.0


def test_lenient_match_accepts_a_turkish_suffix_on_the_gold_token():
    # "İstanbul'da" tokenises to ["istanbul", "da"], which contains the gold token.
    assert lenient_match("İstanbul'da.", ["İstanbul"]) == 1.0


def test_lenient_match_rejects_long_answers_that_only_mention_the_gold():
    assert lenient_match("Cevap bu metin olarak istanbul.", ["istanbul"]) == 0.0


def test_lenient_match_rejects_absent_gold_and_none():
    assert lenient_match("ankara", ["istanbul"]) == 0.0
    assert lenient_match(None, ["istanbul"]) == 0.0


def test_set_f1():
    assert set_f1({"a", "b"}, {"b", "c"}) == pytest.approx(0.5)
    assert set_f1(set(), set()) == 1.0
    assert set_f1(set(), {"a"}) == 0.0
