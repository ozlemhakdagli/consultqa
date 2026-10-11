"""LLM judge for answer correctness: one yes-or-no call with a fixed Turkish prompt.

The prompt is read from ``judge_prompt.txt``. Its SHA-256 is pinned in ``JUDGE_PROMPT_SHA256``;
a test fails when the file changes without the constant being updated.
"""

from collections.abc import Sequence
from pathlib import Path

from consultqa.generate.llm_client import LLMClient

JUDGE_PROMPT = Path(__file__).with_name("judge_prompt.txt").read_text(encoding="utf-8").strip()
JUDGE_PROMPT_SHA256 = "58f00000fcf8cfba550afcfa0f48aa79c2dcd7a96c99daf24e883af1b72f9d98"
_YES = "evet"


def _judge_input(question: str, prediction: str, accepted: Sequence[str]) -> str:
    """Return the user message: the question, the prediction and the accepted answers."""
    answers = "\n".join(f"- {answer}" for answer in accepted)
    return (
        f"Soru: {question}\n\nModel yanıtı: {prediction}\n\nKabul edilen doğru cevaplar:\n{answers}"
    )


def judge_correct(
    question: str,
    prediction: str,
    accepted: Sequence[str],
    *,
    judge: LLMClient,
) -> bool:
    """Return True only when the judge replies ``EVET`` (case and surrounding whitespace ignored).

    Any other reply counts as incorrect. Endpoint failures propagate as ``LLMUnavailable``.
    """
    messages = [
        {"role": "system", "content": JUDGE_PROMPT},
        {"role": "user", "content": _judge_input(question, prediction, accepted)},
    ]
    reply = judge.chat(messages)
    return reply.strip().casefold() == _YES
