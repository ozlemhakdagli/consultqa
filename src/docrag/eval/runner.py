"""Run pipeline presets and the published method over evaluation records, and score every answer.

``evaluate_preset`` ranks passages with a ``Retriever`` and answers with an ``answer_fn``.
``evaluate_paper`` runs the published method (L0 and L1) on the same records. Each row holds one
question's ranking metrics and answer metrics; rows are aligned across systems by ``qid``, the
record's position in the evaluation file.
"""

import re
import time
from collections.abc import Callable, Collection, Mapping, Sequence
from typing import Any

from docrag.baseline.paper_adapter import PaperMethod
from docrag.config import NO_CONTEXT_ANSWER, PipelineConfig
from docrag.eval.metrics import (
    exact_match,
    lenient_match,
    recall_at_k,
    reciprocal_rank_at_k,
    set_f1,
    token_f1,
)
from docrag.eval.records import EvalRecord
from docrag.generate.citations import parse_answer
from docrag.generate.extractive import ExtractiveReader
from docrag.generate.llm_client import LLMClient
from docrag.generate.prompt import build_messages
from docrag.models import Chunk
from docrag.retrieve.context import ContextPassage, build_context
from docrag.retrieve.pipeline import RetrievalResult, Retriever
from docrag.text import normalize_answer

AnswerFn = Callable[[str, RetrievalResult], str]

# Set answers are split on commas, semicolons and the Turkish conjunction "ve".
_SET_SEPARATOR = re.compile(r"\s*[,;]\s*|\s+ve\s+", re.IGNORECASE)


def make_answer_fn(
    cfg: PipelineConfig,
    *,
    reader: ExtractiveReader | None,
    llm: LLMClient | None,
    chunks_by_doc: Mapping[str, Sequence[Chunk]],
) -> AnswerFn:
    """Return the function that answers one question from its retrieval result.

    The extractive reader gets the best-ranked passage alone, with its heading path when
    ``cfg.use_context`` is set; neighbour passages are for the LLM reader only.
    The LLM reader gets the numbered context and returns the parsed answer, or
    ``NO_CONTEXT_ANSWER`` when the model abstains.
    """
    if cfg.reader == "llm":
        if llm is None:
            raise ValueError(f"preset {cfg.name} uses the LLM reader but no LLM client was given")

        def answer_with_llm(question: str, result: RetrievalResult) -> str:
            passages = _context(cfg, result, chunks_by_doc)
            parsed = parse_answer(llm.chat(build_messages(question, passages)), len(passages))
            return parsed.text or NO_CONTEXT_ANSWER

        return answer_with_llm

    if reader is None:
        raise ValueError(f"preset {cfg.name} uses the extractive reader but none was given")

    def answer_with_extractive(question: str, result: RetrievalResult) -> str:
        # The reader sees only the best-ranked passage, never a neighbour added for context.
        if not result.hits:
            return NO_CONTEXT_ANSWER
        top = build_context(
            result.hits[:1],
            chunks_by_doc,
            use_header=cfg.use_context,
            neighbours=0,
            max_passages=1,
        )
        return reader.answer(question, top[0].text)

    return answer_with_extractive


def _context(
    cfg: PipelineConfig, result: RetrievalResult, chunks_by_doc: Mapping[str, Sequence[Chunk]]
) -> list[ContextPassage]:
    """Return the prompt passages of one retrieval result under the preset's settings."""
    return build_context(
        result.hits,
        chunks_by_doc,
        use_header=cfg.use_context,
        neighbours=cfg.neighbours,
        max_passages=cfg.final_k,
    )


def evaluate_preset(
    cfg: PipelineConfig,
    retriever: Retriever,
    records: Sequence[EvalRecord],
    *,
    answer_fn: AnswerFn,
    chunks: Sequence[Chunk] = (),
) -> list[dict]:
    """Return one row per record for the preset that ``retriever`` and ``answer_fn`` implement.

    Gold ids are expanded to every chunk id that shares a gold text, using ``chunks`` for the
    text of each id. Without ``chunks`` no expansion happens. ``latency_ms`` covers retrieval
    and answering for that question.
    """
    text_by_id, ids_by_text = _text_index(chunks)

    def ids_for_text(text: str) -> Sequence[str]:
        return ids_by_text.get(text, ())

    rows: list[dict] = []
    for index, record in enumerate(records):
        started = time.perf_counter()
        result = retriever.retrieve(record.question)
        prediction = answer_fn(record.question, result)
        latency_ms = (time.perf_counter() - started) * 1000.0
        gold = _expanded_gold(record.gold_passage_ids, text_by_id, ids_for_text)
        rows.append(_row(index, record, _ranked_ids(result), gold, prediction, latency_ms))
    return rows


