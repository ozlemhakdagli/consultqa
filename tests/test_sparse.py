from docrag.models import Chunk
from docrag.retrieve.sparse import SparseChannel


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


def test_single_chunk_collection_matches_a_shared_token():
    chunks = [Chunk("d1#0", "d1", 0, (), "Stok modülü")]
    assert [h.chunk.chunk_id for h in SparseChannel(chunks).search("stok", k=5)] == ["d1#0"]
    assert SparseChannel(chunks).search("sipariş", k=5) == []
