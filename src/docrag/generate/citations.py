"""Parse a model answer: keep in-range ``[n]`` citations, drop the others, detect abstention."""

import re
from dataclasses import dataclass

from docrag.config import ABSTAIN_WORD
from docrag.text import casefold_tr

# A marker with the whitespace before it, so that a removed marker leaves no gap behind.
_MARKER = re.compile(r"\s*\[(\d+)\]")


@dataclass(frozen=True)
class ParsedAnswer:
    """An answer with its citations; ``text`` is None when the model abstained or said nothing.

    ``citations`` are the valid passage numbers in order of first appearance. ``dropped`` are the
    numbers outside ``1..n`` in order of first appearance; their markers are removed from ``text``.
    """

    text: str | None
    citations: list[int]
    dropped: list[int]


def parse_answer(raw: str, n_passages: int) -> ParsedAnswer:
    """Parse ``raw`` against ``n_passages`` numbered passages."""
    citations: list[int] = []
    dropped: list[int] = []

    def _keep_or_drop(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if 1 <= number <= n_passages:
            if number not in citations:
                citations.append(number)
            return match.group(0)
        if number not in dropped:
            dropped.append(number)
        return ""

    cleaned = _MARKER.sub(_keep_or_drop, raw).strip()
    core = casefold_tr(cleaned.rstrip(".").strip())
    if not core or core == ABSTAIN_WORD:
        return ParsedAnswer(text=None, citations=citations, dropped=dropped)
    return ParsedAnswer(text=cleaned, citations=citations, dropped=dropped)
