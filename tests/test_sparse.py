import pytest

from consultqa.models import Chunk
from consultqa.retrieve.sparse import SparseChannel
from consultqa.text import tokenize_tr


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
