"""Download the pinned model revisions into the Hugging Face cache (HF_HOME, the models volume).

Run once before the real backend starts:
``docker compose --profile setup run --rm fetch-models``. The download is about 9 GB.
Every revision comes from ``consultqa.config.MODEL_PINS``, so nothing is fetched at a moving
revision.
"""

from huggingface_hub import snapshot_download

from consultqa.config import MODEL_PINS

FETCH_KEYS = ("bge-m3", "reranker-v2-m3", "xlm-roberta-squad2", "paper-embedder")


def main() -> None:
    """Cache each pinned model at its pinned revision."""
    for key in FETCH_KEYS:
        repo_id, revision = MODEL_PINS[key]
        print(f"fetching {key}: {repo_id} @ {revision}", flush=True)
        snapshot_download(repo_id=repo_id, revision=revision)
    print("all pinned models are cached", flush=True)


if __name__ == "__main__":
    main()
