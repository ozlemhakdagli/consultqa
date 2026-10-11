"""Tune the graph parameters of PRESETS["L5"] on the dev split only.

Runs L5 over every setting of the ``tuning`` grid in ``experiments/protocol.json`` on the dev
evaluation file, and writes MRR@10 and EM per setting to ``experiments/results/tune-dev.md``.
Only the corpus and the dev file are checked against the protocol; the test split is never
opened by this script.

Selection: the highest dev MRR@10. Ties go to the smaller ``graph_k``, then to
``graph_restart`` 0.7. Any tie left after that goes to the smaller ``seed_k``, then to the
smaller ``graph_restart``.

The chosen values are written into ``PRESETS["L5"]`` by hand, not by this script.

Usage, from the repository root::

    HF_HUB_OFFLINE=1 python scripts/tune_graph.py
"""

import argparse
import itertools
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from statistics import mean
from typing import Any

from consultqa.config import PRESETS, load_settings
from consultqa.eval.cli import _chunks_by_doc, _Components
from consultqa.eval.datasets import file_sha256, load_corpus_jsonl
from consultqa.eval.protocol import load_protocol, verify_protocol
from consultqa.eval.records import load_eval_jsonl
from consultqa.eval.run_header import build_run_header
from consultqa.eval.runner import evaluate_preset, make_answer_fn

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROTOCOL = REPO_ROOT / "experiments" / "protocol.json"
DEFAULT_OUT = REPO_ROOT / "experiments" / "results" / "tune-dev.md"
DEV_FILES = ("corpus", "eval_dev")  # the test split is deliberately absent
BASE_PRESET = "L5"
PREFERRED_RESTART = 0.7


def _rank_key(result: dict[str, Any]) -> tuple[float, int, bool, int, float]:
    """Sort key: highest MRR@10 first, then the tie-break order of the module docstring."""
    return (
        -round(result["mrr10"], 12),
        result["graph_k"],
        result["graph_restart"] != PREFERRED_RESTART,
        result["seed_k"],
        result["graph_restart"],
    )


def _render(results: list[dict[str, Any]], best: dict[str, Any], header: dict[str, Any]) -> str:
    """Return the Markdown report: run header, one row per setting, and the choice."""
    lines = [
        "# Graph parameter tuning on the dev split (L5)",
        "",
        "Dev split only: the corpus and `eval_dev`. The test split was not opened.",
        "",
        "```json",
        json.dumps(header, ensure_ascii=False, indent=2),
        "```",
        "",
        "| graph_restart | seed_k | graph_k | n | MRR@10 | EM | chosen |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result['graph_restart']} | {result['seed_k']} | {result['graph_k']} "
            f"| {result['n']} | {result['mrr10']:.4f} | {result['em']:.4f} "
            f"| {'yes' if result is best else ''} |"
        )
    lines += [
        "",
        f"Chosen: graph_restart={best['graph_restart']}, seed_k={best['seed_k']}, "
        f"graph_k={best['graph_k']} (dev MRR@10 {best['mrr10']:.4f}, EM {best['em']:.4f}).",
        "",
        "Selection: highest dev MRR@10; ties go to the smaller graph_k, then to graph_restart "
        "0.7, then to the smaller seed_k and graph_restart.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Check the dev files, run the grid, write the report and print the choice."""
    parser = argparse.ArgumentParser(description="Tune L5 graph parameters on the dev split.")
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    protocol = load_protocol(args.protocol)
    files = protocol["files"]
    dev_entries = {name: files[name] for name in DEV_FILES}
    problems = verify_protocol(
        {"files": dev_entries},
        {name: REPO_ROOT / entry["path"] for name, entry in dev_entries.items()},
    )
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 1

    corpus_path = REPO_ROOT / files["corpus"]["path"]
    dev_path = REPO_ROOT / files["eval_dev"]["path"]
    chunks = load_corpus_jsonl(corpus_path)
    records = load_eval_jsonl(dev_path)
    # The helper is shared with the eval CLI so that encoders, graph and reranker load once.
    components = _Components(chunks, load_settings())
    chunks_by_doc = _chunks_by_doc(chunks)
    reader = components.reader()

    grid = protocol["tuning"]
    results: list[dict[str, Any]] = []
    for restart, seed_k, graph_k in itertools.product(
        grid["graph_restart"], grid["seed_k"], grid["graph_k"]
    ):
        cfg = replace(PRESETS[BASE_PRESET], graph_restart=restart, seed_k=seed_k, graph_k=graph_k)
        answer_fn = make_answer_fn(cfg, reader=reader, llm=None, chunks_by_doc=chunks_by_doc)
        rows = evaluate_preset(
            cfg, components.retriever(cfg), records, answer_fn=answer_fn, chunks=chunks
        )
        result = {
            "graph_restart": restart,
            "seed_k": seed_k,
            "graph_k": graph_k,
            "n": len(rows),
            "mrr10": mean(row["mrr10"] for row in rows),
            "em": mean(row["em"] for row in rows),
        }
        results.append(result)
        print(
            f"restart={restart} seed_k={seed_k} graph_k={graph_k} "
            f"MRR@10={result['mrr10']:.4f} EM={result['em']:.4f}",
            flush=True,
        )

    best = min(results, key=_rank_key)
    header = build_run_header(
        corpus_sha=file_sha256(corpus_path),
        eval_sha=file_sha256(dev_path),
        configs={BASE_PRESET: PRESETS[BASE_PRESET]},
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_render(results, best, header), encoding="utf-8")
    print(
        f"chosen: graph_restart={best['graph_restart']} seed_k={best['seed_k']} "
        f"graph_k={best['graph_k']} MRR@10={best['mrr10']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
