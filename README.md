# docrag

docrag answers questions about uploaded documents and cites the passages behind each answer. It runs as a FastAPI service: a document goes into a collection, is split into heading-aware chunks, and is indexed twice, as dense vectors in Qdrant and as a Turkish BM25 index. Ingestion makes no LLM calls.

A question is answered from the fused dense and BM25 lists (reciprocal rank fusion, constant 60). Three optional stages sit after that and are chosen by preset: a cross-encoder reranker, heading-aware context with neighbouring passages, and an evidence graph that expands the candidates by personalised PageRank over passage links. The graph uses no model. The reader is extractive by default; an OpenAI-compatible LLM reader is optional.

## Status

- On the test split, a regression set rather than a clean holdout (see [Results](#results)), hybrid RRF (L2) improves MRR@10 over the published method (L0): 0.551 against 0.284. The gain is for the whole bundle: the encoder (BGE-M3, where the paper uses an English sentence encoder), Turkish BM25 and RRF fusion. Their contributions are not isolated.
- Adding the reranker (L3), the neighbour context (L4) or the evidence graph (L5) did not produce a measurable gain on this public sample. The graph result covers single-hop questions only, and multi-hop questions were not evaluated. See [What did not work](#what-did-not-work).
- The LLM rungs (L4+llm, L5+llm) are not measured.
- The API default is L2. It was changed after these results were recorded, and the later stages did not beat it on the test split. See [Default preset](#default-preset).
- The default embedder (`bge-m3`) and reranker (`reranker-v2-m3`) are unchanged. The bake-off tables below await owner review.

## Quick start

You need Docker with Compose and about 12 GB of free disk space: the image (about 2.4 GB) and the four models copied into the `models` volume (about 9 GB, a second copy of the host cache). The first start takes minutes: the image build installs CPU PyTorch, and the service loads the models before `/api/ready` answers 200.

The models are the pinned revisions in `docrag.config.MODEL_PINS`. If they are already in your Hugging Face cache (`~/.cache/huggingface/hub`), copy the four pinned models that `fetch-models` also downloads into the `models` volume, then start the stack:

```bash
# Once: build the image, then copy the four cached models into the models volume
MODELS="models--BAAI--bge-m3 models--BAAI--bge-reranker-v2-m3 models--deepset--xlm-roberta-large-squad2 models--sentence-transformers--multi-qa-mpnet-base-dot-v1"
docker compose build app
docker run --rm -v docrag_models:/models -v "$HOME/.cache/huggingface/hub:/src:ro" \
  --entrypoint sh docrag:dev -c "mkdir -p /models/hub && for m in $MODELS; do cp -r /src/\$m /models/hub/; done"

# Start the app on http://127.0.0.1:8000 (Qdrant starts with it); --wait returns when it is healthy
DOCRAG_BACKEND=real docker compose up -d --wait app
```

Without a cache, `docker compose --profile setup run --rm fetch-models` downloads the same revisions into the volume first (about 9 GB). If the copy is missing a model, fetch only that model with the same command.

The web page at `http://127.0.0.1:8000/` is in Turkish. On a wide screen it shows a top bar (title, system status and a theme switch: Otomatik, Açık, Koyu; the choice is saved in the browser) above two columns: the documents and the question on the left, the answer on the right; on a phone the same parts stack in reading order. The answer view shows the answer, the document and section it came from and the whole source text with the sentence that contains the answer marked. The default mode is extractive: the answer is a piece taken from one passage of the document, so it can be short or incomplete (the page says so, and says when the AI answer mode is not configured). The page always starts on the default folder "Belgelerim", which it creates on the first visit; other answer modes and other folders are under "Gelişmiş seçenekler", closed by default, and the chosen folder is not remembered. The mode that needs an LLM stays disabled, with the reason shown, until `DOCRAG_LLM_BASE_URL` and `DOCRAG_LLM_MODEL` are set. The page does not show the retrieval trace; the API still returns it. The same steps through the API, all under `/api`:

```bash
# 1. Create a collection; the response holds its id
curl -s -X POST http://127.0.0.1:8000/api/collections \
  -H 'Content-Type: application/json' -d '{"name": "demo"}'

# 2. Upload a .pdf, .txt or .md file; ingestion runs as a job (503 not_ready until the models load)
curl -s -X POST http://127.0.0.1:8000/api/collections/<collection_id>/documents -F 'file=@manual.pdf'
curl -s http://127.0.0.1:8000/api/jobs/<job_id>    # state becomes done, or failed with an error code

# 3. Ask; the answer carries numbered citations and the retrieval trace
curl -s -X POST http://127.0.0.1:8000/api/collections/<collection_id>/ask \
  -H 'Content-Type: application/json' -d '{"question": "<your question>", "preset": "L2"}'
```

`GET /api/presets` lists the presets. The API default is `L2`, the hybrid RRF preset (see [Default preset](#default-preset)). Pass `preset` to use another rung. Uploads are limited to 20 MB by default (`DOCRAG_MAX_UPLOAD_MB`). `GET /api/capabilities` reports readiness, upload limits and which methods are available (the page uses it; `/api/presets` is unchanged).

To check the service without downloading models, `make smoke` starts the stub backend and checks `/api/ready`.

**Optional LLM reader.** Set `DOCRAG_LLM_BASE_URL` (with or without the trailing `/v1`, for example `http://ollama:11434/v1`) and `DOCRAG_LLM_MODEL` in `.env`. For a hosted endpoint, also set `DOCRAG_LLM_API_KEY`; `compose.yml` passes it to the container. Until an endpoint is configured, the LLM presets return 503 `llm_unavailable`. No LLM is included in the stack, and the LLM presets are not measured.

## Results

All numbers are on the public synthetic sample in `data/sample/`. Each interval is a 95% cluster bootstrap (2000 resamples, seed 0). Differences from L0 or from the rung below are paired per question. MRR@10 is the primary metric.

| Rung | Content |
|---|---|
| L0 | Published method (`reference/paper_method/`): dense-first concatenation, extractive reader |
| L1 | L0 with the corrected metric (case, punctuation, multiset F1) |
| L2 | Hybrid RRF (BGE-M3 and Turkish BM25) with the extractive reader |
| L3 | L2 plus the cross-encoder reranker (`reranker-v2-m3`) |
| L4 | L3 plus heading path and one neighbouring passage on each side; no graph |
| L5 | L4 plus evidence-graph expansion (`graph_restart` 0.5, `seed_k` 50, `graph_k` 20). L5 keeps L4's neighbouring passages, so comparing L5 with L4 isolates the graph |
| L4+llm, L5+llm | L4 and L5 with the LLM reader. Not measured |

L0 here is a re-run of the published method on this public sample. Its numbers are not comparable with the paper's own figures.

The extractive reader gets only the top passage, so the heading and neighbour passages of L4 and L5 reach only the LLM reader. For the extractive rungs, L4 changes the heading prefix alone.

### Test split (regression set)

The test split is a regression set, not a clean holdout. It was used in exploration on the earlier branch, which has been deleted, and that exploration shaped the design. It was held out from graph tuning and from the bake-offs only.

Run header (`ladder-T1-test.md`):

- Corpus SHA-256 `f45275ade478f88526fcaaa285ba21f1a8a6d0a81fc85d7bc316ca4fcb1f010f`; evaluation SHA-256 `cf447d604493ce980cfcc3077e389343e5f68a227b76912797ca0ec038107c02`.
- Git HEAD `5aa0bee`, with uncommitted changes: true.
- Python 3.11.17; torch 2.14.1; transformers 4.57.6; sentence-transformers 5.7.0; CUDA available: true. The header records CUDA availability but not the device name; the recorded runs used an NVIDIA GeForce RTX 3080 Ti.

| system | n | clusters | MRR@10 [95% CI] | EM [95% CI] | F1 [95% CI] | Δ MRR@10 vs L0 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| L0 | n=400 | 178 | 0.284 [0.248, 0.319] | 0.117 [0.083, 0.155] | 0.224 [0.180, 0.272] | — | baseline |
| L1 | n=400 | 178 | 0.284 [0.248, 0.319] | 0.193 [0.151, 0.236] | 0.429 [0.379, 0.480] | +0.000 [+0.000, +0.000] | undecided |
| L2 | n=400 | 178 | 0.551 [0.521, 0.578] | 0.427 [0.387, 0.468] | 0.613 [0.572, 0.652] | +0.268 [+0.227, +0.308] | better |
| L3 | n=400 | 178 | 0.545 [0.512, 0.577] | 0.410 [0.367, 0.455] | 0.595 [0.555, 0.632] | +0.261 [+0.218, +0.304] | better |
| L4 | n=400 | 178 | 0.545 [0.512, 0.577] | 0.400 [0.359, 0.445] | 0.596 [0.556, 0.634] | +0.261 [+0.218, +0.304] | better |
| L5 | n=400 | 178 | 0.544 [0.511, 0.577] | 0.400 [0.359, 0.445] | 0.596 [0.556, 0.634] | +0.261 [+0.217, +0.303] | better |

Primary intervals are paired against L0, per question, clustered by cluster_id. Verdict: worse if any primary interval lies entirely below zero; better if every primary interval lies entirely above zero; otherwise undecided. Slices with n <= 20 are anecdotal.

Paired differences, recomputed from `experiments/results/ladder-T1-test.jsonl` with `docrag.eval.stats.cluster_bootstrap`:

| Comparison | MRR@10 | EM¹ |
|---|---|---|
| L2 minus L0 | +0.268 [+0.227, +0.308] | +0.310 [+0.259, +0.361] |
| L3 minus L2 | -0.007 [-0.037, +0.024] | -0.018 [-0.059, +0.026] |
| L4 minus L3 | +0.000 [+0.000, +0.000] | -0.010 [-0.028, +0.007] |
| L5 minus L4 | -0.0004 [-0.001, +0.000] | +0.000 [+0.000, +0.000] |

¹ The EM column of `L2 minus L0` mixes two changes: the metric (L1 is L0 with the corrected metric, on the same predictions) and the system (L2). For the metric change alone, L2 minus L1 is EM +0.235 [+0.185, +0.285].

F1 is a primary metric in the verdict. Its tokenizer splits version strings such as `V2.2.0` into several tokens, so a wrong version gets partial credit: `V2.3.0` for `V2.2.0` shares two of three tokens and scores F1 0.667. Answers that name versions should be read with that in mind.

### Dev split (used for tuning)

Run header (`ladder-T1-dev.md`):

- Corpus SHA-256 `f45275ade478f88526fcaaa285ba21f1a8a6d0a81fc85d7bc316ca4fcb1f010f`; evaluation SHA-256 `9cb1b618b32155480ed7794d1726c54f168670ebf41127c79ccc28fcc96bd545`.
- Git HEAD `5aa0bee`, with uncommitted changes: true.
- Python 3.11.17; torch 2.14.1; transformers 4.57.6; sentence-transformers 5.7.0; CUDA available: true.

| system | n | clusters | MRR@10 [95% CI] | EM [95% CI] | F1 [95% CI] | Δ MRR@10 vs L0 [95% CI] | verdict |
|---|---|---|---|---|---|---|---|
| L0 | n=200 | 82 | 0.257 [0.212, 0.300] | 0.145 [0.100, 0.197] | 0.347 [0.280, 0.419] | — | baseline |
| L1 | n=200 | 82 | 0.257 [0.212, 0.300] | 0.190 [0.141, 0.245] | 0.443 [0.371, 0.510] | +0.000 [+0.000, +0.000] | undecided |
| L2 | n=200 | 82 | 0.507 [0.475, 0.540] | 0.370 [0.314, 0.426] | 0.579 [0.521, 0.636] | +0.251 [+0.203, +0.297] | better |
| L3 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.395 [0.330, 0.461] | 0.588 [0.532, 0.649] | +0.279 [+0.227, +0.330] | better |
| L4 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.420 [0.359, 0.481] | 0.596 [0.538, 0.655] | +0.279 [+0.227, +0.330] | better |
| L5 | n=200 | 82 | 0.535 [0.495, 0.577] | 0.420 [0.359, 0.481] | 0.596 [0.538, 0.655] | +0.279 [+0.227, +0.330] | better |

Primary intervals are paired against L0, per question, clustered by cluster_id. Verdict: worse if any primary interval lies entirely below zero; better if every primary interval lies entirely above zero; otherwise undecided. Slices with n <= 20 are anecdotal.

The dev split was used for tuning. The graph parameters were chosen on dev only (`experiments/results/tune-dev.md`). Across the 12 settings of `graph_restart`, `seed_k` and `graph_k`, L5's dev MRR@10 ranged from 0.5334 to 0.5353.

### Bake-offs (dev split; decisions await owner review)

**Parser** (`bakeoff-parser.md`). Three synthetic text-layer PDFs, so every number is anecdotal (n = 3). Both parsers scored 1.000 on word F1 and heading recall, and the tie went to the faster one. The default parser is unchanged.

| Parser | Files | Failed | Mean word F1 | Mean heading recall | Mean seconds per file |
|---|---|---|---|---|---|
| pymupdf4llm | 3 | 0 | 1.000 | 1.000 | 0.28 |
| docling | 3 | 0 | 1.000 | 1.000 | 3.87 |

The docling mean of 3.87 s per file includes a 6.84 s first-call model load. Its steady state is 2.2 to 2.6 s per file, against 0.14 to 0.15 s per file for pymupdf4llm.

**Embedder** (`bakeoff-embedder.md`). Dense retrieval only, top 20. The rule picks e5-large-instruct, but its paired gain over bge-m3 is +0.0135 [-0.0372, +0.0672], which includes zero. `PipelineConfig.encoder` stays `bge-m3` until the owner approves the table. Gemma was not run because its weights are gated.

| Candidate | Model | Revision | Weights MB | Cache MB | dev MRR@10 [95% CI] | dev recall@20 [95% CI] | Paired MRR@10 vs bge-m3 [95% CI] | n / clusters |
|---|---|---|---|---|---|---|---|---|
| bge-m3 | BAAI/bge-m3 | 5617a9f61b028005a4858fdac845db406aefb181 | 2271 | 2310 | 0.5341 [0.4864, 0.5800] | 0.8100 [0.7552, 0.8579] | reference | 200 / 82 |
| e5-small | intfloat/multilingual-e5-small | 614241f622f53c4eeff9890bdc4f31cfecc418b3 | 471 | 1434 | 0.4863 [0.4466, 0.5262] | 0.7700 [0.7150, 0.8245] | -0.0478 [-0.0844, -0.0089] | 200 / 82 |
| e5-large-instruct | intfloat/multilingual-e5-large-instruct | 274baa43b0e13e37fafa6428dbc7938e62e5c439 | 1120 | 1142 | 0.5476 [0.5018, 0.5941] | 0.8100 [0.7551, 0.8606] | +0.0135 [-0.0372, +0.0672] | 200 / 82 |
| qwen3-embedding-0.6b | Qwen/Qwen3-Embedding-0.6B | 97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3 | 1192 | 1207 | 0.5051 [0.4572, 0.5526] | 0.8150 [0.7619, 0.8641] | -0.0290 [-0.0782, +0.0225] | 200 / 82 |
| google/embeddinggemma-300m | google/embeddinggemma-300m | - | - | - | not run: gated (`gated` is manual; the weight files return HTTP 401 without an accepted licence) | - | - | - |

**Reranker** (`bakeoff-reranker.md`). The embedder was e5-large-instruct for this stage. The rule picks reranker-v2-m3, the current default. Its paired gain over no reranker is +0.0184 [-0.0153, +0.0502], which includes zero.

| Candidate | Model | Revision | Weights MB | Cache MB | dev MRR@10 [95% CI] | dev recall@20 [95% CI] | Paired MRR@10 vs no reranker [95% CI] | n / clusters |
|---|---|---|---|---|---|---|---|---|
| no reranker | - | - | - | - | 0.5157 [0.4887, 0.5424] | 0.7900 [0.7327, 0.8441] | reference | 200 / 82 |
| reranker-v2-m3 | BAAI/bge-reranker-v2-m3 | 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e | 2271 | 2293 | 0.5341 [0.4934, 0.5761] | 0.8100 [0.7553, 0.8602] | +0.0184 [-0.0153, +0.0502] | 200 / 82 |
| qwen3-reranker-0.6b | Qwen/Qwen3-Reranker-0.6B | e61197ed45024b0ed8a2d74b80b4d909f1255473 | 1192 | 1207 | 0.5209 [0.4867, 0.5543] | 0.7900 [0.7358, 0.8418] | +0.0053 [-0.0203, +0.0320] | 200 / 82 |

**LLM** (`bakeoff-llm.md`, `ladder-T1-llm.md`). Blocked. No candidate was run and no LLM call was made. The gates were not met: no reachable endpoint (Ollama is not installed and `DOCRAG_LLM_BASE_URL` is unset), no endpoint chosen by the owner, and no owner calibration labels. L4+llm and L5+llm have no numbers on either split.

### Default preset

The API default was L5 when the tables above were recorded. It was changed to L2 on 2026-10-11, after these results. The change is recorded in `experiments/protocol.json` (`made_after_results`), and no measured number changed. The reason is that the L5 graph did not improve on L4, and L2 is the simplest rung that the later stages did not beat on the test split: L2 scored MRR@10 0.551 against 0.544 for L5. L2 is not the measured best. On dev, L3 to L5 scored about 0.03 MRR@10 above L2; the L3 minus L2 interval includes zero, and that gain did not repeat on test.

## What did not work

- **Reranker (L3).** On the test split, L3 minus L2 is -0.007 MRR@10 [-0.037, +0.024]. On dev the point estimate was +0.028 [-0.010, +0.064], which includes zero and did not repeat on test.
- **Neighbour context (L4).** The extractive reader gets only the top passage, so for it L4 measured the heading prefix alone. MRR@10 is identical for all 400 test questions, and EM moved -0.010 [-0.028, +0.007]. The neighbour effect is unmeasured for the extractive reader. Neighbours reach only the LLM reader (L4+llm), which is not measured.
- **Evidence graph (L5).** Against L4, MRR@10 changes on 4 of 400 test questions, a net difference of -0.0004 [-0.001, +0.000]. EM is unchanged. This result covers single-hop questions only: 388 of the 400 test questions have one gold passage, and the sample has no multi-hop questions, so multi-hop retrieval was not evaluated.
- **Exact match.** From L2 to L5, the EM point estimate fell from 0.427 to 0.400 on the test split, and every stage-by-stage EM interval on the test split includes zero. On dev the same comparison rose: EM went from 0.370 to 0.420, +0.050 [+0.000, +0.104]. The lower bound of that dev interval is zero to three decimals.
- **Default preset.** See [Default preset](#default-preset) above.

## Limitations

- The public sample is synthetic and template-based: 480 passages, 200 dev questions and 400 test questions. It measures this sample, not real user questions. The test split is a regression set, not a clean holdout.
- No real-text split has been built. Its data source is still open: XQuAD-tr is CC BY-SA 4.0, and TQuAD has no licence.
- The parser comparison covers three clean PDFs. Scanned pages, complex layouts and end-to-end Turkish OCR were not tested.
- The LLM reader has no measured results and no approved default.
- The graph result covers single-hop questions only. Multi-hop questions were not evaluated, and the sample has none.
- The recorded runs used one machine, an NVIDIA GeForce RTX 3080 Ti with CUDA. The run headers record CUDA availability, not the device name.

## Privacy

Private material (the git-ignored `private/` folder and `data/raw/`) is never tracked, never copied into the Docker image (`.dockerignore` is an allowlist), and never published. Any figure drawn from private material appears only as an aggregate and is labelled anecdotal when n is 20 or fewer. This README names no company, product, filename or question from private material. `tests/test_repo_privacy.py` checks that no private path or PDF is tracked.

## Reproduce

```bash
make test        # unit tests; no model weights needed
make lint        # ruff check and ruff format --check
make reproduce   # checks the protocol hashes, then reruns both ladders and rewrites experiments/results/
make e2e         # browser tests; needs pip install -e ".[e2e]" and Google Chrome
```

The protocol ordering is evidenced by git only through file timestamps and the protocol hashes in `experiments/protocol.json`. `make reproduce` runs `verify-protocol` first, so a changed sample file stops the run before any number is written.

`make reproduce` needs the pinned weights in the local Hugging Face cache. `scripts/fetch_models.py` fetches them, and the Makefile sets `HF_HUB_OFFLINE=1`. Tests that need real weights are marked `model` and run with `pytest -m model`.

## The published method

`reference/paper_method/` is a standalone copy of the method in Hakdağlı, Ö. (2024), *Hybrid Question-Answering System: A FAISS and BM25 Approach for Extracting Information from Technical Document*, Orclever Proceedings of Research and Development, 5(1), 226-237. It is the L0 rung. Its corpus and questions are not published.

## Layout

- `src/docrag/`: the service (`api/`), ingestion (`ingest/`), storage (`store/`), retrieval (`retrieve/`), the evidence graph (`graph/`), the readers (`generate/`) and evaluation (`eval/`).
- `frontend/`: the web page (plain ES modules, no build step), found through `DOCRAG_FRONTEND_DIR` (the image sets it to `/app/frontend`).
- `reference/paper_method/`: the published method.
- `data/sample/`: the public synthetic corpus and questions. The sample PDFs in `data/sample/pdf/` are generated by `scripts/make_sample_pdfs.py` and are not tracked.
- `experiments/results/`: the tables above, with their run headers.
- `scripts/`: model fetch, sample PDFs and graph tuning.

## Licence

MIT, see [LICENSE](LICENSE).
