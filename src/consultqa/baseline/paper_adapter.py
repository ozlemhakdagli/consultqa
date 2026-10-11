"""Adapter that runs the published method (reference/paper_method) on consultqa chunks.

The reference module is loaded by file path, so its code stays unchanged. Its retriever
ranks passage texts; this adapter maps each text back to the chunk ids that carry it, so
every chunk with a gold text counts as gold, including duplicate-text passages.
"""

import importlib.util
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any

from consultqa.models import Chunk

REFERENCE_PATH = Path(__file__).resolve().parents[3] / "reference" / "paper_method" / "pipeline.py"


@lru_cache(maxsize=1)
def load_reference_module() -> ModuleType:
    """Load reference/paper_method/pipeline.py by file path, once per process."""
    spec = importlib.util.spec_from_file_location("paper_method", REFERENCE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load reference module from {REFERENCE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def shared_reader(reference: Any) -> Any:
    """The published method's reader, built once per reference module and shared by every
    PaperMethod on it. Building it loads a 525 MB question-answering model."""
    return reference.build_reader()


class PaperMethod:
    """The paper's hybrid retrieval and extractive reader, run over consultqa chunks."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        retriever: Any = None,
        reader: Any = None,
    ) -> None:
        self._ref = load_reference_module()
        self._ids_by_text: dict[str, list[str]] = {}
        for chunk in chunks:
            self._ids_by_text.setdefault(chunk.text, []).append(chunk.chunk_id)
        if retriever is None and reader is None:
            retriever = self._ref.Retriever([chunk.text for chunk in chunks])
            reader = shared_reader(self._ref)
        self._retriever = retriever
        self._reader = reader
        # The last question and its passages. The ranking and the answer of one question share
        # one search, so the same question is not searched twice.
        self._memo: tuple[str, list[str]] | None = None

    def _passages(self, query: str) -> list[str]:
        """The hybrid candidate passages of ``query``, from the memo when it holds this question."""
        memo = self._memo
        if memo is None or memo[0] != query:
            memo = (query, self._ref.candidate_passages(self._retriever, query, "hybrid"))
            self._memo = memo
        return list(memo[1])

    def ranked_chunk_ids(self, query: str) -> list[str]:
        """Chunk ids in the order the hybrid retriever ranks their passages."""
        return [self._ids_by_text[text][0] for text in self._passages(query)]

    def ids_for_text(self, text: str) -> list[str]:
        """Every chunk id whose text equals ``text``."""
        return list(self._ids_by_text.get(text, []))

    def answer(self, query: str) -> str:
        """The reference answer: the reader sees only the first unique hybrid passage.

        This is the reference module's ``answer`` with the passages taken from the memo, so the
        question is not searched again.
        """
        passages = self._passages(query)
        if not passages:
            return self._ref.NO_CONTEXT_ANSWER
        return str(self._reader(question=query, context=passages[0])["answer"])
