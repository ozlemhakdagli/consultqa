"""Structure-aware chunking of Markdown text.

Headings set the section path, paragraphs are packed into chunks up to a token budget,
and no chunk crosses a heading boundary.
"""

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from docrag.models import Chunk

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
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
        if line.startswith("#"):
            if lines:
                yield "\n".join(lines)
                lines = []
            stripped = line.lstrip("#")
            yield _Heading(level=len(line) - len(stripped), title=stripped.strip())
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


def _pack(
    units: list[str], sep: str, max_tokens: int, count_tokens: Callable[[str], int]
) -> list[str]:
    """Join consecutive units while the joined text stays within ``max_tokens``.

    A single unit above the budget is kept whole rather than cut mid-word.
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
            sentences = _SENTENCE_BOUNDARY.split(paragraph)
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
