import numpy as np
import pytest
from rank_bm25 import BM25Okapi

from consultqa.config import BM25_PREFIX_LEN
from consultqa.models import Chunk
from consultqa.retrieve.sparse import SparseChannel
from consultqa.text import casefold_neutral, document_folds, tokenize, tokenize_tr


def _chunks():
    return [
        Chunk("d1#0", "d1", 0, (), "Sipariş modülünde tablo filtreleme yapıldı"),
        Chunk("d1#1", "d1", 1, (), "Stok modülü performans iyileştirmesi"),
        # A neutral third chunk: with only two chunks BM25 IDF is 0 for any term in one chunk.
        Chunk("d1#2", "d1", 2, (), "Raporlar ekranına dışa aktarma eklendi"),
    ]


def test_turkish_inflections_match():
    hits = SparseChannel(_chunks()).search("siparişlerde filtreleme", k=2)
    assert hits[0].chunk.chunk_id == "d1#0"


# [R1] Dotted I in a query matches the document.
def test_case_is_folded_before_matching():
    hits = SparseChannel(_chunks()).search("SİPARİŞ", k=2)
    assert hits[0].chunk.chunk_id == "d1#0"


# [R2] A punctuation-only question produces no sparse hits and does not raise.
def test_punctuation_query_gives_no_hits():
    assert SparseChannel(_chunks()).search("?!", k=2) == []
    assert SparseChannel(_chunks()).search("   ", k=2) == []


# With fewer than three chunks, BM25 gives no positive scores, so ranking is by shared tokens.
def test_two_chunk_collection_ranks_by_shared_tokens():
    chunks = [
        Chunk("d1#0", "d1", 0, (), "Sipariş modülü tablo filtreleme"),
        Chunk("d1#1", "d1", 1, (), "Stok modülü performans"),
    ]
    assert [h.chunk.chunk_id for h in SparseChannel(chunks).search("Stok", k=5)] == ["d1#1"]
    assert SparseChannel(chunks).search("bilinmeyen kelime", k=5) == []
    both = SparseChannel(chunks).search("modülü performans", k=5)
    assert [h.chunk.chunk_id for h in both] == ["d1#1", "d1#0"]


def _english_chunks():
    return [
        Chunk("e#0", "e", 0, ("Shipping",), "Parcels come weekly."),
        Chunk("e#1", "e", 1, ("Support",), "Calls come daily."),
        Chunk("e#2", "e", 2, ("Billing",), "Invoices come monthly."),
    ]


def _turkish_chunks():
    return [
        Chunk("t#0", "t", 0, (), "Işık çağrıları her gün cevaplanır."),
        Chunk("t#1", "t", 1, (), "Paketler her hafta gelir."),
        Chunk("t#2", "t", 2, (), "Faturalar ayda bir gelir."),
    ]


@pytest.mark.parametrize(
    "question",
    ["how often do invoices come", "HOW OFTEN DO INVOICES COME", "How often do Invoices come"],
)
def test_english_capitalised_words_match_questions_in_any_case(question):
    hits = SparseChannel(_english_chunks(), per_document_fold=True).search(question, k=3)
    assert hits[0].chunk.chunk_id == "e#2"


def test_turkish_documents_keep_the_turkish_fold_in_a_mixed_library():
    turkish = _turkish_chunks()
    channel = SparseChannel([*turkish, *_english_chunks()], per_document_fold=True)
    assert channel._has_neutral
    for question in ("IŞIK", "ışık"):
        assert channel.search(question, k=1)[0].chunk.chunk_id == "t#0"
    assert channel._corpus[0] == tokenize_tr(turkish[0].text, 5)


def test_a_turkish_only_library_adds_no_query_variants():
    channel = SparseChannel(_turkish_chunks(), per_document_fold=True)
    assert not channel._has_neutral
    assert channel._query_terms("Isparta nerede") == tokenize_tr("Isparta nerede", 5)


def test_a_small_english_library_ranks_by_shared_tokens():
    chunks = [Chunk("e#0", "e", 0, (), "Invoices come monthly."),
              Chunk("e#1", "e", 1, (), "Parcels come weekly.")]  # fmt: skip
    channel = SparseChannel(chunks, per_document_fold=True)
    for question in ("invoices", "INVOICES"):
        assert [h.chunk.chunk_id for h in channel.search(question, k=5)] == ["e#0"]


def test_single_chunk_collection_matches_a_shared_token():
    chunks = [Chunk("d1#0", "d1", 0, (), "Stok modülü")]
    assert [h.chunk.chunk_id for h in SparseChannel(chunks).search("stok", k=5)] == ["d1#0"]
    assert SparseChannel(chunks).search("sipariş", k=5) == []


