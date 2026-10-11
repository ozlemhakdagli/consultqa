# Paper method (reference reproduction)

`pipeline.py` reproduces the paper's retrieval and reading pipeline on a JSON corpus.
Dense retrieval uses FAISS (IndexFlatL2) over `multi-qa-mpnet-base-dot-v1` embeddings, sparse retrieval uses BM25 on whitespace-split text, and hybrid mode merges both lists.
The first unique passage is read by `deepset/xlm-roberta-large-squad2`.
Model revisions are pinned as constants at the top of the script.
The script reports exact match and set-based token F1 for the chosen mode (`dense`, `sparse` or `hybrid`).
Usage: `python pipeline.py --corpus CORPUS.json --eval EVAL.json --mode hybrid [--out RESULT.json]`.
The corpus is a list of documents with `version_info` and `updates`; the eval file is a list of `{"question", "answer"}`.
No data is included in this directory: the corpus, the evaluation questions and the answers are not published.
This copy does not import the project's `src/` package and has no private paths.
