import numpy as np

from consultqa.graph import build as graph_build
from consultqa.graph.build import build_graph
from consultqa.graph.terms import cross_references
from consultqa.models import Chunk


def _chunks():
    return [
        Chunk("d1#0", "d1", 0, (), "Stok modülü güncellendi"),
        Chunk("d1#1", "d1", 1, (), "Stok raporu eklendi"),
    ]


def test_shared_term_links_chunks():
    graph = build_graph(_chunks())
    idx = graph.node_index
    assert graph.adjacency[idx["c:d1#0"], idx["t:stok"]] > 0
    assert graph.adjacency[idx["t:stok"], idx["c:d1#1"]] > 0


def test_terms_in_too_many_chunks_are_dropped():
    chunks = [Chunk(f"d{i}#0", f"d{i}", 0, (), f"ortak metin {i}") for i in range(10)]
    assert "t:ortak" not in build_graph(chunks).node_index


def test_graph_is_symmetric_and_round_trips():
    graph = build_graph(_chunks())
    dense = graph.adjacency.toarray()
    assert np.allclose(dense, dense.T)
    restored = type(graph).from_bytes(graph.to_bytes())
    assert restored.nodes == graph.nodes
    assert np.allclose(restored.adjacency.toarray(), dense)


def test_cross_reference_links_to_numbered_heading():
    assert cross_references("Ayrıntı için Bölüm 3 bkz.") == {"3"}
    target = Chunk("d1#1", "d1", 1, ("3 Kurulum",), "kurulum")
    source = Chunk("d1#0", "d1", 0, (), "Ayrıntı için Bölüm 3 bkz.")
    graph = build_graph([source, target])
    assert graph.adjacency[graph.node_index["c:d1#0"], graph.node_index["c:d1#1"]] > 0


def _reference_cross_reference_pairs(chunks):
    """The original scan over every chunk, kept here as the reference for the faster scan."""
    chunk_list = list(chunks)
    headed = [chunk for chunk in chunk_list if chunk.heading_path]
    pairs = []
    for chunk in chunk_list:
        for number in sorted(cross_references(chunk.text)):
            for target in headed:
                if (
                    target.doc_id == chunk.doc_id
                    and target.chunk_id != chunk.chunk_id
                    and graph_build._heading_has_number(target.heading_path[0], number)
                ):
                    pairs.append((chunk, target))
    return pairs


def _multi_document_fixture():
    """Three interleaved documents with a numbered heading, a prefix trap and self references."""
    return [
        Chunk("a#0", "a", 0, (), "Ayrıntı için Bölüm 3 bkz. ve Bölüm 3.2 bkz."),
        Chunk("b#0", "b", 0, ("3 Ek",), "Bölüm 3 bkz. ek notu."),
        Chunk("a#1", "a", 1, ("3 Kurulum",), "Kurulum adımları stok modülü için."),
        Chunk("a#2", "a", 2, ("30 Ek",), "Bölüm 3 bkz. başka bölüm."),
        Chunk("c#0", "c", 0, (), "Bölüm 3 bkz. tek belge."),
        Chunk("a#3", "a", 3, ("3.2 Tanım",), "Bölüm 3 bkz. ve bkz. 3.2."),
        Chunk("b#1", "b", 1, ("",), "Bölüm 3 bkz."),
        Chunk("a#4", "a", 4, (), "Bölüm 3 bkz. Bölüm 3 bkz."),
    ]


def _generated_fixture():
    """20 documents of 12 chunks: every third chunk is headed, the rest cite a number."""
    chunks = []
    for position in range(12):
        for d in range(20):
            doc_id = f"doc{d}"
            if position % 3 == 0:
                path = (f"{(d + position) % 6 + 1} Bölüm",)
                chunks.append(Chunk(f"{doc_id}#{position}", doc_id, position, path, "stok raporu"))
            else:
                text = f"kurulum notu Bölüm {(d * 5 + position) % 6 + 1} bkz."
                chunks.append(Chunk(f"{doc_id}#{position}", doc_id, position, (), text))
    return chunks


def test_cross_reference_pairs_keep_the_full_scan_order():
    for chunks in (_multi_document_fixture(), _generated_fixture()):
        reference = _reference_cross_reference_pairs(chunks)
        assert reference, "the fixture must contain cross references"
        assert list(graph_build._cross_reference_pairs(chunks)) == reference


def test_graph_bytes_match_the_full_scan(monkeypatch):
    fixtures = [_multi_document_fixture(), _generated_fixture()]
    current = [build_graph(chunks).to_bytes() for chunks in fixtures]
    monkeypatch.setattr(graph_build, "_cross_reference_pairs", _reference_cross_reference_pairs)
    reference = [build_graph(chunks).to_bytes() for chunks in fixtures]
    assert current == reference
