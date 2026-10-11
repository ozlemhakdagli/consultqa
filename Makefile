PY ?= python
export HF_HUB_OFFLINE=1

.PHONY: test lint format

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

format:
	$(PY) -m ruff format .