def evaluate_paper(
    records: Sequence[EvalRecord],
    paper: PaperMethod,
    *,
    reference: Any,
    chunks: Sequence[Chunk] = (),
) -> list[dict]:
    """Return one row per record for the published method, with L0 and L1 answer metrics.

    Each row carries the corrected ``em`` and ``f1`` (L1), computed from ``docrag.eval.metrics``,
    and ``em_legacy`` and ``f1_legacy`` (L0), computed with the reference module's
    ``exact_match`` and ``f1_score``. Both use the ranking and the reader of the published method,
    so one row serves both systems. The caller builds the L0 table by putting the legacy values
    in the ``em`` and ``f1`` columns.
    """
    text_by_id, _ = _text_index(chunks)
    rows: list[dict] = []
    for index, record in enumerate(records):
        started = time.perf_counter()
        ranked = _unique(paper.ranked_chunk_ids(record.question))
        prediction = paper.answer(record.question)
        latency_ms = (time.perf_counter() - started) * 1000.0
        gold = _expanded_gold(record.gold_passage_ids, text_by_id, paper.ids_for_text)
        row = _row(index, record, ranked, gold, prediction, latency_ms)
        row["em_legacy"] = max(
            float(reference.exact_match(prediction, accepted))
            for accepted in record.accepted_answers
        )
        row["f1_legacy"] = max(
            float(reference.f1_score(prediction, accepted)) for accepted in record.accepted_answers
        )
        rows.append(row)
    return rows


def _text_index(chunks: Sequence[Chunk]) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return the text of each chunk id and the chunk ids that carry each text."""
    text_by_id = {chunk.chunk_id: chunk.text for chunk in chunks}
    ids_by_text: dict[str, list[str]] = {}
    for chunk in chunks:
        ids_by_text.setdefault(chunk.text, []).append(chunk.chunk_id)
    return text_by_id, ids_by_text


def _expanded_gold(
    gold_ids: Sequence[str],
    text_by_id: Mapping[str, str],
    ids_for_text: Callable[[str], Sequence[str]],
) -> set[str]:
    """Return the gold ids plus every id that carries the text of a gold id."""
    expanded = set(gold_ids)
    for gold_id in gold_ids:
        text = text_by_id.get(gold_id)
        if text is not None:
            expanded.update(ids_for_text(text))
    return expanded


def _unique(ids: Sequence[str]) -> list[str]:
    """Return the ids with repeats removed, first occurrence kept."""
    return list(dict.fromkeys(ids))


def _ranked_ids(result: RetrievalResult) -> list[str]:
    """Return the deduplicated chunk ids of the ranked pool, best first."""
    return _unique([hit.chunk.chunk_id for hit in result.hits])


def _set_f1(prediction: str | None, accepted: Sequence[str]) -> float:
    """Return set F1 between the items of the prediction and the normalised accepted answers."""
    predicted = {normalize_answer(item) for item in _SET_SEPARATOR.split(prediction or "")}
    gold = {normalize_answer(answer) for answer in accepted}
    return set_f1(predicted - {""}, gold - {""})


def _row(
    index: int,
    record: EvalRecord,
    ranked: Sequence[str],
    gold: Collection[str],
    prediction: str,
    latency_ms: float,
) -> dict:
    """Return the metric row of one question for a deduplicated ranking and a prediction."""
    accepted = record.accepted_answers
    rank_gold = next((rank for rank, cid in enumerate(ranked, start=1) if cid in gold), None)
    return {
        "qid": str(index),
        "cluster_id": record.cluster_id,
        "answer_type": record.answer_type,
        "rank_gold": rank_gold,
        "mrr10": reciprocal_rank_at_k(ranked, gold, k=10),
        "recall1": recall_at_k(ranked, gold, k=1),
        "recall5": recall_at_k(ranked, gold, k=5),
        "recall20": recall_at_k(ranked, gold, k=20),
        "em": exact_match(prediction, accepted),
        "f1": token_f1(prediction, accepted),
        "set_f1": _set_f1(prediction, accepted) if record.answer_type == "set" else None,
        "lenient": lenient_match(prediction, accepted),
        "latency_ms": latency_ms,
        "prediction": prediction,
        "source_chunk_id": ranked[0] if ranked else None,
    }
