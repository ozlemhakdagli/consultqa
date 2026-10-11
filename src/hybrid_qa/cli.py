"""Command-line interface: ask, evaluate, compare and build-dataset."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING

from .config import RAW_PDF_DIR, REBUILT_JSON_PATH

if TYPE_CHECKING:
    from .evaluation import EvalExample, EvalRow
    from .pipeline import HybridQASystem


def _cmd_ask(args: argparse.Namespace) -> int:
    from .pipeline import build_system

    result = build_system().answer(args.question)
    print(f"Soru: {result.question}")
    print(f"Cevap: {result.text}")
    if result.source is not None:
        src = result.source
        print(f"Kaynak: {src.doc_id} | {src.update_id} | versiyon {src.version}")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    from . import evaluation
    from .pipeline import build_system

    system = build_system(mode=args.retriever)
    examples = evaluation.load_eval_set()
    rows = evaluation.evaluate(lambda q: system.answer(q).text, examples)
    for row in rows:
        print(f"EM={row.exact_match} F1={row.f1:.2f} | {row.question}")
    summary = evaluation.summarize(rows)
    print(f"EM: {summary['exact_match'] * 100:.1f}%")
    print(f"F1: {summary['f1'] * 100:.1f}%")
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    """Evaluate dense, sparse and hybrid retrieval with one shared set of models."""
    from . import evaluation
    from .config import EVAL_SET_PATH
    from .data_loader import load_passages
    from .pipeline import HybridQASystem, build_retriever
    from .qa import AnswerExtractor
    from .retrieval import BM25Retriever, DenseRetriever

    passages = load_passages()
    dense = DenseRetriever(passages)
    sparse = BM25Retriever(passages)
    extractor = AnswerExtractor()
    examples = evaluation.load_eval_set(EVAL_SET_PATH)

    print(f"{'Mod':<8} {'EM (%)':>8} {'F1 (%)':>8}")
    for mode in ("dense", "sparse", "hybrid"):
        system = HybridQASystem(build_retriever(mode, dense, sparse), extractor)
        summary = evaluation.summarize(_run_evaluation(system, examples))
        print(f"{mode:<8} {summary['exact_match'] * 100:>8.1f} {summary['f1'] * 100:>8.1f}")
    return 0


def _run_evaluation(system: HybridQASystem, examples: list[EvalExample]) -> list[EvalRow]:
    """Answer every example with ``system``. The lambda binds this call's system only."""
    from . import evaluation

    return evaluation.evaluate(lambda question: system.answer(question).text, examples)


def _cmd_build_dataset(args: argparse.Namespace) -> int:
    from .pdf_extraction import build_dataset

    records = build_dataset(
        pdf_dir=args.pdf_dir or RAW_PDF_DIR,
        output_path=args.output or REBUILT_JSON_PATH,
    )
    print(f"{len(records)} kayıt oluşturuldu.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hybrid_qa", description="Güncelleme raporları için soru-cevap."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ask = sub.add_parser("ask", help="Soru sor ve cevap al")
    ask.add_argument("question", help="Soru metni")
    ask.set_defaults(func=_cmd_ask)

    ev = sub.add_parser("evaluate", help="Değerlendirme kümesi üzerinde EM ve F1 hesapla")
    ev.add_argument("--retriever", choices=["dense", "sparse", "hybrid"], default="hybrid")
    ev.set_defaults(func=_cmd_evaluate)

    cmp_parser = sub.add_parser(
        "compare", help="Dense, sparse ve hybrid modları karşılaştır (makale Tablo 1)"
    )
    cmp_parser.set_defaults(func=_cmd_compare)

    build = sub.add_parser("build-dataset", help="PDF'lerden veri kümesi (JSON) oluştur")
    build.add_argument(
        "--pdf-dir", type=Path, default=None, help=f"PDF klasörü (varsayılan: {RAW_PDF_DIR})"
    )
    build.add_argument(
        "--output", type=Path, default=None, help=f"Çıktı JSON (varsayılan: {REBUILT_JSON_PATH})"
    )
    build.set_defaults(func=_cmd_build_dataset)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)
