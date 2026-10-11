# tests/test_context.py
from consultqa.models import Chunk, Hit
from consultqa.retrieve.context import build_context, long_context_order


def _hit(i):
    return Hit(Chunk(f"d#{i}", "d", i, (), f"t{i}"), 1.0, "rrf", "rrf")


def test_long_context_order_puts_best_hits_at_the_ends():
    ids = [h.chunk.chunk_id for h in long_context_order([_hit(i) for i in range(5)])]
    assert ids == ["d#0", "d#2", "d#4", "d#3", "d#1"]


def test_header_comes_from_the_heading_path():
    chunk = Chunk("d#0", "d", 0, ("Giriş", "Kurulum"), "metin")
    passages = build_context(
        [Hit(chunk, 1.0, "rrf", "rrf")],
        {"d": [chunk]},
        use_header=True,
        neighbours=0,
        max_passages=5,
    )
    assert passages[0].text == "Giriş > Kurulum: metin"


def test_neighbours_are_added_once():
    chunks = [Chunk(f"d#{i}", "d", i, (), f"t{i}") for i in range(3)]
    by_doc = {"d": chunks}
    passages = build_context(
        [Hit(chunks[1], 1.0, "rrf", "rrf")],
        by_doc,
        use_header=False,
        neighbours=1,
        max_passages=5,
    )
    assert sorted(p.chunk.chunk_id for p in passages) == ["d#0", "d#1", "d#2"]
    assert [p.number for p in passages] == [1, 2, 3]
