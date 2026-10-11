# LLM bake-off: blocked

Recorded on 2026-10-11. **Status: blocked.** No candidate was run, no model was pulled or downloaded, and no LLM call was made. This task's gates (plan Task 29) are not met.

## Gates

| Gate | Status | Evidence |
|---|---|---|
| 1. Ollama or a hosted OpenAI-compatible endpoint reachable at `DOCRAG_LLM_BASE_URL` (`curl -fsS $DOCRAG_LLM_BASE_URL/v1/models`) | not met | `DOCRAG_LLM_BASE_URL` is unset. `ollama` is not on PATH, and `/usr/local/bin/ollama` does not exist. Installing Ollama needs root (`docs/verification.md`, item 7). `curl` was not run because no endpoint is configured. |
| 2. The owner chose the endpoint; a hosted key comes from the environment, not a file | not met | The owner has not chosen an endpoint. |
| 3. About 100 owner-labelled answers for judge calibration | not met | No calibration labels exist yet. |

## Done in this task

- `src/docrag/eval/judge.py`, `src/docrag/eval/judge_prompt.txt` (Turkish) and `tests/test_judge.py`. The judge wrapper is tested with a fake LLM only.
- The judge prompt SHA-256 is `58f00000fcf8cfba550afcfa0f48aa79c2dcd7a96c99daf24e883af1b72f9d98`. It is pinned as `JUDGE_PROMPT_SHA256` in `judge.py`, and a test checks the file against it.
- Nothing was installed. `src/docrag/config.py` was not changed; the default LLM stays unset.

## Still needed before this task can run

1. The owner installs Ollama, which needs root, or names a hosted OpenAI-compatible endpoint. The owner sets `DOCRAG_LLM_BASE_URL`. A hosted key goes in the environment only (`DOCRAG_LLM_API_KEY`).
2. The owner approves the candidates: Qwen3 at 4B, 8B and 14B, and Gemma 3 at 4B and 12B. Each candidate's tag and digest is recorded at execution time. None is recorded yet.
3. The owner labels about 100 answers for judge calibration. The CSV stays in the git-ignored private folder.
4. Then, in order: the dev run of `L4+llm` and `L5+llm` per candidate; the Cohen's kappa check (at least 0.6); owner approval of the default LLM; and one test-split run with the chosen model.

## Results

None. There are no judge correctness, citation precision, latency or kappa values. The run header does not yet record the judge prompt hash; the dev run must add it.
