# Ladder T1 with LLM rows: blocked

Recorded on 2026-10-11. **Status: blocked.** No `L4+llm` or `L5+llm` number exists, on the dev split or the test split. `experiments/results/ladder-T1-llm.jsonl` was not created, because nothing was measured.

## Failed gates (plan Task 29)

1. **Endpoint not reachable.** Ollama is not installed. It is not on PATH, and `/usr/local/bin/ollama` does not exist. Installing it needs root, which is not available here (`docs/verification.md`, item 7). `DOCRAG_LLM_BASE_URL` is unset, so the check `curl -fsS $DOCRAG_LLM_BASE_URL/v1/models` was not run.
2. **No owner-chosen endpoint.** The owner has not picked Ollama or a hosted endpoint, and has not supplied a key.
3. **No calibration labels.** The owner has not labelled the about 100 answers needed for judge calibration.

## Rows

| Row | Dev split | Test split |
|---|---|---|
| L4+llm | not run | not run |
| L5+llm | not run | not run |

The non-LLM rows from Task 20 are in `ladder-T1-dev.md` and `ladder-T1-test.md`. This record does not change them and does not repeat their numbers. The test split has not been used for any LLM row.

## Needed to unblock

- The owner installs Ollama, or names a hosted OpenAI-compatible endpoint, and sets `DOCRAG_LLM_BASE_URL`. A hosted key goes in the environment only.
- The owner labels about 100 answers for judge calibration.
- Then: the dev run of `L4+llm` and `L5+llm` for each candidate; the kappa check against the owner's labels (at least 0.6); owner approval of the default; and a single test-split run with the chosen model. Details are in `bakeoff-llm.md`.
