"""Evaluation record dataclass and JSONL persistence for question sets."""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ANSWER_TYPES = frozenset({"span", "version", "set"})
TAGS = frozenset({"keyword", "semantic"})
SPLITS = frozenset({"dev", "test"})
ORIGINS = frozenset({"generated", "agent-written", "private"})


@dataclass(frozen=True)
class EvalRecord:
    """One evaluation question with its accepted answers and gold passage ids."""

    question: str
    accepted_answers: list[str]
    gold_passage_ids: list[str]
    answer_type: str
    tag: str
    family_id: str
    cluster_id: str
    split: str
    origin: str
    overlap: float

    def __post_init__(self) -> None:
        """Validate enumerated fields and raise ValueError on unknown values."""
        _check_member("answer_type", self.answer_type, ANSWER_TYPES)
        _check_member("tag", self.tag, TAGS)
        _check_member("split", self.split, SPLITS)
        _check_member("origin", self.origin, ORIGINS)


def _check_member(name: str, value: str, allowed: frozenset[str]) -> None:
    """Raise ValueError when value is not one of the allowed options."""
    if value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")


def load_eval_jsonl(path: Path) -> list[EvalRecord]:
    """Load evaluation records from a UTF-8 JSONL file, skipping blank lines."""
    records: list[EvalRecord] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload: dict[str, Any] = json.loads(line)
            records.append(EvalRecord(**payload))
    return records


def save_eval_jsonl(records: Sequence[EvalRecord], path: Path) -> None:
    """Write evaluation records to a UTF-8 JSONL file, one record per line."""
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
