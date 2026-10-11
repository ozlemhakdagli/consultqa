# tests/test_chunk.py
from docrag.ingest.chunk import chunk_markdown


def test_heading_path_and_boundaries():
    text = "# Giriş\nBirinci paragraf.\n\n## Kurulum\nİkinci paragraf.\n"
    chunks = chunk_markdown("d1", text, max_tokens=50)
    assert [c.heading_path for c in chunks] == [("Giriş",), ("Giriş", "Kurulum")]
    assert [c.text for c in chunks] == ["Birinci paragraf.", "İkinci paragraf."]


def test_packing_respects_max_tokens():
    text = "\n\n".join(["bir iki üç"] * 4)  # 3 tokens each
    chunks = chunk_markdown("d1", text, max_tokens=6)
    assert [c.text for c in chunks] == ["bir iki üç\n\nbir iki üç"] * 2


def test_empty_text_gives_no_chunks():
    assert chunk_markdown("d1", "  \n", max_tokens=10) == []


def test_chunk_ids_are_positional():
    chunks = chunk_markdown("d1", "a\n\nb", max_tokens=1)
    assert [c.chunk_id for c in chunks] == ["d1#0", "d1#1"]


# A shebang line is not a heading: a heading needs "#" marks, a space, then text.
def test_shebang_line_is_not_a_heading():
    chunks = chunk_markdown("d1", "#!/bin/bash\necho merhaba", max_tokens=50)
    assert [c.heading_path for c in chunks] == [()]
    assert chunks[0].text == "#!/bin/bash\necho merhaba"


def test_hash_without_a_space_is_not_a_heading():
    chunks = chunk_markdown("d1", "#Giriş\nmetin", max_tokens=50)
    assert [c.heading_path for c in chunks] == [()]


# An oversized unit without sentence ends is split by words, not kept whole.
def test_oversized_sentence_less_unit_is_split_by_words():
    text = " ".join(f"k{i}" for i in range(10))
    chunks = chunk_markdown("d1", text, max_tokens=4)
    assert [len(c.text.split()) for c in chunks] == [4, 4, 2]
    assert " ".join(c.text for c in chunks) == text