# The BM25 search as it was before the per-term arrays were cached: BM25Okapi.get_scores on every
# query, rebuilding the length and frequency arrays each time. The channel must agree with it.
class _PreviousSparseChannel:
    def __init__(self, chunks, *, per_document_fold=False):
        self._chunks = list(chunks)
        if per_document_fold:
            folds = document_folds(self._chunks)
            self._corpus = [
                tokenize(c.text, BM25_PREFIX_LEN, fold=folds[c.doc_id]) for c in self._chunks
            ]
            self._has_neutral = any(fold is casefold_neutral for fold in folds.values())
        else:
            self._corpus = [tokenize_tr(c.text, BM25_PREFIX_LEN) for c in self._chunks]
            self._has_neutral = False
        self._index = BM25Okapi(self._corpus)

    def search(self, query, k):
        turkish = tokenize_tr(query, BM25_PREFIX_LEN)
        terms = turkish
        if self._has_neutral:
            neutral = tokenize(query, BM25_PREFIX_LEN, fold=casefold_neutral)
            terms = turkish + [n for t, n in zip(turkish, neutral, strict=False) if t != n]
        if not terms:
            return []
        scores = self._index.get_scores(terms)
        ranked = sorted(
            (i for i in range(len(self._chunks)) if scores[i] > 0), key=lambda i: -scores[i]
        )
        return [(self._chunks[i].chunk_id, float(scores[i])) for i in ranked[:k]]


_TURKISH_WORDS = [
    "sipariş", "modülü", "stok", "tablo", "filtreleme", "performans", "Işık", "çağrı", "ışık",
    "fatura", "ayda", "temizleme", "dışa", "aktarma", "SİPARİŞ",
]  # fmt: skip
_ENGLISH_WORDS = ["Invoices", "come", "Parcels", "weekly", "Shipping", "I", "monthly", "daily"]
_QUERIES = [
    "stok modülü",
    "SİPARİŞ tablo filtreleme",
    "Işık ışık",
    "invoices come",
    "I come weekly",
    "Parcels Shipping monthly",
    "stok stok modülü",  # a repeated term adds its contribution twice
    "faturalar ayda",
    "bilinmeyen kelime",  # no term in the library
    "?!",  # no tokens at all
    "stok modülü",  # asked again: the second round reads the cached arrays
]


def _generated_chunks(count=60):
    """Deterministic chunks: documents d0 and d1 hold Turkish words, e0 and e1 English ones."""
    chunks = []
    for i in range(count):
        doc = ("d0", "d1", "e0", "e1")[i % 4]
        vocabulary = _ENGLISH_WORDS if doc.startswith("e") else _TURKISH_WORDS
        words = [vocabulary[(i * 7 + j * 5) % len(vocabulary)] for j in range(3 + i % 10)]
        chunks.append(Chunk(f"{doc}#{i}", doc, i // 4, (), " ".join(words)))
    return chunks


@pytest.mark.parametrize("per_document_fold", [False, True])
def test_hits_equal_the_previous_implementation(per_document_fold):
    chunks = _generated_chunks()
    channel = SparseChannel(chunks, per_document_fold=per_document_fold)
    previous = _PreviousSparseChannel(chunks, per_document_fold=per_document_fold)
    assert len(previous.search("stok modülü", k=len(chunks))) > 3  # the comparison is not empty
    for _ in range(2):  # the second round answers from the arrays cached by the first
        for query in _QUERIES:
            for k in (3, len(chunks)):
                got = [(h.chunk.chunk_id, h.score) for h in channel.search(query, k=k)]
                assert got == previous.search(query, k=k), (query, k)


def test_length_and_term_arrays_are_built_once_and_reused():
    channel = SparseChannel(_generated_chunks())
    terms = tokenize_tr("stok modülü", BM25_PREFIX_LEN)
    channel.search("stok modülü", k=5)
    lengths = channel._doc_lengths
    cached = dict(channel._term_frequencies)
    assert set(cached) == set(terms)
    channel.search("stok modülü", k=5)
    assert channel._doc_lengths is lengths
    assert all(channel._term_frequencies[t] is cached[t] for t in terms)
    index = channel._index
    np.testing.assert_array_equal(lengths, np.array(index.doc_len))
    for term in terms:
        expected = np.array([(doc.get(term) or 0) for doc in index.doc_freqs])
        np.testing.assert_array_equal(cached[term], expected)


def test_terms_missing_from_the_library_are_not_cached():
    channel = SparseChannel(_generated_chunks())
    channel.search("bilinmeyen stok", k=5)
    assert set(channel._term_frequencies) == {"stok"}
