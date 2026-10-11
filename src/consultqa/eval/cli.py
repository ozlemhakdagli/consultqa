"""Command line for the consultqa evaluation: ``run`` the ablation ladder and ``verify-protocol``.

Examples::

    python -m consultqa.eval.cli run --corpus data/sample/corpus.jsonl \\
        --eval data/sample/eval_dev.jsonl --presets paper,L2,L3,L4,L5 --baseline L0 \\
        --out ladder.md --rows-out ladder.jsonl
    python -m consultqa.eval.cli verify-protocol --protocol experiments/protocol.json \\
        --file corpus=data/sample/corpus.jsonl

``paper`` runs the published method and yields two tables, L0 (legacy metric) and L1 (corrected
metric). The other presets are the entries of ``consultqa.config.PRESETS``. LLM presets read the
endpoint from the ``CONSULTQA_LLM_*`` variables.
"""

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from consultqa.baseline.paper_adapter import PaperMethod, load_reference_module
from consultqa.config import PRESETS, PipelineConfig, Settings, load_settings
from consultqa.eval.datasets import file_sha256, load_corpus_jsonl
from consultqa.eval.protocol import load_protocol, verify_protocol
from consultqa.eval.records import load_eval_jsonl
from consultqa.eval.report import render_ladder
from consultqa.eval.run_header import build_run_header
from consultqa.eval.runner import AnswerFn, evaluate_paper, evaluate_preset, make_answer_fn
from consultqa.generate.extractive import ExtractiveReader
from consultqa.generate.llm_client import LLMClient
from consultqa.graph.build import EvidenceGraph, build_graph
from consultqa.models import Chunk
from consultqa.retrieve.dense import ENCODER_SPECS, DenseChannel, NumpyDenseBackend, SentenceEncoder
from consultqa.retrieve.pipeline import Retriever
from consultqa.retrieve.rerank import Scorer, load_cross_encoder
from consultqa.retrieve.sparse import SparseChannel

PAPER_PRESET = "paper"
PAPER_TABLES = ("L0", "L1")
DEFAULT_PRESETS = "paper,L2,L3,L4,L5"


class _Components:
    """Builds the encoders, indexes, graph, reranker and readers once, shared by all presets."""

    def __init__(self, chunks: Sequence[Chunk], settings: Settings) -> None:
        self._chunks = list(chunks)
        self._chunks_by_id = {chunk.chunk_id: chunk for chunk in self._chunks}
        self._settings = settings
        self._dense: dict[str, tuple[SentenceEncoder, NumpyDenseBackend]] = {}
        self._sparse: SparseChannel | None = None
        self._graph: EvidenceGraph | None = None
        self._scorer: Scorer | None = None
        self._reader: ExtractiveReader | None = None

    def retriever(self, cfg: PipelineConfig) -> Retriever:
        """Return the retriever for one preset, reusing every component it shares."""
        if cfg.use_sparse and self._sparse is None:
            self._sparse = SparseChannel(self._chunks)
        if cfg.use_graph and self._graph is None:
            self._graph = build_graph(self._chunks)
        if cfg.use_reranker and self._scorer is None:
            self._scorer = load_cross_encoder()
        return Retriever(
            cfg,
            self._chunks,
            dense=self._dense_channel(cfg.encoder),
            sparse=self._sparse if cfg.use_sparse else None,
            graph=self._graph if cfg.use_graph else None,
            scorer=self._scorer if cfg.use_reranker else None,
        )

    def _dense_channel(self, key: str) -> DenseChannel:
        """Return a dense channel over the passages, encoding them once per encoder."""
        if key not in self._dense:
            encoder = SentenceEncoder(ENCODER_SPECS[key])
            backend = NumpyDenseBackend()
            vectors = encoder.encode_passages([chunk.text for chunk in self._chunks])
            backend.upsert([chunk.chunk_id for chunk in self._chunks], vectors)
            self._dense[key] = (encoder, backend)
        encoder, backend = self._dense[key]
        return DenseChannel(self._chunks_by_id, encoder, backend)

    def reader(self) -> ExtractiveReader:
        """Return the extractive reader, loaded on first use."""
        if self._reader is None:
            self._reader = ExtractiveReader()
        return self._reader

    def llm(self) -> LLMClient:
        """Return the LLM client configured through the environment."""
        base_url, model = self._settings.llm_base_url, self._settings.llm_model
        if base_url is None or model is None:
            raise ValueError("LLM presets need CONSULTQA_LLM_BASE_URL and CONSULTQA_LLM_MODEL")
        return LLMClient(base_url, model, api_key=self._settings.llm_api_key)


def _chunks_by_doc(chunks: Sequence[Chunk]) -> dict[str, list[Chunk]]:
    """Group chunks by document, each group in reading order."""
    grouped: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        grouped[chunk.doc_id].append(chunk)
    return {doc_id: sorted(items, key=lambda c: c.position) for doc_id, items in grouped.items()}


def _split_presets(text: str) -> list[str]:
    """Split the ``--presets`` value on commas, dropping blanks."""
    return [item.strip() for item in text.split(",") if item.strip()]


