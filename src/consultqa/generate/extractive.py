"""Extractive reader: a pinned question-answering model that returns a span of the context."""

from collections.abc import Callable
from typing import Any

from consultqa.config import MODEL_PINS


class ExtractiveReader:
    """Wraps a question-answering pipeline and returns the extracted answer span."""

    def __init__(
        self,
        model_key: str = "xlm-roberta-squad2",
        pipeline_fn: Callable[..., Callable[..., Any]] | None = None,
    ) -> None:
        """Build the underlying pipeline.

        Args:
            model_key: Key of the pinned model in ``MODEL_PINS``; its id and revision are
                used for both the model and the tokenizer.
            pipeline_fn: Factory called as ``pipeline_fn(task, model=..., tokenizer=...,
                revision=...)``. Defaults to ``transformers.pipeline``, imported lazily so that
                importing this module does not require the model stack.
        """
        model_id, revision = MODEL_PINS[model_key]
        if pipeline_fn is None:
            from transformers import pipeline as hf_pipeline

            pipeline_fn = hf_pipeline

        self._pipeline = pipeline_fn(
            "question-answering",
            model=model_id,
            tokenizer=model_id,
            revision=revision,
        )

    def answer(self, question: str, context: str) -> str:
        """Return the answer span for ``question`` within ``context``.

        Returns an empty string when the model produces no answer.
        """
        return self.answer_span(question, context)[0]

    def answer_span(self, question: str, context: str) -> tuple[str, float]:
        """Return ``(answer, score)`` for ``question`` within ``context``.

        The answer is stripped and is an empty string when the model produces none;
        the score is the pipeline's span score (0.0 when it reports none).
        """
        result = self._pipeline(question=question, context=context)
        if not isinstance(result, dict):
            return "", 0.0
        answer = (result.get("answer", "") or "").strip()
        return answer, float(result.get("score", 0.0) or 0.0)
