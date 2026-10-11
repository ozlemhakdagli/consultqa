"""Embedder and reranker bake-off on the dev split (plan Task 28).

Stage 1 ranks each embedder candidate by dense-only retrieval (cosine, top 20). Stage 2 builds the
hybrid pool (dense and BM25, RRF-fused, top 30) of the embedder that the stage-1 rule chose, and
scores that pool with each reranker candidate. Both stages reuse ``evaluate_preset`` from the
ablation ladder, so the metric code is the same.

Only the corpus and ``eval_dev`` are read, after their SHA-256 values are checked against
``experiments/protocol.json``. ``eval_test`` is never opened here. Each candidate's revision is the
``model_info(model_id).sha`` value and must equal its ``MODEL_PINS`` entry. Answers are not scored.

Usage, from the repository root::

    python -m docrag.eval.bakeoff_models
"""

import gc
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

from docrag.config import MODEL_PINS, PipelineConfig
from docrag.eval.datasets import file_sha256, load_corpus_jsonl
from docrag.eval.protocol import load_protocol, verify_protocol
from docrag.eval.records import EvalRecord, load_eval_jsonl
from docrag.eval.run_header import build_run_header
from docrag.eval.runner import evaluate_preset
from docrag.eval.stats import Interval, cluster_bootstrap
from docrag.models import Chunk
from docrag.retrieve.dense import ENCODER_SPECS, DenseChannel, NumpyDenseBackend, SentenceEncoder
from docrag.retrieve.pipeline import RetrievalResult, Retriever
from docrag.retrieve.rerank import Scorer, load_causal_reranker, load_cross_encoder
from docrag.retrieve.sparse import SparseChannel

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_PATH = REPO_ROOT / "experiments" / "protocol.json"
EMBEDDER_RESULT = REPO_ROOT / "experiments" / "results" / "bakeoff-embedder.md"
RERANKER_RESULT = REPO_ROOT / "experiments" / "results" / "bakeoff-reranker.md"
DEV_FILES = ("corpus", "eval_dev")  # the test split is deliberately absent

DENSE_K = 20  # stage 1: dense-only candidates, and the depth of their ranking
DEFAULT_EMBEDDER = "bge-m3"  # the current PipelineConfig.encoder; the stage-1 paired reference
NO_RERANKER = "no reranker"  # the stage-2 reference: the same hybrid pool, unscored
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 0

EMBEDDERS = ("bge-m3", "e5-small", "e5-large-instruct", "qwen3-embedding-0.6b")
RERANKERS = ("reranker-v2-m3", "qwen3-reranker-0.6b")
SKIPPED_EMBEDDERS = {
    "google/embeddinggemma-300m": (
        "not run: gated (`gated` is manual; the weight files return HTTP 401 without an "
        "accepted licence)"
    ),
}


def choose(table: Mapping[str, Mapping[str, float]]) -> str:
    """Return the candidate with the highest ``mrr10``; ties go to the smaller ``size_mb``.

    MRR values that differ only by float noise (below 1e-12) count as ties. A tie on size is
    broken by name, so the choice is deterministic.
    """
    if not table:
        raise ValueError("choose needs at least one candidate")
    return min(
        table,
        key=lambda name: (-round(table[name]["mrr10"], 12), table[name]["size_mb"], name),
    )


def pinned_revision(model_key: str, resolved_sha: str) -> str:
    """Return the pinned revision of ``model_key``, or raise if ``resolved_sha`` differs."""
    model_id, pinned = MODEL_PINS[model_key]
    if resolved_sha != pinned:
        raise ValueError(f"{model_id}: model_info sha {resolved_sha} differs from the pin {pinned}")
    return pinned


@dataclass(frozen=True)
class ModelFacts:
    """A candidate's pinned revision and the sizes that the result files report."""

    key: str
    model_id: str
    revision: str
    weight_mb: float | None  # safetensors weights, or pytorch_model.bin, at the revision
    cached_mb: float | None  # Hugging Face cache size of the revision; None when not cached


