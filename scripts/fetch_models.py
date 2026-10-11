"""Download the pinned models into the models volume.

Two places, both under the models volume (``/models`` in the image):

- The sentence encoders, the reranker and the reader go into the Hugging Face cache (HF_HOME).
- The Docling layout and table models, and the RapidOCR models its OCR reads, go into the folder
  named by ``CONSULTQA_DOCLING_ARTIFACTS`` (the image sets ``/models/docling``). Docling reads that
  folder through its ``artifacts_path``, so the app never needs the network for them.

Run once before the real backend starts:
``docker compose --profile setup run --rm fetch-models``. The download is about 7.3 GB plus 0.5 GB.
Every revision here is a full commit hash, so nothing is fetched at a moving revision.
"""

import subprocess
from pathlib import Path

from huggingface_hub import snapshot_download

from consultqa.config import MODEL_PINS, load_settings

FETCH_KEYS = ("bge-m3", "reranker-v2-m3", "xlm-roberta-squad2", "paper-embedder")

# Files that the app never loads: the ONNX export (bge-m3 onnx/model.onnx_data alone is 2.2 GB),
# the model-card images and the stray jpg and webp files. fnmatch matches "*" across "/", so
# "*.jpg" also covers a jpg at the root of a repository. The weights, configs and tokenizers stay.
IGNORE_PATTERNS = ["onnx/*", "imgs/*", "*.jpg", "*.webp"]

# The commits that Docling requests: the layout model asks for "main" (8f39ad3c...) and the
# table models for the tag "v2.3.0" (fc0f2d45...). Pinning the commit keeps the cache valid
# offline and makes the download reproducible.
DOCLING_REPOS = (
    ("docling-project/docling-layout-heron", "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"),
    ("docling-project/docling-models", "fc0f2d45e2218ea24bce5045f58a389aed16dc23"),
)


def rapidocr_command(folder: Path) -> list[str]:
    """The Docling tool that downloads the RapidOCR torch models Docling's default OCR reads."""
    return [
        "docling-tools", "models", "download", "rapidocr",
        "--rapidocr-backend-lang", "torch:ch", "-o", str(folder),
    ]  # fmt: skip


def main() -> None:
    """Cache each pinned model, then write the Docling models to their own folder."""
    for key in FETCH_KEYS:
        repo_id, revision = MODEL_PINS[key]
        print(f"fetching {key}: {repo_id} @ {revision}", flush=True)
        snapshot_download(repo_id=repo_id, revision=revision, ignore_patterns=IGNORE_PATTERNS)

    folder = load_settings().docling_artifacts
    if folder is None:
        raise SystemExit("set CONSULTQA_DOCLING_ARTIFACTS to the folder for the Docling models")
    for repo_id, revision in DOCLING_REPOS:
        target = folder / repo_id.replace("/", "--")
        print(f"fetching docling {repo_id} @ {revision} into {target}", flush=True)
        snapshot_download(repo_id=repo_id, revision=revision, local_dir=target)
    print(f"downloading the RapidOCR models into {folder / 'RapidOcr'}", flush=True)
    # The command is fixed by rapidocr_command; the folder is set by the operator.
    subprocess.run(rapidocr_command(folder), check=True)  # noqa: S603
    print("all pinned models are cached", flush=True)


if __name__ == "__main__":
    main()
