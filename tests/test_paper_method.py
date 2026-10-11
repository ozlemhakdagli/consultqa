"""Tests for the pure functions of the paper-method reproduction (synthetic inputs only)."""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "reference" / "paper_method" / "pipeline.py"
_SPEC = importlib.util.spec_from_file_location("paper_method_pipeline", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
pipeline = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pipeline)


def test_merge_unique_keeps_dense_order_then_new_sparse_items():
    merged = pipeline.merge_unique(["alpha", "beta"], ["gamma", "beta", "delta"])
    assert merged == ["alpha", "beta", "gamma", "delta"]


def test_merge_unique_keeps_first_occurrence_within_one_list():
    assert pipeline.merge_unique(["a", "b", "a"], []) == ["a", "b"]


def test_merge_unique_of_empty_inputs_is_empty():
    assert pipeline.merge_unique([], []) == []


def test_merge_unique_first_element_is_the_first_dense_item_when_dense_is_present():
    assert pipeline.merge_unique(["first"], ["second"])[0] == "first"


def test_exact_match_ignores_outer_whitespace_and_case():
    assert pipeline.exact_match("  Gamma Modülüne ", "gamma modülüne") is True


def test_exact_match_rejects_different_text():
    assert pipeline.exact_match("alpha beta", "alpha") is False


def test_exact_match_does_not_ignore_inner_whitespace_or_punctuation():
    assert pipeline.exact_match("alpha  beta", "alpha beta") is False
    assert pipeline.exact_match("alpha beta.", "alpha beta") is False


def test_f1_identical_strings_score_one():
    assert pipeline.f1_score("alpha beta", "Alpha Beta") == pytest.approx(1.0)


def test_f1_disjoint_strings_score_zero():
    assert pipeline.f1_score("alpha", "beta") == pytest.approx(0.0)


def test_f1_uses_set_precision_and_recall():
    # prediction tokens {alpha, beta, gamma}, gold tokens {alpha, beta}
    # precision 2/3, recall 1, F1 = 2 * (2/3) * 1 / (2/3 + 1) = 0.8
    assert pipeline.f1_score("alpha beta gamma", "alpha beta") == pytest.approx(0.8)


def test_f1_counts_repeated_tokens_once():
    assert pipeline.f1_score("alpha alpha beta", "alpha beta") == pytest.approx(1.0)


def test_f1_empty_prediction_scores_zero():
    assert pipeline.f1_score("", "alpha") == pytest.approx(0.0)


def test_top_k_indices_orders_by_descending_score():
    assert pipeline.top_k_indices([0.1, 0.9, 0.5, 0.7], 3) == [1, 3, 2]


def test_passage_text_joins_description_and_version():
    records = [
        {
            "version_info": {"version": "V1.0.0"},
            "updates": [{"id": "u1", "description": "alpha tool added"}],
        }
    ]
    assert pipeline.load_passages_from_records(records) == ["alpha tool added (Versiyon: V1.0.0)"]
