"""Registry of the sentence encoders used by the dense channel, with lazy model loading.

Each encoder is described by an immutable EncoderSpec: the pinned model revision, the
prefixes its model family expects and whether embeddings are L2-normalised. The
sentence-transformers package is imported only when an encoder is actually loaded.
"""

from __future__ import annotations

from dataclasses import dataclass

from hybrid_qa.config import EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from hybrid_qa.retrieval.base import Encoder


@dataclass(frozen=True)
class EncoderSpec:
    """Everything needed to load one encoder and encode queries and passages correctly."""

    key: str
    model_id: str
    revision: str
    query_prefix: str = ""
    passage_prefix: str = ""
    normalize: bool = False
    max_seq_length: int | None = None


ENCODER_SPECS: dict[str, EncoderSpec] = {
    "mpnet": EncoderSpec(
        key="mpnet",
        model_id=EMBEDDING_MODEL,
        revision=EMBEDDING_MODEL_REVISION,
    ),
}


def get_encoder_spec(key: str) -> EncoderSpec:
    """Return the registered spec for an encoder key, raising ValueError for unknown keys."""
    try:
        return ENCODER_SPECS[key]
    except KeyError:
        known = ", ".join(sorted(ENCODER_SPECS))
        raise ValueError(f"Unknown encoder key {key!r}; expected one of: {known}.") from None


def load_sentence_encoder(spec: EncoderSpec) -> Encoder:
    """Load the pinned sentence-transformer model described by a spec (imports lazily)."""
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(spec.model_id, revision=spec.revision)
    if spec.max_seq_length is not None:
        model.max_seq_length = spec.max_seq_length
    return model
