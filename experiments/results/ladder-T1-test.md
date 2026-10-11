# docrag evaluation run

```json
{
  "corpus_sha": "f45275ade478f88526fcaaa285ba21f1a8a6d0a81fc85d7bc316ca4fcb1f010f",
  "eval_sha": "cf447d604493ce980cfcc3077e389343e5f68a227b76912797ca0ec038107c02",
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
    "paper": {
      "method": "reference/paper_method",
      "tables": [
        "L0",
        "L1"
      ]
    },
    "L2": {
      "name": "L2",
      "encoder": "bge-m3",
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
    "L3": {
      "name": "L3",
      "encoder": "bge-m3",
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
    "L4": {
      "name": "L4",
      "encoder": "bge-m3",
      "use_sparse": true,
      "use_graph": false,
      "use_reranker": true,
      "use_context": true,
      "neighbours": 1,
      "reader": "extractive",
      "seed_k": 50,
      "pool_k": 30,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.7,
      "graph_k": 20
    },
    "L5": {
      "name": "L5",
      "encoder": "bge-m3",
      "use_sparse": true,
      "use_graph": true,
      "use_reranker": true,
      "use_context": true,
      "neighbours": 1,
      "reader": "extractive",
      "seed_k": 50,
      "pool_k": 30,
      "final_k": 5,
      "rrf_k": 60,
      "graph_restart": 0.5,
      "graph_k": 20
    }
  }
}
```

| system | n | clusters | MRR@10 [95% CI] | EM [95% CI] | F1 [95% CI] | Δ MRR@10 vs L0 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| L0 | n=400 | 178 | 0.284 [0.248, 0.319] | 0.117 [0.083, 0.155] | 0.224 [0.180, 0.272] | — | baseline |
| L1 | n=400 | 178 | 0.284 [0.248, 0.319] | 0.193 [0.151, 0.236] | 0.429 [0.379, 0.480] | +0.000 [+0.000, +0.000] | undecided |
| L2 | n=400 | 178 | 0.551 [0.521, 0.578] | 0.427 [0.387, 0.468] | 0.613 [0.572, 0.652] | +0.268 [+0.227, +0.308] | better |
| L3 | n=400 | 178 | 0.545 [0.512, 0.577] | 0.410 [0.367, 0.455] | 0.595 [0.555, 0.632] | +0.261 [+0.218, +0.304] | better |
| L4 | n=400 | 178 | 0.545 [0.512, 0.577] | 0.400 [0.359, 0.445] | 0.596 [0.556, 0.634] | +0.261 [+0.218, +0.304] | better |
| L5 | n=400 | 178 | 0.544 [0.511, 0.577] | 0.400 [0.359, 0.445] | 0.596 [0.556, 0.634] | +0.261 [+0.217, +0.303] | better |

Primary intervals are paired against L0, per question, clustered by cluster_id. Verdict: worse if any primary interval lies entirely below zero; better if every primary interval lies entirely above zero; otherwise undecided. Slices with n <= 20 are anecdotal.
