"""Configuration, model pins and ablation presets for consultqa.

Settings are read from ``CONSULTQA_*`` environment variables by ``load_settings``.
Model revisions are full commit hashes so that every run is reproducible.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

RRF_K = 60
BM25_PREFIX_LEN = 5
ABSTAIN_WORD = "bulunamadı"
NO_CONTEXT_ANSWER = "Maalesef, bu soruya uygun bir bağlam bulunamadı."

MODEL_PINS: dict[str, tuple[str, str]] = {
    "bge-m3": ("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181"),
    "e5-small": ("intfloat/multilingual-e5-small", "614241f622f53c4eeff9890bdc4f31cfecc418b3"),
    "reranker-v2-m3": ("BAAI/bge-reranker-v2-m3", "953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e"),
    "xlm-roberta-squad2": (
        "deepset/xlm-roberta-large-squad2",
        "dafe59921a75cdffc06ed3ad6e45c581b22b85cc",
    ),
    "paper-embedder": (
        "sentence-transformers/multi-qa-mpnet-base-dot-v1",
        "17997f24dca0df1a4fed68894fb0e1e133e60482",
    ),
    # Bake-off candidates (Task 28). Revisions from huggingface_hub.model_info(id).sha.
    "e5-large-instruct": (
        "intfloat/multilingual-e5-large-instruct",
        "274baa43b0e13e37fafa6428dbc7938e62e5c439",
    ),
    "qwen3-embedding-0.6b": (
        "Qwen/Qwen3-Embedding-0.6B",
        "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
    ),
    "qwen3-reranker-0.6b": (
        "Qwen/Qwen3-Reranker-0.6B",
        "e61197ed45024b0ed8a2d74b80b4d909f1255473",
    ),
}


@dataclass(frozen=True)
class PipelineConfig:
    """One rung of the ablation ladder."""

    name: str
    encoder: str = "bge-m3"
    use_sparse: bool = True
    use_graph: bool = False
    use_reranker: bool = False
    use_context: bool = False
    neighbours: int = 0
    reader: str = "extractive"
    seed_k: int = 50
    pool_k: int = 30
    final_k: int = 5
    rrf_k: int = RRF_K
    graph_restart: float = 0.7
    graph_k: int = 20


_L2 = PipelineConfig(name="L2")
_L3 = replace(_L2, name="L3", use_reranker=True)
_L4 = replace(_L3, name="L4", use_context=True, neighbours=1)
# D2: L5 keeps the neighbour passages of L4, so L5 against L4 isolates the graph.
# Graph parameters chosen on the dev split only (experiments/results/tune-dev.md).
_L5 = replace(_L4, name="L5", use_graph=True, graph_restart=0.5, seed_k=50, graph_k=20)

PRESETS: dict[str, PipelineConfig] = {
    "L2": _L2,
    "L3": _L3,
    "L4": _L4,
    "L5": _L5,
    "L4+llm": replace(_L4, name="L4+llm", reader="llm"),
    "L5+llm": replace(_L5, name="L5+llm", reader="llm"),
}


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the service and the evaluation tools."""

    backend: str = "real"
    state_dir: Path = field(default_factory=lambda: Path.home() / ".consultqa")
    qdrant_url: str | None = None
    llm_base_url: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    enable_paper_baseline: bool = False
    parser: str = "docling"
    # The folder with the Docling layout and table models (scripts/fetch_models.py). None means
    # Docling reads them from the Hugging Face cache.
    docling_artifacts: Path | None = None
    max_upload_mb: float = 20
    max_pages: int = 200
    chunk_max_tokens: int = 200
    frontend_dir: Path | None = None


def _value(source: Mapping[str, str], name: str) -> str | None:
    """Return the variable's value, treating an unset or empty variable as absent."""
    return source.get(name) or None


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build ``Settings`` from ``CONSULTQA_*`` variables; defaults apply to unset ones."""
    source: Mapping[str, str] = os.environ if env is None else env
    base = Settings()
    state_dir = _value(source, "CONSULTQA_STATE_DIR")
    frontend_dir = _value(source, "CONSULTQA_FRONTEND_DIR")
    docling_artifacts = _value(source, "CONSULTQA_DOCLING_ARTIFACTS")
    return Settings(
        backend=_value(source, "CONSULTQA_BACKEND") or base.backend,
        state_dir=Path(state_dir) if state_dir else base.state_dir,
        qdrant_url=_value(source, "CONSULTQA_QDRANT_URL"),
        llm_base_url=_value(source, "CONSULTQA_LLM_BASE_URL"),
        llm_model=_value(source, "CONSULTQA_LLM_MODEL"),
        llm_api_key=_value(source, "CONSULTQA_LLM_API_KEY"),
        enable_paper_baseline=_value(source, "CONSULTQA_ENABLE_PAPER_BASELINE") == "1",
        parser=_value(source, "CONSULTQA_PARSER") or base.parser,
        docling_artifacts=Path(docling_artifacts) if docling_artifacts else None,
        max_upload_mb=float(_value(source, "CONSULTQA_MAX_UPLOAD_MB") or base.max_upload_mb),
        max_pages=int(_value(source, "CONSULTQA_MAX_PAGES") or base.max_pages),
        chunk_max_tokens=int(_value(source, "CONSULTQA_CHUNK_MAX_TOKENS") or base.chunk_max_tokens),
        frontend_dir=Path(frontend_dir) if frontend_dir else None,
    )