def _cached_mb(model_id: str, revision: str) -> float | None:
    """Return the cache size of one model revision on disk, or None when it is not cached."""
    # Deferred: huggingface_hub reads HF_HUB_OFFLINE once, when it is first imported.
    from huggingface_hub import scan_cache_dir

    for repo in scan_cache_dir().repos:
        if repo.repo_type == "model" and repo.repo_id == model_id:
            for cached in repo.revisions:
                if cached.commit_hash == revision:
                    return cached.size_on_disk / 1e6
    return None


def resolve_model(key: str) -> ModelFacts:
    """Resolve a candidate's revision from the Hub and check it against ``MODEL_PINS``."""
    from huggingface_hub import model_info

    model_id, _ = MODEL_PINS[key]
    info = model_info(model_id, files_metadata=True)
    revision = pinned_revision(key, info.sha)
    sizes = {sibling.rfilename: sibling.size or 0 for sibling in info.siblings}
    weights = [size for name, size in sizes.items() if name.endswith(".safetensors")]
    if not weights and "pytorch_model.bin" in sizes:
        weights = [sizes["pytorch_model.bin"]]
    weight_mb = sum(weights) / 1e6 if weights else None
    return ModelFacts(key, model_id, revision, weight_mb, _cached_mb(model_id, revision))


def load_dev_split() -> tuple[list[Chunk], list[EvalRecord], dict[str, str]]:
    """Check the corpus and ``eval_dev`` against the protocol and load them with their hashes."""
    files = load_protocol(PROTOCOL_PATH)["files"]
    entries = {name: files[name] for name in DEV_FILES}
    paths = {name: REPO_ROOT / entry["path"] for name, entry in entries.items()}
    problems = verify_protocol({"files": entries}, paths)
    if problems:
        raise ValueError("; ".join(problems))
    chunks = load_corpus_jsonl(paths["corpus"])
    records = load_eval_jsonl(paths["eval_dev"])
    shas = {name: file_sha256(path) for name, path in paths.items()}
    return chunks, records, shas


def _no_answer(question: str, result: RetrievalResult) -> str:
    """Answers are not scored in this bake-off, so no reader runs."""
    return ""


def _interval(questions: Sequence[Mapping[str, Any]], metric: str) -> Interval:
    """Return the mean of one per-question metric with its cluster-bootstrap interval."""
    return cluster_bootstrap(
        [q[metric] for q in questions],
        [q["cluster_id"] for q in questions],
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )


def _paired(
    questions: Sequence[Mapping[str, Any]], reference: Sequence[Mapping[str, Any]], metric: str
) -> Interval:
    """Return the paired per-question difference from the reference, with its interval."""
    if [q["qid"] for q in questions] != [q["qid"] for q in reference]:
        raise ValueError("candidate and reference rows are not aligned by question")
    diffs = [a[metric] - b[metric] for a, b in zip(questions, reference, strict=True)]
    return cluster_bootstrap(
        diffs,
        [q["cluster_id"] for q in questions],
        n_resamples=BOOTSTRAP_RESAMPLES,
        seed=BOOTSTRAP_SEED,
    )


