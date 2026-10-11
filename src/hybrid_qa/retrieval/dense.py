"""Dense passage retrieval with a flat L2 FAISS index over sentence embeddings.

Queries and passages can be given model-specific prefixes (e5 needs "query: " and
"passage: "), and embeddings can be L2-normalised, so that the L2 order equals the
cosine order. With the defaults the behaviour is identical to the v0.1 retriever.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from hybrid_qa.config import DENSE_TOP_K, EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION
from hybrid_qa.corpus import Passage
from hybrid_qa.retrieval.base import Encoder, Hit
from hybrid_qa.retrieval.encoders import EncoderSpec, load_sentence_encoder


def _passage_text(passage: Passage) -> str:
    """Return the default text that is embedded for a passage."""
    return passage.text


def _with_prefix(text: str, prefix: str) -> str:
    """Add a prefix unless the text already starts with it, so that a prefix is never doubled."""
    if not prefix or text.startswith(prefix):
        return text
    return prefix + text


def _l2_normalise(vectors: np.ndarray) -> np.ndarray:
    """Scale each row to unit length; zero rows stay zero instead of becoming NaN."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms > 0.0, norms, 1.0)


class DenseRetriever:
    """Nearest-neighbour search over sentence embeddings using a flat L2 FAISS index."""

    def __init__(
        self,
        passages: list[Passage],
        model_name: str = EMBEDDING_MODEL,
        encoder: Encoder | None = None,
        revision: str = EMBEDDING_MODEL_REVISION,
        *,
        query_prefix: str = "",
        passage_prefix: str = "",
        normalize: bool = False,
        text_fn: Callable[[Passage], str] = _passage_text,
    ) -> None:
        if not passages:
            raise ValueError("DenseRetriever needs at least one passage.")

        # Imported here so that merely importing this module stays cheap.
        import faiss

        if encoder is None:
            from sentence_transformers import SentenceTransformer

            encoder = SentenceTransformer(model_name, revision=revision)

        self._passages = list(passages)
        self._encoder = encoder
        self._query_prefix = query_prefix
        self._passage_prefix = passage_prefix
        self._normalize = normalize
        texts = [_with_prefix(text_fn(p), passage_prefix) for p in self._passages]
        embeddings = self._embed(texts)
        self._index = faiss.IndexFlatL2(embeddings.shape[1])
        self._index.add(embeddings)

    @classmethod
    def from_spec(
        cls,
        passages: list[Passage],
        spec: EncoderSpec,
        *,
        encoder: Encoder | None = None,
        text_fn: Callable[[Passage], str] | None = None,
    ) -> DenseRetriever:
        """Build a retriever configured by an encoder spec, loading the model if none is given."""
        if encoder is None:
            encoder = load_sentence_encoder(spec)
        return cls(
            passages,
            encoder=encoder,
            query_prefix=spec.query_prefix,
            passage_prefix=spec.passage_prefix,
            normalize=spec.normalize,
            text_fn=text_fn or _passage_text,
        )

    def _embed(self, texts: list[str]) -> np.ndarray:
        """Encode texts as float32 rows, normalised when the retriever is configured so."""
        vectors = np.asarray(self._encoder.encode(texts), dtype=np.float32)
        if self._normalize:
            vectors = _l2_normalise(vectors).astype(np.float32, copy=False)
        return vectors

    def search(self, query: str, k: int = DENSE_TOP_K) -> list[Hit]:
        """Return up to k passages closest to the query, best first."""
        query_vec = self._embed([_with_prefix(query, self._query_prefix)])
        distances, indices = self._index.search(query_vec, min(k, len(self._passages)))

        hits: list[Hit] = []
        for dist, idx in zip(distances[0], indices[0], strict=True):
            if idx < 0:  # FAISS pads with -1 when fewer neighbours exist
                continue
            hits.append(
                Hit(
                    passage=self._passages[idx],
                    score=-float(np.sqrt(max(dist, 0.0))),
                    score_type="l2",
                )
            )
        return hits
