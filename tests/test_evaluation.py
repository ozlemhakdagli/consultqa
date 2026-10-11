"""Tests for hybrid_qa.evaluation."""

import pytest

from hybrid_qa.config import EVAL_SET_PATH
from hybrid_qa.evaluation import (
    EvalExample,
    EvalRow,
    evaluate,
    exact_match,
    load_eval_set,
    summarize,
    token_f1,
)


def test_exact_match_ignores_case_and_surrounding_whitespace() -> None:
    assert exact_match("  alpha beta gamma ", "alpha beta gamma")


def test_exact_match_rejects_different_answers() -> None:
    assert not exact_match("SMS", "alpha beta gamma")


def test_token_f1_perfect_match() -> None:
    assert token_f1("Gamma Modülüne", "gamma modülüne") == pytest.approx(1.0)


def test_token_f1_partial_overlap() -> None:
    # prediction tokens {a, b, c}, gold tokens {a, b}: precision 2/3, recall 1
    expected = 2 * (2 / 3) * 1.0 / ((2 / 3) + 1.0)
    assert token_f1("a b c", "a b") == pytest.approx(expected)


def test_token_f1_no_overlap_is_zero() -> None:
    assert token_f1("foo", "bar") == 0.0


def test_token_f1_empty_prediction_is_zero() -> None:
    assert token_f1("", "bar") == 0.0


def test_token_f1_uses_token_sets() -> None:
    # Repeated tokens count once, as in the notebook.
    assert token_f1("a a a", "a") == pytest.approx(1.0)


def test_evaluate_scores_each_example_with_fake_answer_fn() -> None:
    answers = {"q1": "Gamma Modülüne", "q2": "wrong answer"}
    examples = [
        EvalExample(question="q1", answer="Gamma Modülüne"),
        EvalExample(question="q2", answer="V9.9.9"),
    ]

    rows = evaluate(lambda q: answers[q], examples)

    assert rows == [
        EvalRow(
            question="q1",
            gold="Gamma Modülüne",
            prediction="Gamma Modülüne",
            exact_match=True,
            f1=pytest.approx(1.0),
        ),
        EvalRow(
            question="q2",
            gold="V9.9.9",
            prediction="wrong answer",
            exact_match=False,
            f1=0.0,
        ),
    ]


def test_summarize_means_in_zero_to_one_range() -> None:
    rows = [
        EvalRow(question="q1", gold="a", prediction="a", exact_match=True, f1=1.0),
        EvalRow(question="q2", gold="b", prediction="c", exact_match=False, f1=0.5),
    ]

    result = summarize(rows)

    assert result["exact_match"] == pytest.approx(0.5)
    assert result["f1"] == pytest.approx(0.75)


def test_summarize_empty_returns_zeros() -> None:
    assert summarize([]) == {"exact_match": 0.0, "f1": 0.0}


@pytest.mark.skipif(not EVAL_SET_PATH.exists(), reason="private data not available")
def test_load_eval_set_reads_real_file() -> None:
    examples = load_eval_set(EVAL_SET_PATH)

    assert len(examples) == 20
    assert all(isinstance(e, EvalExample) for e in examples)
    assert all(e.answer and e.question for e in examples)


def test_load_eval_set_ignores_context_field(tmp_path) -> None:
    path = tmp_path / "set.json"
    path.write_text('[{"question": "q", "answer": "a", "context": "ignored"}]', encoding="utf-8")

    assert load_eval_set(path) == [EvalExample(question="q", answer="a")]