def _row(
    name: str, facts: ModelFacts | None, cfg: PipelineConfig, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return one candidate's summary, keeping its per-question rows for paired differences."""
    return {
        "name": name,
        "facts": facts,
        "cfg": cfg,
        "n": len(questions),
        "clusters": len({q["cluster_id"] for q in questions}),
        "mrr10": _interval(questions, "mrr10"),
        "recall20": _interval(questions, "recall20"),
        "paired": None,
        "questions": questions,
    }


def _attach_paired(rows: list[dict[str, Any]], reference_name: str) -> None:
    """Fill the paired MRR@10 interval of every row against the reference row."""
    reference = next(row for row in rows if row["name"] == reference_name)
    for row in rows:
        if row is not reference:
            row["paired"] = _paired(row["questions"], reference["questions"], "mrr10")


def _free_gpu() -> None:
    """Drop unreferenced models and release their GPU memory before the next candidate."""
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _dense_channel(chunks: Sequence[Chunk], key: str) -> DenseChannel:
    """Encode the passages once with the named encoder and index them exactly."""
    encoder = SentenceEncoder(ENCODER_SPECS[key])
    backend = NumpyDenseBackend()
    backend.upsert([c.chunk_id for c in chunks], encoder.encode_passages([c.text for c in chunks]))
    return DenseChannel({c.chunk_id: c for c in chunks}, encoder, backend)


def _dense_stage(chunks: Sequence[Chunk], records: Sequence[EvalRecord]) -> list[dict[str, Any]]:
    """Measure each embedder by dense-only retrieval, top ``DENSE_K``."""
    rows: list[dict[str, Any]] = []
    for key in EMBEDDERS:
        facts = resolve_model(key)
        cfg = PipelineConfig(
            name=f"dense-{key}", encoder=key, use_sparse=False, seed_k=DENSE_K, pool_k=DENSE_K
        )
        retriever = Retriever(cfg, chunks, dense=_dense_channel(chunks, key))
        questions = evaluate_preset(cfg, retriever, records, answer_fn=_no_answer, chunks=chunks)
        rows.append(_row(key, facts, cfg, questions))
        _free_gpu()
    return rows


def _load_scorer(key: str) -> Scorer:
    """Return the scorer of one reranker candidate: a cross-encoder or a causal-LM scorer."""
    if key == "reranker-v2-m3":
        return load_cross_encoder(key)
    return load_causal_reranker(key)


def _rerank_one(
    key: str,
    base: PipelineConfig,
    chunks: Sequence[Chunk],
    records: Sequence[EvalRecord],
    dense: DenseChannel,
    sparse: SparseChannel,
) -> dict[str, Any]:
    """Score the hybrid pool with one reranker and return its summary row."""
    cfg = replace(base, name=key, use_reranker=True)
    retriever = Retriever(cfg, chunks, dense=dense, sparse=sparse, scorer=_load_scorer(key))
    questions = evaluate_preset(cfg, retriever, records, answer_fn=_no_answer, chunks=chunks)
    return _row(key, resolve_model(key), cfg, questions)


def _rerank_stage(
    chunks: Sequence[Chunk], records: Sequence[EvalRecord], embedder: str
) -> list[dict[str, Any]]:
    """Measure each reranker on the hybrid pool of ``embedder``, against the unscored pool."""
    dense = _dense_channel(chunks, embedder)
    sparse = SparseChannel(chunks)
    # The pool settings match the ablation presets: seed_k 50 per channel, pool_k 30 kept.
    base = PipelineConfig(name=embedder, encoder=embedder)
    plain = replace(base, name=NO_RERANKER)
    plain_retriever = Retriever(plain, chunks, dense=dense, sparse=sparse)
    plain_questions = evaluate_preset(
        plain, plain_retriever, records, answer_fn=_no_answer, chunks=chunks
    )
    rows = [_row(NO_RERANKER, None, plain, plain_questions)]
    for key in RERANKERS:
        rows.append(_rerank_one(key, base, chunks, records, dense, sparse))
        _free_gpu()
    return rows


def _choice_table(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float]]:
    """Return the decision-rule table: MRR@10 and weight size of each measured candidate."""
    table: dict[str, dict[str, float]] = {}
    for row in rows:
        facts: ModelFacts = row["facts"]
        if facts.weight_mb is None:
            raise ValueError(f"{facts.model_id}: no weight file found at {facts.revision}")
        table[row["name"]] = {"mrr10": row["mrr10"].mean, "size_mb": facts.weight_mb}
    return table


def _mb(value: float | None) -> str:
    """Format a size in megabytes, or a dash when it is unknown."""
    return "-" if value is None else f"{value:.0f}"


def _ci(interval: Interval) -> str:
    """Format a mean with its 95% interval."""
    return f"{interval.mean:.4f} [{interval.low:.4f}, {interval.high:.4f}]"


def _paired_ci(interval: Interval) -> str:
    """Format a paired difference with its 95% interval, signed."""
    return f"{interval.mean:+.4f} [{interval.low:+.4f}, {interval.high:+.4f}]"


