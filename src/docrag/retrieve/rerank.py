"""Cross-encoder reranking of the first hits of a ranked list."""

from collections.abc import Callable, Sequence

from docrag.config import MODEL_PINS
from docrag.models import Hit

Scorer = Callable[[str, Sequence[str]], Sequence[float]]


def rerank(
    query: str,
    hits: Sequence[Hit],
    scorer: Scorer,
    *,
    depth: int,
    k: int,
) -> list[Hit]:
    """Score the first ``depth`` hits against ``query`` and return the best ``k`` of them.

    Ties keep input order. Hits beyond ``depth`` are not scored and not returned. Raises
    ``ValueError`` if the scorer does not return exactly one score per scored hit.
    """
    pool = list(hits[:depth])
    if not pool:
        return []
    scores = list(scorer(query, [hit.chunk.text for hit in pool]))
    if len(scores) != len(pool):
        raise ValueError(f"scorer returned {len(scores)} scores for {len(pool)} hits")
    order = sorted(range(len(pool)), key=lambda i: -scores[i])
    return [Hit(pool[i].chunk, float(scores[i]), "cross_encoder", "rerank") for i in order[:k]]


def load_cross_encoder(model_key: str = "reranker-v2-m3") -> Scorer:
    """Load the pinned cross-encoder named by ``model_key`` and return a scorer for it.

    ``sentence_transformers`` is imported here, not at module import, so that code paths
    without reranking do not need it installed.
    """
    from sentence_transformers import CrossEncoder

    model_id, revision = MODEL_PINS[model_key]
    model = CrossEncoder(model_id, revision=revision)

    def scorer(query: str, texts: Sequence[str]) -> Sequence[float]:
        pairs = [(query, text) for text in texts]
        return [float(s) for s in model.predict(pairs)]

    return scorer
