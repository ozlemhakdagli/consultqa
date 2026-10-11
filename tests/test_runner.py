from dataclasses import replace

import pytest

from consultqa.config import ABSTAIN_WORD, NO_CONTEXT_ANSWER, PRESETS
from consultqa.eval.records import EvalRecord
from consultqa.eval.runner import evaluate_paper, evaluate_preset, make_answer_fn
from consultqa.models import Chunk, Hit
from consultqa.retrieve.pipeline import RetrievalResult


class FakeRetriever:
    def __init__(self, ranking):
        self.ranking = ranking

    def retrieve(self, query):
        hits = [Hit(Chunk(cid, "d", 0, (), cid), 1.0, "rrf", "rrf") for cid in self.ranking[query]]
        return RetrievalResult(hits=hits, trace=[])


def _record(qid, gold, answer):
    return EvalRecord(qid, [answer], [gold], "span", "keyword", "f", "c", "dev", "generated", 0.0)


class FakeReader:
    def __init__(self, answer):
        self.answer_text = answer
        self.contexts = []

    def answer(self, question, context):
        self.contexts.append(context)
        return self.answer_text


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def chat(self, messages):
        self.calls.append(messages)
        return self.reply


class FakePaper:
    def __init__(self, ranking, answers, ids_by_text):
        self.ranking = ranking
        self.answers = answers
        self.ids_by_text = ids_by_text

    def ranked_chunk_ids(self, query):
        return self.ranking[query]

    def ids_for_text(self, text):
        return list(self.ids_by_text.get(text, []))

    def answer(self, query):
        return self.answers[query]


class FakeReference:
    """Stands in for the reference module: exact match on the raw strings, no normalisation."""

    @staticmethod
    def exact_match(prediction, gold):
        return prediction.strip().lower() == gold.strip().lower()

    @staticmethod
    def f1_score(prediction, gold):
        return 1.0 if prediction.strip().lower() == gold.strip().lower() else 0.0


def _hit(chunk_id, text, position=0, heading=()):
    return Hit(Chunk(chunk_id, "d", position, heading, text), 1.0, "rrf", "rrf")


def test_mrr_and_recall_on_two_questions():
    records = [_record("q1", "g1", "x"), _record("q2", "g2", "x")]
    retriever = FakeRetriever({"q1": ["g1", "z"], "q2": ["z", "y", "g2"]})
    rows = evaluate_preset(PRESETS["L2"], retriever, records, answer_fn=lambda q, r: "x")
    assert rows[0]["mrr10"] == 1.0
    assert rows[1]["mrr10"] == 1 / 3
    assert rows[0]["em"] == 1.0


def test_gold_passages_with_the_same_text_all_count():
    chunks = [Chunk("d#1", "d", 0, (), "B"), Chunk("d#2", "d", 1, (), "B")]
    records = [_record("q", "d#1", "x")]
    retriever = FakeRetriever({"q": ["z", "d#2"]})
    rows = evaluate_preset(
        PRESETS["L2"], retriever, records, answer_fn=lambda q, r: "x", chunks=chunks
    )
    assert rows[0]["rank_gold"] == 2
    assert rows[0]["mrr10"] == 0.5


def test_extractive_reader_gets_the_first_passage_with_its_heading():
    reader = FakeReader("Stok")
    cfg = replace(PRESETS["L2"], use_context=True)
    answer_fn = make_answer_fn(cfg, reader=reader, llm=None, chunks_by_doc={})
    result = RetrievalResult(
        hits=[_hit("d#0", "Stok modülü", heading=("Bölüm 1",)), _hit("d#1", "Rapor")],
        trace=[],
    )
    assert answer_fn("soru", result) == "Stok"
    assert reader.contexts == ["Bölüm 1: Stok modülü"]


def test_extractive_without_hits_gives_no_context_answer_and_no_reader_call():
    reader = FakeReader("unused")
    answer_fn = make_answer_fn(PRESETS["L2"], reader=reader, llm=None, chunks_by_doc={})
    assert answer_fn("soru", RetrievalResult(hits=[], trace=[])) == NO_CONTEXT_ANSWER
    assert reader.contexts == []


def test_llm_answer_keeps_in_range_citations_and_drops_the_rest():
    llm = FakeLLM("Stok modülü [1] [7].")
    answer_fn = make_answer_fn(PRESETS["L4+llm"], reader=None, llm=llm, chunks_by_doc={})
    result = RetrievalResult(hits=[_hit("d#0", "Stok modülü")], trace=[])
    assert answer_fn("soru", result) == "Stok modülü [1]."
    user_message = llm.calls[0][1]["content"]
    assert '<passage n="1">' in user_message


def test_llm_abstention_becomes_no_context_answer():
    llm = FakeLLM(ABSTAIN_WORD)
    answer_fn = make_answer_fn(PRESETS["L4+llm"], reader=None, llm=llm, chunks_by_doc={})
    result = RetrievalResult(hits=[_hit("d#0", "Rapor")], trace=[])
    assert answer_fn("soru", result) == NO_CONTEXT_ANSWER


def test_llm_preset_without_a_client_is_rejected():
    with pytest.raises(ValueError, match="LLM"):
        make_answer_fn(PRESETS["L4+llm"], reader=None, llm=None, chunks_by_doc={})


def test_paper_rows_carry_legacy_and_corrected_answer_metrics():
    record = _record("q", "d#0", "stok")
    chunks = [Chunk("d#0", "d", 0, (), "Stok modülü")]
    paper = FakePaper(
        ranking={"q": ["d#0"]},
        answers={"q": "Stok."},
        ids_by_text={"Stok modülü": ["d#0"]},
    )
    rows = evaluate_paper([record], paper, reference=FakeReference(), chunks=chunks)
    assert rows[0]["em_legacy"] == 0.0
    assert rows[0]["em"] == 1.0
    assert rows[0]["mrr10"] == 1.0