def _tables_for(name: str) -> tuple[str, ...]:
    """Return the table names that a requested preset produces."""
    return PAPER_TABLES if name == PAPER_PRESET else (name,)


def _run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the requested systems over the evaluation file and write the report."""
    names = _split_presets(args.presets)
    if not names:
        parser.error("--presets names no system")
    unknown = [name for name in names if name != PAPER_PRESET and name not in PRESETS]
    if unknown:
        parser.error(f"unknown preset(s): {', '.join(unknown)}")
    produced = {table for name in names for table in _tables_for(name)}
    if args.baseline not in produced:
        parser.error(f"baseline {args.baseline!r} is not among the tables this run produces")
    settings = load_settings()
    needs_llm = any(PRESETS[name].reader == "llm" for name in names if name in PRESETS)
    if needs_llm and (settings.llm_base_url is None or settings.llm_model is None):
        parser.error("LLM presets need CONSULTQA_LLM_BASE_URL and CONSULTQA_LLM_MODEL")

    chunks = load_corpus_jsonl(args.corpus)
    records = load_eval_jsonl(args.eval)
    components = _Components(chunks, settings)
    chunks_by_doc = _chunks_by_doc(chunks)

    tables: dict[str, list[dict]] = {}
    configs: dict[str, object] = {}
    for name in names:
        if name == PAPER_PRESET:
            rows = evaluate_paper(
                records, PaperMethod(chunks), reference=load_reference_module(), chunks=chunks
            )
            tables["L0"] = [{**row, "em": row["em_legacy"], "f1": row["f1_legacy"]} for row in rows]
            tables["L1"] = rows
            configs[PAPER_PRESET] = {"method": "reference/paper_method", "tables": PAPER_TABLES}
            continue
        cfg = PRESETS[name]
        answer_fn: AnswerFn = make_answer_fn(
            cfg,
            reader=components.reader() if cfg.reader == "extractive" else None,
            llm=components.llm() if cfg.reader == "llm" else None,
            chunks_by_doc=chunks_by_doc,
        )
        tables[name] = evaluate_preset(
            cfg, components.retriever(cfg), records, answer_fn=answer_fn, chunks=chunks
        )
        configs[name] = cfg

    header = build_run_header(
        corpus_sha=file_sha256(args.corpus), eval_sha=file_sha256(args.eval), configs=configs
    )
    markdown = (
        "# consultqa evaluation run\n\n```json\n"
        + json.dumps(header, ensure_ascii=False, indent=2)
        + "\n```\n\n"
        + render_ladder(tables, baseline=args.baseline)
    )
    if args.out is None:
        sys.stdout.write(markdown)
    else:
        args.out.write_text(markdown, encoding="utf-8")
    if args.rows_out is not None:
        _write_rows(args.rows_out, tables)
    return 0


def _write_rows(path: Path, tables: dict[str, list[dict]]) -> None:
    """Write one JSON object per question and system, with the system name in ``system``."""
    with path.open("w", encoding="utf-8") as handle:
        for system, rows in tables.items():
            for row in rows:
                handle.write(json.dumps({"system": system, **row}, ensure_ascii=False) + "\n")


def _verify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Check every protocol file against its declared hash; print mismatches to stderr."""
    file_paths: dict[str, Path] = {}
    for item in args.file or []:
        name, separator, path = item.partition("=")
        if not separator or not name or not path:
            parser.error(f"--file expects NAME=PATH, got {item!r}")
        file_paths[name] = Path(path)
    problems = verify_protocol(load_protocol(args.protocol), file_paths)
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1 if problems else 0


def _build_parser() -> argparse.ArgumentParser:
    """Return the parser with the ``run`` and ``verify-protocol`` subcommands."""
    parser = argparse.ArgumentParser(
        prog="python -m consultqa.eval.cli", description="consultqa evaluation."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the ablation ladder over an evaluation file")
    run.add_argument(
        "--corpus", type=Path, required=True, help="corpus JSONL, one passage per line"
    )
    run.add_argument("--eval", type=Path, required=True, help="evaluation JSONL")
    run.add_argument(
        "--presets",
        default=DEFAULT_PRESETS,
        help=f"comma list of '{PAPER_PRESET}' and preset names ({', '.join(PRESETS)}); "
        f"default {DEFAULT_PRESETS}",
    )
    run.add_argument(
        "--baseline", default="L0", help="table that the paired differences are taken against"
    )
    run.add_argument("--out", type=Path, help="Markdown report path (default: stdout)")
    run.add_argument("--rows-out", type=Path, help="JSONL with one row per question and system")

    verify = commands.add_parser("verify-protocol", help="check file hashes against a protocol")
    verify.add_argument("--protocol", type=Path, required=True, help="protocol JSON file")
    verify.add_argument(
        "--file",
        action="append",
        metavar="NAME=PATH",
        help="a file named in the protocol; repeat for each file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line and return the exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run(args, parser)
    return _verify(args, parser)


if __name__ == "__main__":
    raise SystemExit(main())