def _verdict(interval: Interval) -> str:
    """Say whether a paired interval lies above zero, below zero, or includes zero."""
    if interval.low > 0:
        return "lies entirely above zero"
    if interval.high < 0:
        return "lies entirely below zero"
    return "includes zero, so it is not separated from the reference at this sample size"


def _candidate_table(rows: Sequence[Mapping[str, Any]], reference: str) -> list[str]:
    """Return the Markdown table of measured candidates, one row each."""
    paired_header = f"Paired MRR@10 vs {reference} [95% CI]"
    lines = [
        "| Candidate | Model | Revision | Weights MB | Cache MB | dev MRR@10 [95% CI] "
        f"| dev recall@20 [95% CI] | {paired_header} | n / clusters |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        facts: ModelFacts | None = row["facts"]
        model = facts.model_id if facts else "-"
        revision = facts.revision if facts else "-"
        weights = _mb(facts.weight_mb) if facts else "-"
        cached = _mb(facts.cached_mb) if facts else "-"
        paired = "reference" if row["paired"] is None else _paired_ci(row["paired"])
        lines.append(
            f"| {row['name']} | {model} | {revision} | {weights} | {cached} "
            f"| {_ci(row['mrr10'])} | {_ci(row['recall20'])} | {paired} "
            f"| {row['n']} / {row['clusters']} |"
        )
    return lines


def _skipped_lines(skipped: Mapping[str, str]) -> list[str]:
    """Return table rows for candidates that were not run, with the reason in the score column."""
    return [
        f"| {model} | {model} | - | - | - | {reason} | - | - | - |"
        for model, reason in skipped.items()
    ]


def _split_note(records: Sequence[EvalRecord], n_passages: int, shas: Mapping[str, str]) -> str:
    """Return the paragraph that states which split and corpus every number comes from."""
    clusters = len({record.cluster_id for record in records})
    return (
        f"**Split:** T1 dev only. `data/sample/eval_dev.jsonl` ({len(records)} questions, "
        f"{clusters} clusters, sha256 `{shas['eval_dev']}`) over the public sample corpus "
        f"`data/sample/corpus.jsonl` ({n_passages} passages, sha256 `{shas['corpus']}`). "
        "The corpus is synthetic. The T2 real-text dev split was not built: its data source is "
        "still the "
        "owner's choice (XQuAD-tr is CC BY-SA 4.0 and TQuAD has no licence). The test split was "
        "not opened."
    )


def _measure_note() -> str:
    """Return the paragraph that states how the intervals are computed."""
    return (
        "**Measure:** every interval is a 95% cluster bootstrap (2000 resamples, seed 0) over "
        "questions grouped by cluster. MRR@10 is the primary metric; recall@20 is secondary."
    )


def render_embedders(
    rows: Sequence[Mapping[str, Any]],
    *,
    winner: str,
    header: Mapping[str, Any],
    records: Sequence[EvalRecord],
    n_passages: int,
    shas: Mapping[str, str],
    today: str,
) -> str:
    """Return the embedder result file: the split, the header, the table and the decision."""
    winner_row = next(row for row in rows if row["name"] == winner)
    if winner == DEFAULT_EMBEDDER:
        paired_text = f"It is the reference, {DEFAULT_EMBEDDER}."
    else:
        paired_text = (
            f"Its paired difference from {DEFAULT_EMBEDDER} is {_paired_ci(winner_row['paired'])}, "
            f"which {_verdict(winner_row['paired'])}."
        )
    lines = [
        "# Embedder bake-off on the dev split",
        "",
        f"Run on {today}. Stage 1 of plan Task 28: dense-only retrieval, top {DENSE_K}, exact "
        "cosine search.",
        "",
        _split_note(records, n_passages, shas),
        "",
        _measure_note(),
        "",
        "## Run header",
        "",
        "```json",
        json.dumps(header, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Candidates",
        "",
        *_candidate_table(rows, DEFAULT_EMBEDDER),
        *_skipped_lines(SKIPPED_EMBEDDERS),
        "",
        "## Decision",
        "",
        "Rule (plan Task 28): highest dev MRR@10; ties go to the smaller model.",
        "",
        f"Rule result: **{winner}** (dev MRR@10 {winner_row['mrr10'].mean:.4f}). {paired_text}",
        "",
        "This is a recommendation for the owner. `PipelineConfig.encoder` stays "
        f"`{DEFAULT_EMBEDDER}` until the owner approves these tables. Stage 2 uses **{winner}** "
        "as its embedder.",
        "",
    ]
    return "\n".join(lines)


def render_rerankers(
    rows: Sequence[Mapping[str, Any]],
    *,
    embedder: str,
    winner: str,
    header: Mapping[str, Any],
    records: Sequence[EvalRecord],
    n_passages: int,
    shas: Mapping[str, str],
    today: str,
) -> str:
    """Return the reranker result file: the split, the header, the table and the decision."""
    winner_row = next(row for row in rows if row["name"] == winner)
    plain_row = next(row for row in rows if row["name"] == NO_RERANKER)
    lines = [
        "# Reranker bake-off on the dev split",
        "",
        f"Run on {today}. Stage 2 of plan Task 28. Embedder: **{embedder}** (the stage-1 rule "
        "result). Pool: hybrid, dense top 50 and BM25 top 50, RRF-fused, top 30 kept and scored. "
        "Metrics are on the reranked top 30.",
        "",
        _split_note(records, n_passages, shas),
        "",
        _measure_note(),
        "",
        "## Run header",
        "",
        "```json",
        json.dumps(header, ensure_ascii=False, indent=2),
        "```",
        "",
        "## Candidates",
        "",
        *_candidate_table(rows, NO_RERANKER),
        "",
        "## Decision",
        "",
        f"Rule (plan Task 28): highest dev MRR@10 after reranking; ties go to the smaller model. "
        f"`{NO_RERANKER}` is a reference row, not a candidate.",
        "",
        f"Rule result: **{winner}** (dev MRR@10 {winner_row['mrr10'].mean:.4f}, against "
        f"{plain_row['mrr10'].mean:.4f} with no reranker). Its paired difference from the "
        f"unscored pool is {_paired_ci(winner_row['paired'])}, which "
        f"{_verdict(winner_row['paired'])}.",
        "",
        "This is a recommendation for the owner. `load_cross_encoder` keeps "
        "`reranker-v2-m3` as its default and no preset changes until the owner approves these "
        "tables.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Run both stages on the dev split and write the two result files."""
    chunks, records, shas = load_dev_split()
    today = date.today().isoformat()

    dense_rows = _dense_stage(chunks, records)
    _attach_paired(dense_rows, DEFAULT_EMBEDDER)
    embedder = choose(_choice_table(dense_rows))
    header = build_run_header(
        corpus_sha=shas["corpus"],
        eval_sha=shas["eval_dev"],
        configs={row["name"]: row["cfg"] for row in dense_rows},
    )
    EMBEDDER_RESULT.write_text(
        render_embedders(
            dense_rows,
            winner=embedder,
            header=header,
            records=records,
            n_passages=len(chunks),
            shas=shas,
            today=today,
        ),
        encoding="utf-8",
    )

    rerank_rows = _rerank_stage(chunks, records, embedder)
    _attach_paired(rerank_rows, NO_RERANKER)
    reranker = choose(_choice_table([row for row in rerank_rows if row["name"] != NO_RERANKER]))
    header = build_run_header(
        corpus_sha=shas["corpus"],
        eval_sha=shas["eval_dev"],
        configs={row["name"]: row["cfg"] for row in rerank_rows},
    )
    RERANKER_RESULT.write_text(
        render_rerankers(
            rerank_rows,
            embedder=embedder,
            winner=reranker,
            header=header,
            records=records,
            n_passages=len(chunks),
            shas=shas,
            today=today,
        ),
        encoding="utf-8",
    )
    print(f"embedder rule result: {embedder}; reranker rule result: {reranker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
