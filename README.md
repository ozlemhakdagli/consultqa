# Hybrid QA

[![License: MIT](https://img.shields.io/github/license/ozlemhakdagli/Hybrid-Release-Notes-QA)](LICENSE)
![Python 3.11](https://img.shields.io/badge/Python-3.11-3776ab?logo=python&logoColor=white)
![FAISS](https://img.shields.io/badge/FAISS-dense%20retrieval-0467df)
![BM25](https://img.shields.io/badge/BM25-sparse%20retrieval-555555)
![Ruff](https://img.shields.io/badge/lint-ruff-d7ff64?logo=ruff&logoColor=black)

Code for the hybrid question-answering method of the paper below: a FAISS dense index and a BM25 keyword
index find the passage, and an XLM-RoBERTa Large reader extracts the answer from it. This branch holds
only the paper's method, a small package around it, and a public synthetic sample.

> Hakdağlı, Ö. (2024). *Hybrid Question-Answering System: A FAISS and BM25 Approach for Extracting
> Information from Technical Document.* Orclever Proceedings of Research and Development, 5(1), 226-237.
> The paper works on 23 technical documents.

## Status

The numbers reported in the paper are **not reproduced here**. The paper's corpus, questions and gold
answers are not published, so this repository cannot recompute them and no result is claimed in this
README. What it offers is the code that does the work: the pipeline in `src/hybrid_qa/` and a standalone
copy of the method in `reference/paper_method/`. Run either on your own corpus and evaluation file to get
exact match and token F1.

Experiments that came after the paper (other encoders, other fusion rules, measurement protocols) are
not part of this repository.

## What is included

- **Dense retrieval:** a flat L2 FAISS index over `multi-qa-mpnet-base-dot-v1` sentence embeddings.
- **Sparse retrieval:** Okapi BM25 over the same passages.
- **Hybrid mode:** the dense hits first, then the BM25 hits, duplicates removed, cut to the top 5. The
  reader receives the first passage.
- **Extractive reader:** `deepset/xlm-roberta-large-squad2`. Model revisions are pinned in
  `src/hybrid_qa/config.py`.
- **Evaluation:** exact match and set-based token F1, with a `compare` command that runs dense, sparse
  and hybrid retrieval side by side.
- **PDF extraction:** a parser that turns monthly update-report PDFs into the structured JSON the
  retrievers read (PyMuPDF, optional extra `pdf`).
- **Reference copy:** `reference/paper_method/pipeline.py`, a single script with no import from `src/`.
- **Sample data:** `data/sample/corpus.jsonl` (480 passages) and `data/sample/eval_test.jsonl` (400
  questions), synthetic Turkish text with no third-party content.
- **Not included:** the paper's corpus and questions, any trained or fine-tuned weights, a web service.

## Quick start

You need Git and [Miniconda](https://docs.conda.io/). The conda environment installs the package with
all extras (`ml`, `pdf`, `dev`).

```bash
git clone https://github.com/ozlemhakdagli/Hybrid-Release-Notes-QA.git
cd Hybrid-Release-Notes-QA

conda env create -f environment.yml
conda activate hybrid-qa
```

The first run that loads a model downloads the embedding model and the reader from Hugging Face. The
`Makefile` sets `HF_HUB_OFFLINE=1`, so run `make` targets only after the models are in the local cache,
or run the commands below without it.

The command line works on a processed update-report JSON file. Its location is `PROCESSED_JSON_PATH` in
`src/hybrid_qa/config.py`; the evaluation file is `EVAL_SET_PATH` in the same module. The paper's files
are not published, so supply your own in the same format (a list of documents with `version_info` and
`updates`; evaluation items with `question` and `answer`).

```bash
python -m hybrid_qa ask "your question"                 # answer one question, show the source passage
python -m hybrid_qa evaluate --retriever hybrid         # EM and F1 (dense, sparse or hybrid)
python -m hybrid_qa compare                             # dense, sparse and hybrid in one table
python -m hybrid_qa build-dataset --pdf-dir DIR --output OUT.json   # PDFs to the processed JSON
```

The standalone reference script takes its inputs on the command line:

```bash
python reference/paper_method/pipeline.py --corpus CORPUS.json --eval EVAL.json --mode hybrid --out RESULT.json
```

To try the pipeline on the synthetic sample, load the passages yourself:

```python
from pathlib import Path

from hybrid_qa.corpus import load_jsonl_passages
from hybrid_qa.pipeline import build_system

system = build_system(load_jsonl_passages(Path("data/sample/corpus.jsonl")), mode="hybrid")
print(system.answer("V2.10.0 sürümünde hangi modül içinde performans iyileştirmeleri yapıldı?").text)
```

## Tests

```bash
make test        # pytest -q, no model weights needed
make lint        # ruff check and ruff format --check
make format      # ruff format
```

Tests marked `model` (none at the moment) would need the real model weights and are excluded by default
(`pytest.ini`). The test files are:

- `test_corpus.py`, `test_data_loader.py`: passage schema and loaders
- `test_text.py`: Turkish-aware normalisation and tokenisation
- `test_retrieval.py`: dense, BM25 and hybrid retrieval
- `test_qa.py`, `test_pipeline.py`: the reader and the end-to-end system
- `test_evaluation.py`: exact match and token F1
- `test_pdf_extraction.py`: the update-report parser
- `test_paper_method.py`: the standalone reference script
- `test_repo_privacy.py`: no private path or PDF is tracked, and `.dockerignore` stays an allowlist

## Make it yours

1. Your corpus: a JSON file in the format above (or JSONL passages with `doc_id`, `update_id`, `version`,
   `description`), and point `PROCESSED_JSON_PATH` in `src/hybrid_qa/config.py` at it, or pass passages to
   `build_system`.
2. Your questions: an evaluation JSON list of `{"question", "answer"}` items, set as `EVAL_SET_PATH`.
3. The encoder or the reader: `EMBEDDING_MODEL` and `QA_MODEL` (with their pinned revisions) in
   `config.py`.
4. How many passages are kept: `DENSE_TOP_K`, `SPARSE_TOP_K` and `FINAL_TOP_K` in `config.py`.
5. A different merge rule: `src/hybrid_qa/retrieval/fusion.py`; `pipeline.build_retriever` selects the
   mode.
6. Your own PDFs: `python -m hybrid_qa build-dataset`; the layout it expects is described in
   `src/hybrid_qa/pdf_extraction.py`.

## License

MIT, see [LICENSE](LICENSE).

## More

<details>
<summary><b>Project layout</b></summary>

```
src/hybrid_qa/
  __main__.py        python -m hybrid_qa
  cli.py             ask, evaluate, compare, build-dataset
  config.py          paths, pinned model revisions, top-k values
  corpus.py          Passage schema, JSON and JSONL loaders and writer
  data_loader.py     thin shim over corpus.py
  text.py            Turkish-aware normalisation and tokenisation
  pdf_extraction.py  update-report PDFs to structured JSON
  qa.py              XLM-RoBERTa extractive reader
  pipeline.py        HybridQASystem, retriever modes, build_system
  evaluation.py      exact match, token F1, evaluation loop
  retrieval/
    base.py          Hit, Encoder and Retriever types
    encoders.py      sentence-encoder registry with lazy loading
    dense.py         FAISS flat L2 index
    bm25.py          Okapi BM25
    fusion.py        hybrid merge (dense first, then sparse)
reference/paper_method/
  pipeline.py        standalone copy of the paper method
  README.md          how to run it
data/sample/         corpus.jsonl and eval_test.jsonl (synthetic, public)
tests/               pytest suite, one file per module
Makefile             test, lint, format
```

</details>

<details>
<summary><b>Design notes</b></summary>

### Hybrid mode is a concatenation

`HybridRetriever` takes the dense hits, appends the BM25 hits, removes duplicates by passage text and
keeps the first 5. When the dense channel already returns 5 distinct passages, the BM25 hits fall past
the cut and the hybrid list equals the dense list. This is how the method is written, and the code
keeps it that way on purpose. Read dense, sparse and hybrid rows of `compare` with this in mind.

### One passage per update

Each update description is one passage, stored with its document, update id and version. The text used for
indexing and for the reader is the description followed by `(Versiyon: <version>)`, so a question that
names a version can match on it.

### The reader sees one passage

`HybridQASystem.answer` passes only the best-ranked passage to the reader. When retrieval misses, the
reader cannot recover, so reader accuracy is bounded by how often the right passage is first. If no
passage is found, or the reader returns nothing, the answer is a fixed "no context" sentence in Turkish.

### Pinned models, lazy loading

Both models are pinned to a revision in `config.py` and in the reference script. The
sentence-transformers and transformers packages are imported only when a model is loaded, so the unit
tests and the lint run without model weights.

### Metrics

Exact match compares the stripped, lowercased strings. F1 is computed on the sets of lowercase
whitespace tokens, so repeated tokens count once.

### Private data stays out

The paper's source documents are not published. `private/` and `data/raw/` are git-ignored, PDFs are
never tracked, and `tests/test_repo_privacy.py` checks the list of tracked files for private paths and
PDFs.

</details>
