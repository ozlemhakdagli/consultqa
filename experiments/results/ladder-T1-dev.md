# docrag evaluation run

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
| L0 | n=200 | 82 | 0.257 [0.212, 0.300] | 0.145 [0.100, 0.197] | 0.347 [0.280, 0.419] | — | baseline |
| L1 | n=200 | 82 | 0.257 [0.212, 0.300] | 0.190 [0.141, 0.245] | 0.443 [0.371, 0.510] | +0.000 [+0.000, +0.000] | undecided |
| L2 | n=200 | 82 | 0.507 [0.475, 0.540] | 0.370 [0.314, 0.426] | 0.579 [0.521, 0.636] | +0.251 [+0.203, +0.297] | better |
| L3 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.395 [0.330, 0.461] | 0.588 [0.532, 0.649] | +0.279 [+0.227, +0.330] | better |
| L4 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.420 [0.359, 0.481] | 0.596 [0.538, 0.655] | +0.279 [+0.227, +0.330] | better |
| L5 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.420 [0.359, 0.481] | 0.596 [0.538, 0.655] | +0.279 [+0.227, +0.330] | better |

Primary intervals are paired against L0, per question, clustered by cluster_id. Verdict: worse if any primary interval lies entirely below zero; better if every primary interval lies entirely above zero; otherwise undecided. Slices with n <= 20 are anecdotal.
