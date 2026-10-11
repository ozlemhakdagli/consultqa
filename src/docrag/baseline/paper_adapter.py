"""Adapter that runs the published method (reference/paper_method) on docrag chunks.

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

from docrag.models import Chunk

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


class PaperMethod:
    """The paper's hybrid retrieval and extractive reader, run over docrag chunks."""

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
            reader = self._ref.build_reader()
        self._retriever = retriever
        self._reader = reader

    def ranked_chunk_ids(self, query: str) -> list[str]:
        """Chunk ids in the order the hybrid retriever ranks their passages."""
        passages = self._ref.candidate_passages(self._retriever, query, "hybrid")
        return [self._ids_by_text[text][0] for text in passages]

    def ids_for_text(self, text: str) -> list[str]:
        """Every chunk id whose text equals ``text``."""
        return list(self._ids_by_text.get(text, []))

    def answer(self, query: str) -> str:
        """The reference answer: the reader sees only the first unique hybrid passage."""
        return self._ref.answer(self._retriever, self._reader, query, "hybrid")
