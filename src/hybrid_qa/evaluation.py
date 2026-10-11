"""Evaluation of answers with Exact Match and token-level F1."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from hybrid_qa.config import EVAL_SET_PATH


@dataclass(frozen=True)
class EvalExample:
    """A single gold question-answer pair."""

    question: str
    answer: str


@dataclass(frozen=True)
class EvalRow:
    """Per-question evaluation result."""

    question: str
    gold: str
    prediction: str
    exact_match: bool
    f1: float


def load_eval_set(path: Path = EVAL_SET_PATH) -> list[EvalExample]:
    """Load gold examples from a JSON list of ``{"question", "answer", "context"}``.

    The ``context`` field is ignored.
    """
    with path.open(encoding="utf-8") as f:
        items = json.load(f)
    return [EvalExample(question=item["question"], answer=item["answer"]) for item in items]


def exact_match(prediction: str, gold: str) -> bool:
    """Return True if the prediction equals the gold answer after strip and lowercase."""
    return prediction.strip().lower() == gold.strip().lower()


def token_f1(prediction: str, gold: str) -> float:
    """Return the F1 of the lowercase whitespace-token sets of prediction and gold."""
    pred_tokens = set(prediction.strip().lower().split())
    gold_tokens = set(gold.strip().lower().split())
    common = pred_tokens & gold_tokens
    precision = len(common) / len(pred_tokens) if pred_tokens else 0.0
    recall = len(common) / len(gold_tokens) if gold_tokens else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate(
    answer_fn: Callable[[str], str],
    examples: list[EvalExample],
) -> list[EvalRow]:
    """Run ``answer_fn`` on each question and score the predictions against gold answers."""
    rows: list[EvalRow] = []
    for example in examples:
        prediction = answer_fn(example.question)
        rows.append(
            EvalRow(
                question=example.question,
                gold=example.answer,
                prediction=prediction,
                exact_match=exact_match(prediction, example.answer),
                f1=token_f1(prediction, example.answer),
            )
        )
    return rows


def summarize(rows: list[EvalRow]) -> dict[str, float]:
    """Return mean Exact Match and mean F1 in the range 0..1 (zeros for no rows)."""
    if not rows:
        return {"exact_match": 0.0, "f1": 0.0}
    n = len(rows)
    return {
        "exact_match": sum(1 for r in rows if r.exact_match) / n,
        "f1": sum(r.f1 for r in rows) / n,
    }
