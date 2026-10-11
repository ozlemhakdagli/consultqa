"""Paper method: dense, sparse and hybrid retrieval followed by an extractive reader.

Reads a JSON corpus (a list of documents, each with ``version_info`` and ``updates``)
and a JSON evaluation file (a list of ``{"question": ..., "answer": ...}``), answers
every question with the chosen retrieval mode and prints exact match and F1.
No data is bundled; the corpus and evaluation files must be supplied.
"""

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

EMBEDDING_MODEL = "sentence-transformers/multi-qa-mpnet-base-dot-v1"
EMBEDDING_MODEL_REVISION = "17997f24dca0df1a4fed68894fb0e1e133e60482"
QA_MODEL = "deepset/xlm-roberta-large-squad2"
QA_MODEL_REVISION = "dafe59921a75cdffc06ed3ad6e45c581b22b85cc"
TOP_K = 5
NO_CONTEXT_ANSWER = "Maalesef, bu soruya uygun bir bağlam bulunamadı."
MODES = ("dense", "sparse", "hybrid")


def load_passages_from_records(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """One passage per update: its description followed by the document version."""
    passages = []
    for document in records:
        version = document["version_info"]["version"]
        for update in document["updates"]:
            passages.append(f"{update['description']} (Versiyon: {version})")
    return passages


def load_passages(corpus_path: Path) -> list[str]:
    with corpus_path.open(encoding="utf-8") as handle:
        return load_passages_from_records(json.load(handle))


def merge_unique(dense: Sequence[str], sparse: Sequence[str]) -> list[str]:
    """Concatenate the two lists and keep the first occurrence of each text."""
    seen: set[str] = set()
    merged: list[str] = []
    for text in [*dense, *sparse]:
        if text not in seen:
            seen.add(text)
            merged.append(text)
    return merged


def top_k_indices(scores: Sequence[float], k: int) -> list[int]:
    """Indices of the k highest scores, highest first."""
    ranked = np.argsort(scores)[::-1][:k]
    return [int(index) for index in ranked]


def exact_match(prediction: str, gold: str) -> bool:
    return prediction.strip().lower() == gold.strip().lower()


def f1_score(prediction: str, gold: str) -> float:
    """Set-based token F1 over lowercased whitespace tokens."""
    predicted = set(prediction.strip().lower().split())
    expected = set(gold.strip().lower().split())
    common = predicted & expected
    precision = len(common) / len(predicted) if predicted else 0.0
    recall = len(common) / len(expected) if expected else 0.0
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _encodable(texts: Sequence[str]) -> list[str]:
    return [text.replace("\n", " ") for text in texts]


class Retriever:
    """Dense (FAISS L2 over sentence embeddings) and sparse (BM25) retrieval over passages."""

    def __init__(self, passages: Sequence[str]) -> None:
        import faiss
        from rank_bm25 import BM25Okapi
        from sentence_transformers import SentenceTransformer

        self.passages = list(passages)
        self.encoder = SentenceTransformer(EMBEDDING_MODEL, revision=EMBEDDING_MODEL_REVISION)
        vectors = np.asarray(self.encoder.encode(_encodable(self.passages)), dtype=np.float32)
        self.index = faiss.IndexFlatL2(vectors.shape[1])
        self.index.add(vectors)
        self.bm25 = BM25Okapi([text.split(" ") for text in self.passages])

    def dense(self, query: str, k: int = TOP_K) -> list[str]:
        vector = np.asarray(self.encoder.encode(_encodable([query])), dtype=np.float32)
        _, ids = self.index.search(vector, k)
        return [self.passages[int(i)] for i in ids[0] if i != -1]

    def sparse(self, query: str, k: int = TOP_K) -> list[str]:
        scores = self.bm25.get_scores(query.split(" "))
        return [self.passages[index] for index in top_k_indices(scores, k)]


def build_reader() -> Any:
    from transformers import pipeline

    return pipeline(
        "question-answering",
        model=QA_MODEL,
        tokenizer=QA_MODEL,
        revision=QA_MODEL_REVISION,
    )


def candidate_passages(retriever: Retriever, query: str, mode: str) -> list[str]:
    dense = retriever.dense(query) if mode in ("dense", "hybrid") else []
    sparse = retriever.sparse(query) if mode in ("sparse", "hybrid") else []
    return merge_unique(dense, sparse)


def answer(retriever: Retriever, reader: Any, query: str, mode: str) -> str:
    """The reader sees only the first unique passage."""
    passages = candidate_passages(retriever, query, mode)
    if not passages:
        return NO_CONTEXT_ANSWER
    return str(reader(question=query, context=passages[0])["answer"])


def evaluate(
    retriever: Retriever,
    reader: Any,
    items: Sequence[Mapping[str, str]],
    mode: str,
) -> list[dict[str, Any]]:
    rows = []
    for item in items:
        prediction = answer(retriever, reader, item["question"], mode)
        rows.append(
            {
                "question": item["question"],
                "gold": item["answer"],
                "prediction": prediction,
                "exact_match": exact_match(prediction, item["answer"]),
                "f1": f1_score(prediction, item["answer"]),
            }
        )
    return rows


def summarize(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Exact match and F1 as percentages."""
    if not rows:
        raise ValueError("no evaluation items")
    em = 100 * sum(1 for row in rows if row["exact_match"]) / len(rows)
    f1 = 100 * sum(row["f1"] for row in rows) / len(rows)
    return {"em": em, "f1": f1}


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True, help="JSON corpus file")
    parser.add_argument("--eval", type=Path, required=True, help="JSON evaluation file")
    parser.add_argument("--mode", choices=MODES, default="hybrid")
    parser.add_argument("--out", type=Path, default=None, help="optional JSON output file")
    args = parser.parse_args(argv)

    items = json.loads(args.eval.read_text(encoding="utf-8"))
    retriever = Retriever(load_passages(args.corpus))
    reader = build_reader()
    rows = evaluate(retriever, reader, items, args.mode)
    scores = summarize(rows)

    if args.out is not None:
        payload = {"mode": args.mode, "n": len(rows), "items": rows, **scores}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(f"mode={args.mode} n={len(rows)} EM {scores['em']:.1f} F1 {scores['f1']:.1f}")


if __name__ == "__main__":
    main()
