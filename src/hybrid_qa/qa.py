"""Extractive question answering over a retrieved context."""

from collections.abc import Callable
from typing import Any

from hybrid_qa.config import QA_MODEL, QA_MODEL_REVISION


class AnswerExtractor:
    """Wraps a question-answering pipeline and returns the extracted answer span."""

    def __init__(
        self,
        model_name: str = QA_MODEL,
        pipeline_fn: Callable[..., Callable[..., Any]] | None = None,
        revision: str = QA_MODEL_REVISION,
    ) -> None:
        """Build the underlying pipeline.

        Args:
            model_name: Hugging Face model id used for both model and tokenizer.
            revision: Pinned Hugging Face commit used for both model and tokenizer.
            pipeline_fn: Factory called as ``pipeline_fn(task, model=..., tokenizer=...,
                revision=...)``. Defaults to ``transformers.pipeline``, imported lazily so that
                importing this module does not require the model stack.
        """
        if pipeline_fn is None:
            from transformers import pipeline as hf_pipeline

            pipeline_fn = hf_pipeline

        self._pipeline = pipeline_fn(
            "question-answering",
            model=model_name,
            tokenizer=model_name,
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
