from docrag.config import PRESETS
from docrag.eval.runner import make_answer_fn
from docrag.models import Chunk, Hit
from docrag.retrieve.pipeline import RetrievalResult


class RecordingReader:
    def __init__(self):
        self.contexts = []

    def answer(self, question, context):
        self.contexts.append(context)
        return "x"


# The extractive reader must read the best-ranked passage, never a neighbour added for context.
def test_extractive_reader_gets_top_hit_not_neighbour():
    chunks = [
        Chunk("d#0", "d", 0, ("Giriş",), "onceki metin"),
        Chunk("d#1", "d", 1, ("Giriş",), "en iyi metin"),
        Chunk("d#2", "d", 2, ("Giriş",), "sonraki metin"),
    ]
    by_doc = {"d": chunks}
    result = RetrievalResult(hits=[Hit(chunks[1], 1.0, "rrf", "rrf")], trace=[])
    reader = RecordingReader()
    answer = make_answer_fn(PRESETS["L4"], reader=reader, llm=None, chunks_by_doc=by_doc)
    answer("soru", result)
    assert reader.contexts == ["Giriş: en iyi metin"]
