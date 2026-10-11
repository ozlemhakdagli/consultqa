# tests/test_extractive.py
from docrag.config import MODEL_PINS
from docrag.generate.extractive import ExtractiveReader


def test_span_and_score_are_returned():
    reader = ExtractiveReader(
        pipeline_fn=lambda task, **kw: lambda question, context: {"answer": " Stok ", "score": 0.9}
    )
    assert reader.answer_span("q", "c") == ("Stok", 0.9)


def test_non_dict_output_gives_empty_answer():
    reader = ExtractiveReader(pipeline_fn=lambda task, **kw: lambda question, context: None)
    assert reader.answer_span("q", "c") == ("", 0.0)


def test_pipeline_is_loaded_with_the_pinned_revision():
    seen = {}

    def factory(task, **kwargs):
        seen.update(kwargs)
        return lambda question, context: {"answer": "", "score": 0.0}

    ExtractiveReader(pipeline_fn=factory)
    assert seen["revision"] == MODEL_PINS["xlm-roberta-squad2"][1]
