"""The Docling models that scripts/fetch_models.py caches, pinned and placed where the app looks."""

import importlib.util
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from huggingface_hub.utils import filter_repo_objects

from consultqa.config import MODEL_PINS

ROOT = Path(__file__).resolve().parents[1]

# The files each pinned snapshot holds, named as in the local Hugging Face cache at the pinned
# revision (~/.cache/huggingface/hub). The names were listed from that cache; nothing was fetched.
CACHED_FILES = {
    "bge-m3": [
        ".gitattributes",
        "1_Pooling/config.json",
        "README.md",
        "colbert_linear.pt",
        "config.json",
        "config_sentence_transformers.json",
        "long.jpg",
        "modules.json",
        "pytorch_model.bin",
        "sentence_bert_config.json",
        "sentencepiece.bpe.model",
        "sparse_linear.pt",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "imgs/.DS_Store",
        "imgs/bm25.jpg",
        "imgs/long.jpg",
        "imgs/miracl.jpg",
        "imgs/mkqa.jpg",
        "imgs/nqa.jpg",
        "imgs/others.webp",
        "onnx/Constant_7_attr__value",
        "onnx/config.json",
        "onnx/model.onnx",
        "onnx/model.onnx_data",
        "onnx/sentencepiece.bpe.model",
        "onnx/special_tokens_map.json",
        "onnx/tokenizer.json",
        "onnx/tokenizer_config.json",
    ],
    "reranker-v2-m3": [
        ".gitattributes",
        "README.md",
        "assets/BEIR-bge-en-v1.5.png",
        "assets/BEIR-e5-mistral.png",
        "assets/CMTEB-retrieval-bge-zh-v1.5.png",
        "assets/llama-index.png",
        "assets/miracl-bge-m3.png",
        "config.json",
        "model.safetensors",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
    ],
    "xlm-roberta-squad2": [
        ".gitattributes",
        "README.md",
        "config.json",
        "model.safetensors",
        "sentencepiece.bpe.model",
        "special_tokens_map.json",
        "tokenizer_config.json",
    ],
    "paper-embedder": [
        "1_Pooling/config.json",
        "README.md",
        "config.json",
        "config_sentence_transformers.json",
        "model.safetensors",
        "modules.json",
        "sentence_bert_config.json",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "vocab.txt",
    ],
}

# The weight, config and tokenizer files that each pinned model's loader reads at its revision.
# bge-m3 has no model.safetensors at its pinned revision, so its weights are pytorch_model.bin.
LOADED_FILES = {
    "bge-m3": {
        "pytorch_model.bin",
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    },
    "reranker-v2-m3": {
        "model.safetensors",
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "sentencepiece.bpe.model",
    },
    "xlm-roberta-squad2": {
        "model.safetensors",
        "config.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "sentencepiece.bpe.model",
    },
    "paper-embedder": {
        "model.safetensors",
        "config.json",
        "config_sentence_transformers.json",
        "modules.json",
        "sentence_bert_config.json",
        "1_Pooling/config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "special_tokens_map.json",
    },
}


def _load_fetch_models():
    spec = importlib.util.spec_from_file_location(
        "fetch_models", ROOT / "scripts" / "fetch_models.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_docling_models_are_pinned_to_full_commit_hashes():
    fetch = _load_fetch_models()
    assert fetch.DOCLING_REPOS, "no Docling repositories are listed"
    for repo_id, revision in fetch.DOCLING_REPOS:
        assert re.fullmatch(r"[0-9a-f]{40}", revision), repo_id


def test_docling_folders_use_the_name_docling_looks_for():
    # Docling reads artifacts_path / "<org>--<name>" for each repository it loads.
    fetch = _load_fetch_models()
    folders = {repo_id.replace("/", "--") for repo_id, _ in fetch.DOCLING_REPOS}
    assert folders == {"docling-project--docling-layout-heron", "docling-project--docling-models"}


def test_rapidocr_download_uses_the_torch_backend_into_the_folder(tmp_path):
    # Docling's default OCR with artifacts_path reads the torch checkpoints (.pth) under RapidOcr.
    fetch = _load_fetch_models()
    command = fetch.rapidocr_command(tmp_path)
    assert command[:4] == ["docling-tools", "models", "download", "rapidocr"]
    assert command[command.index("--rapidocr-backend-lang") + 1] == "torch:ch"
    assert command[command.index("-o") + 1] == str(tmp_path)


@pytest.mark.parametrize(
    "path",
    [
        "onnx/model.onnx_data",
        "onnx/config.json",
        "imgs/bm25.jpg",
        "long.jpg",
        "imgs/others.webp",
        "nested/dir/photo.webp",
    ],
)
def test_ignore_patterns_exclude_onnx_images_jpg_and_webp(path):
    fetch = _load_fetch_models()
    assert list(filter_repo_objects([path], ignore_patterns=fetch.IGNORE_PATTERNS)) == []


@pytest.mark.parametrize("key", list(CACHED_FILES))
def test_ignore_patterns_skip_only_onnx_images_jpg_and_webp(key):
    fetch = _load_fetch_models()
    kept = set(filter_repo_objects(CACHED_FILES[key], ignore_patterns=fetch.IGNORE_PATTERNS))
    skipped = set(CACHED_FILES[key]) - kept
    assert kept
    assert all(
        path.startswith(("onnx/", "imgs/")) or path.endswith((".jpg", ".webp")) for path in skipped
    ), skipped
    assert not any(path.startswith(("onnx/", "imgs/")) for path in kept)
    assert not any(path.endswith((".jpg", ".webp")) for path in kept)


def test_bge_m3_onnx_weights_are_not_downloaded():
    fetch = _load_fetch_models()
    kept = set(filter_repo_objects(CACHED_FILES["bge-m3"], ignore_patterns=fetch.IGNORE_PATTERNS))
    assert "onnx/model.onnx_data" not in kept


@pytest.mark.parametrize("key", list(LOADED_FILES))
def test_ignore_patterns_keep_the_weights_config_and_tokenizer_each_model_loads(key):
    fetch = _load_fetch_models()
    kept = set(filter_repo_objects(CACHED_FILES[key], ignore_patterns=fetch.IGNORE_PATTERNS))
    assert LOADED_FILES[key] <= kept


def test_main_downloads_each_pinned_model_with_the_ignore_patterns(monkeypatch, tmp_path):
    # Every download is replaced by a recorder, so nothing reaches the network or the Docling tool.
    fetch = _load_fetch_models()
    calls = []
    monkeypatch.setattr(fetch, "snapshot_download", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr(fetch, "load_settings", lambda: SimpleNamespace(docling_artifacts=tmp_path))
    monkeypatch.setattr(fetch.subprocess, "run", lambda *args, **kwargs: None)
    fetch.main()
    pinned = [call for call in calls if "local_dir" not in call]
    assert [(call["repo_id"], call["revision"]) for call in pinned] == [
        MODEL_PINS[key] for key in fetch.FETCH_KEYS
    ]
    assert all(call["ignore_patterns"] == fetch.IGNORE_PATTERNS for call in pinned)
