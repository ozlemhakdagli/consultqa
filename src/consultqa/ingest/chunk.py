"""Structure-aware chunking of Markdown text.

Headings set the section path, paragraphs are packed into chunks up to a token budget,
and no chunk crosses a heading boundary.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from consultqa.models import Chunk

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
# A heading is one or more "#" marks, a space, then text. "#!/bin/bash" is not a heading.
_HEADING = re.compile(r"^(#+)[ \t]+(\S.*)$")
_PARAGRAPH_SEP = "\n\n"
_SENTENCE_SEP = " "


def count_words(text: str) -> int:
    """Token count used by default: whitespace-separated words."""
    return len(text.split())


@dataclass(frozen=True)
class _Heading:
    level: int
    title: str


def _blocks(text: str) -> Iterator[str | _Heading]:
    """Yield paragraphs (as strings) and headings (as ``_Heading``) in reading order."""
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        heading = _HEADING.match(line)
        if heading is not None:
            if lines:
                yield "\n".join(lines)
                lines = []
            yield _Heading(level=len(heading.group(1)), title=heading.group(2).strip())
        elif line:
            lines.append(line)
        elif lines:
            yield "\n".join(lines)
            lines = []
    if lines:
        yield "\n".join(lines)


def _sections(text: str) -> list[tuple[tuple[str, ...], list[str]]]:
    """Group paragraphs by the heading path in force where they appear."""
    sections: list[tuple[tuple[str, ...], list[str]]] = []
    path: tuple[str, ...] = ()
    paragraphs: list[str] = []
    for block in _blocks(text):
        if isinstance(block, _Heading):
            sections.append((path, paragraphs))
            paragraphs = []
            path = path[: block.level - 1]
            if block.title:
                path = (*path, block.title)
        else:
            paragraphs.append(block)
    sections.append((path, paragraphs))
    return sections


# A piece of text with its token count. The count is taken once, when the piece is made, and a
# run of pieces is counted as the sum of its parts, so no growing run is ever counted again.
_Piece = tuple[str, int]


@dataclass(frozen=True)
class _Budget:
    max_tokens: int
    count_tokens: Callable[[str], int]
    paragraph_join: int  # tokens one paragraph separator adds between two pieces
    word_join: int  # tokens one space adds between two pieces


def _join_costs(count_tokens: Callable[[str], int]) -> tuple[int, int]:
    """Tokens that the paragraph separator and the space add when they join two pieces.

    Measured on a probe pair, so that a counter with a fixed offset per text (a tokenizer that
    adds special tokens, for example) is handled as well as word and character counts are.
    """
    one = count_tokens("x")
    return (
        count_tokens("x" + _PARAGRAPH_SEP + "x") - 2 * one,
        count_tokens("x" + _SENTENCE_SEP + "x") - 2 * one,
    )


def _texts(pieces: list[_Piece]) -> list[str]:
    return [text for text, _ in pieces]


def _split_by_words(text: str, tokens: int, budget: _Budget) -> list[_Piece]:
    """Split one unit above the budget into runs of whole words, each within the budget.

    ``tokens`` is the count of ``text`` itself. A single word above the budget is kept whole,
    since words are not cut.
    """
    if tokens <= budget.max_tokens:
        return [(text, tokens)]
    words = [(word, budget.count_tokens(word)) for word in text.split()]
    return _pack(words, " ", budget.word_join, budget)


def _sentence_runs(paragraph: str, tokens: int, budget: _Budget) -> list[_Piece]:
    """Split an oversized paragraph into sentences, and into word runs if a sentence is too long."""
    sentences = _SENTENCE_BOUNDARY.split(paragraph)
    # A paragraph with no sentence end is one sentence, and its count is already known.
    counts = [tokens] if len(sentences) == 1 else [budget.count_tokens(s) for s in sentences]
    return [
        run
        for sentence, sentence_tokens in zip(sentences, counts, strict=True)
        for run in _split_by_words(sentence, sentence_tokens, budget)
    ]


def _pack(units: list[_Piece], sep: str, join: int, budget: _Budget) -> list[_Piece]:
    """Join consecutive pieces while the joined text stays within the budget.

    The count of a run is a running sum: its first piece's count, plus for each further piece
    the join cost and that piece's count. Pieces are assumed to fit the budget on their own;
    ``_pack_section`` splits the ones that do not.
    """
    packed: list[_Piece] = []
    current: list[str] = []
    total = 0
    for text, tokens in units:
        if not current:
            current, total = [text], tokens
        elif total + join + tokens > budget.max_tokens:
            packed.append((sep.join(current), total))
            current, total = [text], tokens
        else:
            current.append(text)
            total += join + tokens
    if current:
        packed.append((sep.join(current), total))
    return packed


def _pack_section(paragraphs: list[str], budget: _Budget) -> list[str]:
    """Pack the paragraphs of one heading section, splitting oversized paragraphs."""
    texts: list[str] = []
    pending: list[_Piece] = []
    for paragraph in paragraphs:
        tokens = budget.count_tokens(paragraph)
        if tokens > budget.max_tokens:
            texts.extend(_texts(_pack(pending, _PARAGRAPH_SEP, budget.paragraph_join, budget)))
            pending = []
            sentences = _sentence_runs(paragraph, tokens, budget)
            texts.extend(_texts(_pack(sentences, _SENTENCE_SEP, budget.word_join, budget)))
        else:
            pending.append((paragraph, tokens))
    texts.extend(_texts(_pack(pending, _PARAGRAPH_SEP, budget.paragraph_join, budget)))
    return texts


def chunk_markdown(
    doc_id: str,
    text: str,
    *,
    max_tokens: int,
    count_tokens: Callable[[str], int] = count_words,
) -> list[Chunk]:
    """Split Markdown text into chunks with heading paths and positional ids.

    Each paragraph, sentence and word is counted once. A joined run is counted as the sum of its
    parts plus the join cost of its separator, which gives the same chunks as counting the joined
    text whole for counts of this kind: word counts, character counts, and tokenizers that add a
    fixed number of special tokens to each text.
    """
    paragraph_join, word_join = _join_costs(count_tokens)
    budget = _Budget(max_tokens, count_tokens, paragraph_join, word_join)
    pieces: list[tuple[tuple[str, ...], str]] = []
    for heading_path, paragraphs in _sections(text):
        for piece in _pack_section(paragraphs, budget):
            pieces.append((heading_path, piece))
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
