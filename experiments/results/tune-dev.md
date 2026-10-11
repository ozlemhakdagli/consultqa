# Graph parameter tuning on the dev split (L5)

Dev split only: the corpus and `eval_dev`. The test split was not opened.

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
      "graph_restart": 0.7,
      "graph_k": 20
    }
  }
}
```

| graph_restart | seed_k | graph_k | n | MRR@10 | EM | chosen |
|---|---|---|---|---|---|---|
| 0.5 | 20 | 10 | 200 | 0.5334 | 0.4200 |  |
| 0.5 | 20 | 20 | 200 | 0.5334 | 0.4200 |  |
| 0.5 | 50 | 10 | 200 | 0.5352 | 0.4200 |  |
| 0.5 | 50 | 20 | 200 | 0.5353 | 0.4200 | yes |
| 0.7 | 20 | 10 | 200 | 0.5334 | 0.4200 |  |
| 0.7 | 20 | 20 | 200 | 0.5334 | 0.4200 |  |
| 0.7 | 50 | 10 | 200 | 0.5353 | 0.4200 |  |
| 0.7 | 50 | 20 | 200 | 0.5352 | 0.4200 |  |
| 0.85 | 20 | 10 | 200 | 0.5334 | 0.4200 |  |
| 0.85 | 20 | 20 | 200 | 0.5334 | 0.4200 |  |
| 0.85 | 50 | 10 | 200 | 0.5353 | 0.4200 |  |
| 0.85 | 50 | 20 | 200 | 0.5353 | 0.4200 |  |

Chosen: graph_restart=0.5, seed_k=50, graph_k=20 (dev MRR@10 0.5353, EM 0.4200).

Selection: highest dev MRR@10; ties go to the smaller graph_k, then to graph_restart 0.7, then to the smaller seed_k and graph_restart.
