"""Prompt context assembly: long-context ordering, heading headers and neighbour passages."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from consultqa.models import Chunk, Hit


@dataclass(frozen=True)
class ContextPassage:
    """One numbered passage of the prompt context."""

    number: int
    chunk: Chunk
    header: str
    text: str


def long_context_order(hits: Sequence[Hit]) -> list[Hit]:
    """Reorder ranked hits as ranks ``1, 3, 5, ..., 6, 4, 2`` so the best sit at both ends."""
    ranked = list(hits)
    return ranked[0::2] + ranked[1::2][::-1]


def _window(
    chunk: Chunk, chunks_by_doc: Mapping[str, Sequence[Chunk]], neighbours: int
) -> list[Chunk]:
    """Return ``chunk`` with up to ``neighbours`` chunks on each side, in reading order."""
    width = max(neighbours, 0)
    by_position = {c.position: c for c in chunks_by_doc.get(chunk.doc_id, ())}
    window: list[Chunk] = []
    for offset in range(-width, width + 1):
        if offset == 0:
            window.append(chunk)
            continue
        neighbour = by_position.get(chunk.position + offset)
        if neighbour is not None:
            window.append(neighbour)
    return window


def build_context(
    hits: Sequence[Hit],
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
    *,
    use_header: bool,
    neighbours: int,
    max_passages: int,
) -> list[ContextPassage]:
    """Build the numbered passages for the prompt from the first ``max_passages`` hits.

    The hits are reordered by ``long_context_order``. Each one is expanded with up to
    ``neighbours`` chunks on each side from the same document. A chunk already present is not
    added again. With ``use_header`` the passage text starts with its heading path.
    """
    ordered = long_context_order(hits[:max_passages])
    seen: set[str] = set()
    passages: list[ContextPassage] = []
    for hit in ordered:
        for chunk in _window(hit.chunk, chunks_by_doc, neighbours):
            if chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            header = " > ".join(chunk.heading_path) if use_header else ""
            text = f"{header}: {chunk.text}" if header else chunk.text
            passages.append(ContextPassage(len(passages) + 1, chunk, header, text))
    return passages
