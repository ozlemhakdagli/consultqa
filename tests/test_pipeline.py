"""Tests for the end-to-end pipeline, using fake retrievers and extractors."""

from hybrid_qa.config import NO_CONTEXT_ANSWER
from hybrid_qa.data_loader import Passage
from hybrid_qa.pipeline import HybridQASystem, build_system


def _passage(update_id: str, text: str) -> Passage:
    return Passage(doc_id="doc", update_id=update_id, version="4.23", description=text)


class FakeRetriever:
    def __init__(self, passages):
        self.passages = passages
        self.queries = []

    def search(self, query):
        self.queries.append(query)
        return list(self.passages)


class FakeExtractor:
    def __init__(self, reply="cevap"):
        self.reply = reply
        self.calls = []

    def answer(self, question, context):
        self.calls.append((question, context))
        return self.reply


def test_no_passages_returns_no_context_answer():
    extractor = FakeExtractor()
    system = HybridQASystem(FakeRetriever([]), extractor)

    result = system.answer("soru")

    assert result.text == NO_CONTEXT_ANSWER
    assert result.source is None
    assert extractor.calls == []


def test_only_best_passage_is_used_as_context():
    best = _passage("1", "en iyi pasaj")
    other = _passage("2", "diğer pasaj")
    extractor = FakeExtractor(reply="42")
    system = HybridQASystem(FakeRetriever([best, other]), extractor)

    result = system.answer("soru")

    assert extractor.calls == [("soru", best.text)]
    assert "diğer pasaj" not in extractor.calls[0][1]
    assert result.text == "42"
    assert result.source == best
    assert result.question == "soru"


def test_empty_extraction_falls_back_to_no_context_answer():
    best = _passage("1", "pasaj")
    system = HybridQASystem(FakeRetriever([best]), FakeExtractor(reply=""))

    result = system.answer("soru")

    assert result.text == NO_CONTEXT_ANSWER
    assert result.source == best


def test_build_system_uses_given_passages_without_loading_files(monkeypatch):
    import hybrid_qa.pipeline as pipeline

    created = {}

    class FakeDense:
        def __init__(self, passages):
            created["dense"] = passages

    class FakeSparse:
        def __init__(self, passages):
            created["sparse"] = passages

    class FakeHybrid:
        def __init__(self, dense, sparse):
            created["hybrid"] = (dense, sparse)

    class FakeAnswerExtractor:
        pass

    def fail_load(*args, **kwargs):
        raise AssertionError("load_passages must not be called when passages are given")

    monkeypatch.setattr(pipeline, "DenseRetriever", FakeDense)
    monkeypatch.setattr(pipeline, "BM25Retriever", FakeSparse)
    monkeypatch.setattr(pipeline, "HybridRetriever", FakeHybrid)
    monkeypatch.setattr(pipeline, "AnswerExtractor", FakeAnswerExtractor)
    monkeypatch.setattr(pipeline, "load_passages", fail_load)

    passages = [_passage("1", "pasaj")]
    system = build_system(passages)

    assert isinstance(system, HybridQASystem)
    assert isinstance(system.extractor, FakeAnswerExtractor)
    assert created["dense"] == passages
    assert created["sparse"] == passages
    dense, sparse = created["hybrid"]
    assert isinstance(dense, FakeDense) and isinstance(sparse, FakeSparse)


def test_build_system_loads_passages_when_none_given(monkeypatch):
    import hybrid_qa.pipeline as pipeline

    loaded = [_passage("1", "yüklenen")]
    monkeypatch.setattr(pipeline, "load_passages", lambda *a, **k: loaded)
    monkeypatch.setattr(pipeline, "DenseRetriever", lambda passages: passages)
    monkeypatch.setattr(pipeline, "BM25Retriever", lambda passages: passages)
    monkeypatch.setattr(pipeline, "HybridRetriever", lambda dense, sparse: (dense, sparse))
    monkeypatch.setattr(pipeline, "AnswerExtractor", lambda: FakeExtractor())

    system = build_system()

    assert system.retriever == (loaded, loaded)
