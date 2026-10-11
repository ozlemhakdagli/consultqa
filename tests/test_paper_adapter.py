from consultqa.baseline.paper_adapter import PaperMethod
from consultqa.models import Chunk


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
