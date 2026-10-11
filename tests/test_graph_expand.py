from docrag.graph.build import build_graph
from docrag.graph.expand import expand
from docrag.models import Chunk


def _setup():
    chunks = [
        Chunk("d1#0", "d1", 0, (), "Stok modülü"),
        Chunk("d1#1", "d1", 1, (), "Stok raporu"),
        Chunk("d2#0", "d2", 0, (), "Tamamen farklı konu"),  # other document, no shared term
    ]
    return build_graph(chunks), {c.chunk_id: c for c in chunks}


def test_seed_mass_reaches_chunks_sharing_a_term():
    graph, chunks = _setup()
    hits = expand(graph, {"d1#0": 1.0}, ["stok"], chunks, restart=0.7, k=5)
    ids = [h.chunk.chunk_id for h in hits]
    assert ids[:2] == ["d1#0", "d1#1"] or ids[:2] == ["d1#1", "d1#0"]
    assert "d2#0" not in ids


def test_full_restart_returns_only_the_reset_mass():
    graph, chunks = _setup()
    hits = expand(graph, {"d1#0": 1.0}, [], chunks, restart=1.0, k=5)
    assert [h.chunk.chunk_id for h in hits] == ["d1#0"]


def test_no_seeds_and_no_terms_returns_nothing():
    graph, chunks = _setup()
    assert expand(graph, {}, [], chunks, restart=0.7, k=5) == []
