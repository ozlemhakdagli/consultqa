"""Tests for hybrid_qa.qa using a fake pipeline (no model download)."""

from typing import Any

from hybrid_qa.config import QA_MODEL, QA_MODEL_REVISION
from hybrid_qa.qa import AnswerExtractor


class FakePipeline:
    """Records calls and returns a canned result."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.calls: list[dict[str, str]] = []

    def __call__(self, question: str, context: str) -> dict[str, Any]:
        self.calls.append({"question": question, "context": context})
        return self.result


def _factory(fake: FakePipeline):
    created: dict[str, Any] = {}

    def pipeline_fn(task: str, model: str, tokenizer: str, revision: str) -> FakePipeline:
        created.update(task=task, model=model, tokenizer=tokenizer, revision=revision)
        return fake

    pipeline_fn.created = created  # type: ignore[attr-defined]
    return pipeline_fn


def test_answer_returns_stripped_span() -> None:
    fake = FakePipeline({"answer": "  Gamma Modülüne \n", "score": 0.9})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    assert extractor.answer("hangi araca?", "Gamma Modülüne eklendi") == "Gamma Modülüne"


def test_answer_passes_question_and_context_to_pipeline() -> None:
    fake = FakePipeline({"answer": "x"})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    extractor.answer("soru?", "bağlam")

    assert fake.calls == [{"question": "soru?", "context": "bağlam"}]


def test_empty_answer_returns_empty_string() -> None:
    fake = FakePipeline({"answer": "   ", "score": 0.0})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    assert extractor.answer("soru?", "bağlam") == ""


def test_missing_answer_key_returns_empty_string() -> None:
    fake = FakePipeline({"score": 0.0})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    assert extractor.answer("soru?", "bağlam") == ""


def test_default_model_name_is_used_for_pipeline() -> None:
    fake = FakePipeline({"answer": "x"})
    factory = _factory(fake)

    AnswerExtractor(pipeline_fn=factory)

    assert factory.created == {
        "task": "question-answering",
        "model": QA_MODEL,
        "tokenizer": QA_MODEL,
        "revision": QA_MODEL_REVISION,
    }


def test_default_revision_is_pinned_and_passed_to_pipeline() -> None:
    from hybrid_qa.config import QA_MODEL_REVISION

    assert QA_MODEL_REVISION == "dafe59921a75cdffc06ed3ad6e45c581b22b85cc"
    fake = FakePipeline({"answer": "x"})
    factory = _factory(fake)

    AnswerExtractor(pipeline_fn=factory)

    assert factory.created["revision"] == QA_MODEL_REVISION


def test_explicit_revision_is_passed_to_pipeline() -> None:
    fake = FakePipeline({"answer": "x"})
    factory = _factory(fake)

    AnswerExtractor(pipeline_fn=factory, revision="abc123")

    assert factory.created["revision"] == "abc123"


def test_answer_span_returns_stripped_answer_and_score() -> None:
    fake = FakePipeline({"answer": "  Gamma Modülüne \n", "score": 0.75})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    assert extractor.answer_span("hangi araca?", "Gamma Modülüne eklendi") == (
        "Gamma Modülüne",
        0.75,
    )


def test_answer_span_keeps_empty_answer_with_its_score() -> None:
    fake = FakePipeline({"answer": "", "score": 0.4})
    extractor = AnswerExtractor(pipeline_fn=_factory(fake))

    assert extractor.answer_span("soru?", "bağlam") == ("", 0.4)
