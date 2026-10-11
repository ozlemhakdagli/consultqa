"""The Turkish sample keeps identical tokens and rankings when the language-aware fold is on."""

from pathlib import Path

from consultqa.config import BM25_PREFIX_LEN
from consultqa.eval.datasets import load_corpus_jsonl
from consultqa.eval.records import load_eval_jsonl
from consultqa.retrieve.sparse import SparseChannel
from consultqa.text import casefold_tr, document_folds, tokenize_tr

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "sample" / "corpus.jsonl"
DEV = ROOT / "data" / "sample" / "eval_dev.jsonl"  # the test split is never read here


def _sample():
    chunks = load_corpus_jsonl(CORPUS)
    questions = [record.question for record in load_eval_jsonl(DEV)]
    assert len(chunks) == 480 and len(questions) == 200
    return chunks, questions


def test_turkish_sample_gives_identical_tokens():
    chunks, questions = _sample()
    assert set(document_folds(chunks).values()) == {casefold_tr}
    old = SparseChannel(chunks)
    new = SparseChannel(chunks, per_document_fold=True)
    assert new._corpus == old._corpus
    assert not new._has_neutral
    for question in questions:
        assert new._query_terms(question) == tokenize_tr(question, BM25_PREFIX_LEN)


def test_turkish_sample_gives_identical_rankings_for_every_dev_question():
    chunks, questions = _sample()
    old = SparseChannel(chunks)
    new = SparseChannel(chunks, per_document_fold=True)
    for question in questions:
        before = [(hit.chunk.chunk_id, hit.score) for hit in old.search(question, 50)]
        after = [(hit.chunk.chunk_id, hit.score) for hit in new.search(question, 50)]
        assert after == before, question


def test_only_the_service_uses_the_language_aware_channel():
    # The evaluation builds SparseChannel(chunks) with the default, so its tokens cannot change.
    users = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src" / "consultqa").rglob("*.py")
        if "per_document_fold=True" in path.read_text(encoding="utf-8")
    ]
    assert users == ["src/consultqa/api/services.py"]
