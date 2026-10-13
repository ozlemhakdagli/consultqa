# tests/test_chunk.py
import random
import re
from collections.abc import Callable

from consultqa.ingest.chunk import _sections, chunk_markdown, chunk_pages, count_words
from consultqa.models import Chunk


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


# Reference copy of the chunking before the running count was introduced. Each growing run was
# re-counted in full. The chunker must give exactly the same chunks for every input.
_REFERENCE_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


def _reference_chunks(
    doc_id: str, text: str, *, max_tokens: int, count_tokens: Callable[[str], int]
) -> list[Chunk]:
    def split_by_words(unit: str) -> list[str]:
        if count_tokens(unit) <= max_tokens:
            return [unit]
        runs: list[str] = []
        current: list[str] = []
        for word in unit.split():
            if current and count_tokens(" ".join([*current, word])) > max_tokens:
                runs.append(" ".join(current))
                current = []
            current.append(word)
        if current:
            runs.append(" ".join(current))
        return runs

    def pack(units: list[str], sep: str) -> list[str]:
        packed: list[str] = []
        current: list[str] = []
        for unit in units:
            if current and count_tokens(sep.join([*current, unit])) > max_tokens:
                packed.append(sep.join(current))
                current = [unit]
            else:
                current.append(unit)
        if current:
            packed.append(sep.join(current))
        return packed

    def pack_section(paragraphs: list[str]) -> list[str]:
        texts: list[str] = []
        pending: list[str] = []
        for paragraph in paragraphs:
            if count_tokens(paragraph) > max_tokens:
                texts.extend(pack(pending, "\n\n"))
                pending = []
                sentences = [
                    run
                    for sentence in _REFERENCE_SENTENCE_BOUNDARY.split(paragraph)
                    for run in split_by_words(sentence)
                ]
                texts.extend(pack(sentences, " "))
            else:
                pending.append(paragraph)
        texts.extend(pack(pending, "\n\n"))
        return texts

    pieces = [
        (heading_path, piece)
        for heading_path, paragraphs in _sections(text)
        for piece in pack_section(paragraphs)
    ]
    return [
        Chunk(
            chunk_id=f"{doc_id}#{position}",
            doc_id=doc_id,
            position=position,
            heading_path=heading_path,
            text=piece,
        )
        for position, (heading_path, piece) in enumerate(pieces)
    ]


_WORDS = (
    "alpha Beta. gamma! delta? çok şöyle. x|y | --- k a.b 1.5 #tag #!/bin/sh ğüş sonuç. end?"
).split()
_GAPS = (" ", " ", "  ", "\t", " \u00a0 ")  # a no-break space is whitespace for both counts


def _random_document(rng: random.Random) -> str:
    """Markdown with headings, long paragraphs, pipe tables, empty lines and odd spacing."""

    def words(count: int) -> str:
        parts = [rng.choice(_WORDS)]
        for _ in range(count - 1):
            parts.append(rng.choice(_GAPS))
            parts.append(rng.choice(_WORDS))
        return "".join(parts)

    def line() -> str:
        roll = rng.random()
        if roll < 0.2:  # a row of a pipe table
            cells = [words(rng.randint(1, 3)) for _ in range(rng.randint(2, 6))]
            text = "| " + " | ".join(cells) + " |"
        elif roll < 0.3:  # a long run of prose with no blank line
            text = words(rng.randint(60, 150))
        elif roll < 0.4:  # a heading inside a paragraph
            text = "#" * rng.randint(1, 4) + rng.choice((" ", "\t", "   ")) + words(3)
        else:
            text = words(rng.randint(1, 20))
        return rng.choice(("", "", "  ", "\t")) + text

    lines: list[str] = []
    for _ in range(rng.randint(1, 4)):
        if rng.random() < 0.6:
            lines.append("#" * rng.randint(1, 3) + " " + words(rng.randint(1, 4)))
        for _ in range(rng.randint(1, 4)):
            lines.extend(line() for _ in range(rng.randint(1, 5)))
            lines.extend(rng.choice(("", "   ", "\t")) for _ in range(rng.randint(1, 3)))
    return rng.choice(("\n", "\r\n")).join(lines)


def _count_chars(text: str) -> int:
    return len(text)


def test_chunks_match_the_reference_on_generated_documents():
    rng = random.Random(20261012)  # noqa: S311 (reproducible test input, not a secret)
    total_chunks = 0
    for index in range(400):
        text = _random_document(rng)
        if index % 2:
            count, max_tokens = count_words, rng.randint(1, 40)
        else:
            count, max_tokens = _count_chars, rng.randint(1, 300)
        expected = _reference_chunks("d1", text, max_tokens=max_tokens, count_tokens=count)
        actual = chunk_markdown("d1", text, max_tokens=max_tokens, count_tokens=count)
        assert actual == expected, f"document {index} with max_tokens={max_tokens}"
        total_chunks += len(actual)
    assert total_chunks > 2000  # the documents really do produce many chunks


def test_each_piece_is_counted_once_not_as_a_growing_run():
    table = "\n".join(
        "| " + " | ".join(f"c{row}{col}" for col in range(6)) + " |" for row in range(300)
    )
    counted: list[str] = []

    def counting(text: str) -> int:
        counted.append(text)
        return count_words(text)

    chunk_markdown("d1", table, max_tokens=50, count_tokens=counting)

    # One call per word, one for the table paragraph and three constant probes at most.
    assert len(counted) <= len(table.split()) + 4
    # Each character of the table is counted as a paragraph and as a word, nothing more.
    assert sum(len(text) for text in counted) <= 2 * len(table) + 20


def test_chunk_pages_sets_page_and_keeps_positions():
    chunks = chunk_pages("d", ["# A\n\nalpha beta", "gamma delta"], max_tokens=50)
    assert [c.page for c in chunks] == [1, 2]
    assert [c.position for c in chunks] == [0, 1]
    assert [c.chunk_id for c in chunks] == ["d#0", "d#1"]


def test_chunk_pages_carries_heading_path():
    chunks = chunk_pages("d", ["# A\n\nalpha beta", "gamma delta"], max_tokens=50)
    assert chunks[1].heading_path == ("A",)


def test_chunk_pages_blank_page_keeps_numbering():
    chunks = chunk_pages("d", ["one", "  \n", "three"], max_tokens=50)
    assert [c.page for c in chunks] == [1, 3]
