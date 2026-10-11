# Reranker bake-off on the dev split

Run on 2026-10-11. Stage 2 of plan Task 28. Embedder: **e5-large-instruct** (the stage-1 rule result). Pool: hybrid, dense top 50 and BM25 top 50, RRF-fused, top 30 kept and scored. Metrics are on the reranked top 30.

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
    "no reranker": {
      "name": "no reranker",
      "encoder": "e5-large-instruct",
      "use_sparse": true,
      "use_graph": false,
      "use_reranker": false,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 50,
      "pool_k": 30,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "reranker-v2-m3": {
      "name": "reranker-v2-m3",
      "encoder": "e5-large-instruct",
      "use_sparse": true,
      "use_graph": false,
      "use_reranker": true,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 50,
      "pool_k": 30,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "qwen3-reranker-0.6b": {
      "name": "qwen3-reranker-0.6b",
      "encoder": "e5-large-instruct",
      "use_sparse": true,
      "use_graph": false,
      "use_reranker": true,
      "use_context": false,
      "neighbours": 0,
      "reader": "extractive",
      "seed_k": 50,
      "pool_k": 30,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    }
  }
}
```

## Candidates

| Candidate | Model | Revision | Weights MB | Cache MB | dev MRR@10 [95% CI] | dev recall@20 [95% CI] | Paired MRR@10 vs no reranker [95% CI] | n / clusters |
|---|---|---|---|---|---|---|---|---|
| no reranker | - | - | - | - | 0.5157 [0.4887, 0.5424] | 0.7900 [0.7327, 0.8441] | reference | 200 / 82 |
| reranker-v2-m3 | BAAI/bge-reranker-v2-m3 | 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e | 2271 | 2293 | 0.5341 [0.4934, 0.5761] | 0.8100 [0.7553, 0.8602] | +0.0184 [-0.0153, +0.0502] | 200 / 82 |
| qwen3-reranker-0.6b | Qwen/Qwen3-Reranker-0.6B | e61197ed45024b0ed8a2d74b80b4d909f1255473 | 1192 | 1207 | 0.5209 [0.4867, 0.5543] | 0.7900 [0.7358, 0.8418] | +0.0053 [-0.0203, +0.0320] | 200 / 82 |

## Decision

Rule (plan Task 28): highest dev MRR@10 after reranking; ties go to the smaller model. `no reranker` is a reference row, not a candidate.

Rule result: **reranker-v2-m3** (dev MRR@10 0.5341, against 0.5157 with no reranker). Its paired difference from the unscored pool is +0.0184 [-0.0153, +0.0502], which includes zero, so it is not separated from the reference at this sample size.

This is a recommendation for the owner. `load_cross_encoder` keeps `reranker-v2-m3` as its default and no preset changes until the owner approves these tables.

## Notes

- `reranker-v2-m3` is scored by `load_cross_encoder`, unchanged. `qwen3-reranker-0.6b` is scored by `load_causal_reranker`, a causal-LM yes/no scorer that follows the model card's prompt. Its score is the "yes" logit minus the "no" logit at the last position, which ranks pairs the same way as the card's P(yes). The scorer was not dropped. Its unit tests check the prompt format, the score and the order. Its real-weight tests (`pytest -m model tests/test_bakeoff_models.py`) check that the relevant passage ranks first and that batch size does not change the scores.
- The embedder used here is the stage-1 rule result, so these numbers depend on it.
- Both stages read only the corpus and `eval_dev`. The test split was not opened.
