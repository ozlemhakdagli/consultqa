import numpy as np

from docrag.graph.build import build_graph
from docrag.graph.terms import cross_references
from docrag.models import Chunk


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
