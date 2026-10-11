import pytest

from consultqa.baseline import paper_adapter
from consultqa.baseline.paper_adapter import PaperMethod
from consultqa.models import Chunk

CHUNKS = [
    Chunk("d#0", "d", 0, (), "siparis tablo filtreleme"),
    Chunk("d#1", "d", 1, (), "stok performans"),
    Chunk("d#2", "d", 2, (), "stok performans"),
]


class FakeIndex:
    def __init__(self, passages):
        self.passages = list(passages)


class FakeReference:
    """Stands in for reference/paper_method/pipeline.py; counts the searches and the readers."""

    NO_CONTEXT_ANSWER = "no context"
    Retriever = FakeIndex

    def __init__(self) -> None:
        self.searches = 0
        self.readers_built = 0

    def build_reader(self):
        self.readers_built += 1
        return FakeReader()

    def candidate_passages(self, retriever, query, mode):
        self.searches += 1
        return [text for text in retriever.passages if any(w in text for w in query.split())]

    def answer(self, retriever, reader, query, mode):
        passages = self.candidate_passages(retriever, query, mode)
        if not passages:
            return self.NO_CONTEXT_ANSWER
        return str(reader(question=query, context=passages[0])["answer"])


class FakeReader:
    def __call__(self, question, context):
        return {"answer": context.split()[0]}


@pytest.fixture
def reference(monkeypatch):
    fake = FakeReference()
    monkeypatch.setattr(paper_adapter, "load_reference_module", lambda: fake)
    return fake


def test_asking_the_same_question_twice_runs_retrieval_once(reference):
    method = PaperMethod(CHUNKS)
    ranked = method.ranked_chunk_ids("stok")
    answer = method.answer("stok")
    assert method.ranked_chunk_ids("stok") == ranked
    assert method.answer("stok") == answer
    assert reference.searches == 1


def test_a_new_question_runs_retrieval_again(reference):
    method = PaperMethod(CHUNKS)
    method.ranked_chunk_ids("stok")
    method.ranked_chunk_ids("siparis")
    assert reference.searches == 2


def test_memoised_passages_give_the_same_result_as_a_fresh_adapter(reference):
    memoised = PaperMethod(CHUNKS)
    memoised.ranked_chunk_ids("siparis")
    memoised.answer("stok")
    fresh = PaperMethod(CHUNKS)
    assert memoised.ranked_chunk_ids("stok") == fresh.ranked_chunk_ids("stok")
    assert memoised.answer("stok") == fresh.answer("stok")


def test_two_adapters_share_one_reader(reference):
    PaperMethod(CHUNKS)
    PaperMethod(CHUNKS)
    assert reference.readers_built == 1


class FakeRetriever:
    def dense(self, query, k=5):
        return ["metin A", "metin B"]

    def sparse(self, query, k=5):
        return ["metin B", "metin C"]


def test_duplicate_texts_map_to_every_chunk_id():
    chunks = [
        Chunk("d#0", "d", 0, (), "metin A"),
        Chunk("d#1", "d", 1, (), "metin B"),
        Chunk("d#2", "d", 2, (), "metin B"),
        Chunk("d#3", "d", 3, (), "metin C"),
    ]
    method = PaperMethod(chunks, retriever=FakeRetriever())
    assert method.ranked_chunk_ids("q") == ["d#0", "d#1", "d#3"]
    assert method.ids_for_text("metin B") == ["d#1", "d#2"]
