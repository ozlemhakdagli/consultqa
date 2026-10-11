# Embedder bake-off on the dev split

Run on 2026-10-11. Stage 1 of plan Task 28: dense-only retrieval, top 20, exact cosine search.

**Split:** T1 dev only. `data/sample/eval_dev.jsonl` (200 questions, 82 clusters, sha256 `9cb1b618b32155480ed7794d1726c54f168670ebf41127c79ccc28fcc96bd545`) over the public sample corpus `data/sample/corpus.jsonl` (480 passages, sha256 `f45275ade478f88526fcaaa285ba21f1a8a6d0a81fc85d7bc316ca4fcb1f010f`). The corpus is synthetic. The T2 real-text dev split was not built: its data source is still the owner's choice (XQuAD-tr is CC BY-SA 4.0 and TQuAD has no licence). The test split was not opened.

**Measure:** every interval is a 95% cluster bootstrap (2000 resamples, seed 0) over questions grouped by cluster. MRR@10 is the primary metric; recall@20 is secondary.

## Run header

```json
{
  "corpus_sha": "f45275ade478f88526fcaaa285ba21f1a8a6d0a81fc85d7bc316ca4fcb1f010f",
  "eval_sha": "9cb1b618b32155480ed7794d1726c54f168670ebf41127c79ccc28fcc96bd545",
  "git": {
    "head": "5aa0bee9eabfa8465804c5ae50c434840bbf5188",
    "dirty": true
  },
  "python": "3.11.17",
  "libraries": {
    "torch": "2.14.1",
    "transformers": "4.57.6",
    "sentence-transformers": "5.7.0"
  },
  "cuda_available": true,
  "configs": {
    "bge-m3": {
      "name": "dense-bge-m3",
      "encoder": "bge-m3",
      "use_sparse": false,
      "use_graph": false,
      "use_reranker": false,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 20,
      "pool_k": 20,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "e5-small": {
      "name": "dense-e5-small",
      "encoder": "e5-small",
      "use_sparse": false,
      "use_graph": false,
      "use_reranker": false,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 20,
      "pool_k": 20,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "e5-large-instruct": {
      "name": "dense-e5-large-instruct",
      "encoder": "e5-large-instruct",
      "use_sparse": false,
      "use_graph": false,
      "use_reranker": false,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 20,
      "pool_k": 20,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "qwen3-embedding-0.6b": {
      "name": "dense-qwen3-embedding-0.6b",
      "encoder": "qwen3-embedding-0.6b",
      "use_sparse": false,
      "use_graph": false,
      "use_reranker": false,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 20,
      "pool_k": 20,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    }
  }
}
```

## Candidates

| Candidate | Model | Revision | Weights MB | Cache MB | dev MRR@10 [95% CI] | dev recall@20 [95% CI] | Paired MRR@10 vs bge-m3 [95% CI] | n / clusters |
|---|---|---|---|---|---|---|---|---|
| bge-m3 | BAAI/bge-m3 | 5617a9f61b028005a4858fdac845db406aefb181 | 2271 | 2310 | 0.5341 [0.4864, 0.5800] | 0.8100 [0.7552, 0.8579] | reference | 200 / 82 |
| e5-small | intfloat/multilingual-e5-small | 614241f622f53c4eeff9890bdc4f31cfecc418b3 | 471 | 1434 | 0.4863 [0.4466, 0.5262] | 0.7700 [0.7150, 0.8245] | -0.0478 [-0.0844, -0.0089] | 200 / 82 |
| e5-large-instruct | intfloat/multilingual-e5-large-instruct | 274baa43b0e13e37fafa6428dbc7938e62e5c439 | 1120 | 1142 | 0.5476 [0.5018, 0.5941] | 0.8100 [0.7551, 0.8606] | +0.0135 [-0.0372, +0.0672] | 200 / 82 |
| qwen3-embedding-0.6b | Qwen/Qwen3-Embedding-0.6B | 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 | 1192 | 1207 | 0.5051 [0.4572, 0.5526] | 0.8150 [0.7619, 0.8641] | -0.0290 [-0.0782, +0.0225] | 200 / 82 |
| google/embeddinggemma-300m | google/embeddinggemma-300m | - | - | - | not run: gated (`gated` is manual; the weight files return HTTP 401 without an accepted licence) | - | - | - |

## Decision

Rule (plan Task 28): highest dev MRR@10; ties go to the smaller model.

Rule result: **e5-large-instruct** (dev MRR@10 0.5476). Its paired difference from bge-m3 is +0.0135 [-0.0372, +0.0672], which includes zero, so it is not separated from the reference at this sample size.

This is a recommendation for the owner. `PipelineConfig.encoder` stays `bge-m3` until the owner approves these tables. Stage 2 uses **e5-large-instruct** as its embedder.

## Notes

- Revisions: each row's revision is the `model_info(model_id).sha` value. The run raises if it differs from `MODEL_PINS`, so every measured row matches its pin. The new pins are `e5-large-instruct`, `qwen3-embedding-0.6b` and `qwen3-reranker-0.6b`. `google/embeddinggemma-300m` has no pin because it was not run.
- Prompts: both instruct models take the query instruction "Given a web search query, retrieve relevant passages that answer the query", written in each model card's format. Passages take no prefix. `e5-small` keeps its existing `query: ` and `passage: ` prefixes.
- Downloads: the three new models were downloaded once with network access, using the pinned revisions. `e5-large-instruct` is 1142 MB on disk because its ONNX copy was excluded. `Qwen3-Embedding-0.6B` is 1207 MB. The Cache MB column gives each revision's size on disk. Together the three downloads added about 3.56 GB to the Hugging Face cache.
- Environment: NVIDIA RTX 3080 Ti (12 GB), CUDA; encoders run in fp32 through sentence-transformers.
