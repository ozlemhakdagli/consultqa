PY ?= python
export HF_HUB_OFFLINE=1

.PHONY: test e2e lint format privacy up smoke reproduce

reproduce:
	$(PY) -m consultqa.eval.cli verify-protocol --protocol experiments/protocol.json --file corpus=data/sample/corpus.jsonl --file eval_dev=data/sample/eval_dev.jsonl --file eval_test=data/sample/eval_test.jsonl
	$(PY) -m consultqa.eval.cli run --corpus data/sample/corpus.jsonl --eval data/sample/eval_dev.jsonl --presets paper,L2,L3,L4,L5 --baseline L0 --out experiments/results/ladder-T1-dev.md --rows-out experiments/results/ladder-T1-dev.jsonl
	$(PY) -m consultqa.eval.cli run --corpus data/sample/corpus.jsonl --eval data/sample/eval_test.jsonl --presets paper,L2,L3,L4,L5 --baseline L0 --out experiments/results/ladder-T1-test.md --rows-out experiments/results/ladder-T1-test.jsonl

test:
	$(PY) -m pytest -q

e2e:
	$(PY) -m pytest -q -m e2e

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .

privacy:
	$(PY) -m pytest -q tests/test_repo_privacy.py

up:
	docker compose up -d --wait app

smoke:
	CONSULTQA_BACKEND=stub docker compose up -d --wait app
	curl -fsS http://localhost:8000/api/ready
