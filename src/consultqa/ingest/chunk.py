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


def _split_by_words(text: str, max_tokens: int, count_tokens: Callable[[str], int]) -> list[str]:
    """Split one unit above the budget into runs of whole words, each within the budget.

    A single word above the budget is kept whole, since words are not cut.
    """
    if count_tokens(text) <= max_tokens:
        return [text]
    runs: list[str] = []
    current: list[str] = []
    for word in text.split():
        if current and count_tokens(" ".join([*current, word])) > max_tokens:
            runs.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        runs.append(" ".join(current))
    return runs


def _pack(
    units: list[str], sep: str, max_tokens: int, count_tokens: Callable[[str], int]
) -> list[str]:
    """Join consecutive units while the joined text stays within ``max_tokens``.

    Units are assumed to fit the budget on their own; ``_pack_section`` splits the ones that do not.
    """
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


def _pack_section(
    paragraphs: list[str], max_tokens: int, count_tokens: Callable[[str], int]
) -> list[str]:
    """Pack the paragraphs of one heading section, splitting oversized paragraphs."""
    texts: list[str] = []
    pending: list[str] = []
    for paragraph in paragraphs:
        if count_tokens(paragraph) > max_tokens:
            texts.extend(_pack(pending, _PARAGRAPH_SEP, max_tokens, count_tokens))
            pending = []
            sentences = [
                run
                for sentence in _SENTENCE_BOUNDARY.split(paragraph)
                for run in _split_by_words(sentence, max_tokens, count_tokens)
            ]
            texts.extend(_pack(sentences, _SENTENCE_SEP, max_tokens, count_tokens))
        else:
            pending.append(paragraph)
    texts.extend(_pack(pending, _PARAGRAPH_SEP, max_tokens, count_tokens))
    return texts


def chunk_markdown(
    doc_id: str,
    text: str,
    *,
    max_tokens: int,
    count_tokens: Callable[[str], int] = count_words,
) -> list[Chunk]:
    """Split Markdown text into chunks with heading paths and positional ids."""
    pieces: list[tuple[tuple[str, ...], str]] = []
    for heading_path, paragraphs in _sections(text):
        for piece in _pack_section(paragraphs, max_tokens, count_tokens):
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
