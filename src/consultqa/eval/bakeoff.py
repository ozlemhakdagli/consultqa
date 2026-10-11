"""Score a parser against Markdown ground truth for the parser bake-off.

Two measures per file. Word F1 compares multisets of Turkish tokens from ``tokenize_tr``.
Heading recall takes each ``#`` heading in the ground truth and checks whether the parser output
has a ``#`` heading with the same normalised text; the heading level is not compared. A parse
that raises ``ParseError`` scores zero on both measures and is counted in ``failed``.
"""

import re
import time
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from statistics import mean
from typing import Any

from consultqa.ingest.parse import ParseError, Parser
from consultqa.text import normalize_answer, tokenize_tr

_HEADING = re.compile(r"^\s*#{1,6}\s+(\S.*?)\s*$")


def _headings(markdown: str) -> list[str]:
    """Return the normalised text of every ``#`` heading line, in order."""
    found = []
    for line in markdown.splitlines():
        match = _HEADING.match(line)
        if match:
            found.append(normalize_answer(match.group(1)))
    return found


def _word_f1(predicted: str, truth: str) -> float:
    pred = Counter(tokenize_tr(predicted))
    gold = Counter(tokenize_tr(truth))
    if not pred and not gold:
        return 1.0
    overlap = sum((pred & gold).values())
    if overlap == 0:
        return 0.0
    precision = overlap / sum(pred.values())
    recall = overlap / sum(gold.values())
    return 2 * precision * recall / (precision + recall)


def _heading_recall(predicted: str, truth: str) -> float:
    truth_headings = _headings(truth)
    if not truth_headings:
        return 1.0
    predicted_headings = set(_headings(predicted))
    found = sum(1 for heading in truth_headings if heading in predicted_headings)
    return found / len(truth_headings)


def parser_scores(parser: Parser, pairs: Sequence[tuple[Path, Path]]) -> dict[str, Any]:
    """Parse each source file and compare the output with its Markdown ground truth.

    ``pairs`` holds ``(source, truth)`` pairs. The result has the mean ``word_f1`` and
    ``heading_recall`` over all pairs, the mean ``seconds_per_file`` (the first call of a
    parser that loads models includes the load time), the count of ``failed`` parses, and
    ``per_file`` with the score and time of each pair.
    """
    if not pairs:
        raise ValueError("parser_scores needs at least one (source, truth) pair")
    per_file: list[dict[str, Any]] = []
    for source, truth_path in pairs:
        truth = truth_path.read_text(encoding="utf-8")
        started = time.perf_counter()
        try:
            output = parser.parse(source)
            failed = False
        except ParseError:
            output = None
            failed = True
        seconds = time.perf_counter() - started
        if output is None:
            word_f1 = 0.0
            heading_recall = 0.0
        else:
            word_f1 = _word_f1(output, truth)
            heading_recall = _heading_recall(output, truth)
        per_file.append(
            {
                "file": source.name,
                "failed": failed,
                "word_f1": word_f1,
                "heading_recall": heading_recall,
                "seconds": seconds,
            }
        )
    return {
        "parser": parser.name,
        "files": len(per_file),
        "failed": sum(1 for row in per_file if row["failed"]),
        "word_f1": mean(row["word_f1"] for row in per_file),
        "heading_recall": mean(row["heading_recall"] for row in per_file),
        "seconds_per_file": mean(row["seconds"] for row in per_file),
        "per_file": per_file,
    }
