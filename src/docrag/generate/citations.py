"""Parse a model answer: keep in-range ``[n]`` citations, drop the others, detect abstention."""

import re
from dataclasses import dataclass

from docrag.config import ABSTAIN_WORD
from docrag.text import casefold_tr

# A marker "[n]" or a list "[n, m]", with the whitespace before it, so that a removed marker
# leaves no gap behind. A bracket that follows a word character ("arr[3]") is an index, not a
# citation, so it is left alone.
_MARKER = re.compile(r"(\s*)(?<!\w)\[(\d+(?:\s*,\s*\d+)*)\]")
_NUMBER = re.compile(r"\d+")


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
        numbers = [int(token) for token in _NUMBER.findall(match.group(2))]
        kept: list[int] = []
        for number in numbers:
            if 1 <= number <= n_passages:
                kept.append(number)
                if number not in citations:
                    citations.append(number)
            elif number not in dropped:
                dropped.append(number)
        if not kept:
            return ""
        if len(kept) == len(numbers):
            return match.group(0)
        # Part of a list is out of range: keep the valid numbers in the same bracket form.
        return f"{match.group(1)}[{', '.join(str(number) for number in kept)}]"

    cleaned = _MARKER.sub(_keep_or_drop, raw).strip()
    core = casefold_tr(cleaned.rstrip(".").strip())
    if not core or core == ABSTAIN_WORD:
        return ParsedAnswer(text=None, citations=citations, dropped=dropped)
    return ParsedAnswer(text=cleaned, citations=citations, dropped=dropped)
