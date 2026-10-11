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
