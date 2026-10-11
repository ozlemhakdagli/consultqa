"""Project-wide paths and model settings.

Values mirror the reference implementation in notebooks/son2_reference.ipynb
and the academic paper in docs/paper.pdf.
"""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Synthetic, publishable corpus and eval files
DATA_DIR = Path(os.environ.get("HYBRID_QA_DATA_DIR", PROJECT_ROOT / "data" / "sample"))
SAMPLE_CORPUS_PATH = DATA_DIR / "corpus.jsonl"
SAMPLE_EVAL_TEST_PATH = DATA_DIR / "eval_test.jsonl"

# Private company data (never published or copied into images)
PRIVATE_DIR = PROJECT_ROOT / "private"
RAW_PDF_DIR = PRIVATE_DIR / "raw"
PROCESSED_JSON_PATH = PRIVATE_DIR / "processed" / "all_pdf_data2.json"
REBUILT_JSON_PATH = PRIVATE_DIR / "processed" / "rebuilt_dataset.json"
EVAL_SET_PATH = PRIVATE_DIR / "eval" / "test_set.json"

# Dense retrieval (FAISS over sentence embeddings)
EMBEDDING_MODEL = "sentence-transformers/multi-qa-mpnet-base-dot-v1"
EMBEDDING_MODEL_REVISION = "17997f24dca0df1a4fed68894fb0e1e133e60482"

# Extractive question answering
QA_MODEL = "deepset/xlm-roberta-large-squad2"
QA_MODEL_REVISION = "dafe59921a75cdffc06ed3ad6e45c581b22b85cc"

# Number of passages taken from each retriever, and the number kept after merging
DENSE_TOP_K = 5
SPARSE_TOP_K = 5
FINAL_TOP_K = 5

NO_CONTEXT_ANSWER = "Maalesef, bu soruya uygun bir bağlam bulunamadı."

PRIVATE_RESULTS_DIR = PRIVATE_DIR / "results"
