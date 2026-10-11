"""Reciprocal rank fusion and text de-duplication of ranked retrieval hits."""

from collections.abc import Sequence

from docrag.config import RRF_K
from docrag.models import Hit


def rrf_fuse(channels: Sequence[Sequence[Hit]], *, k: int, rrf_k: int = RRF_K) -> list[Hit]:
    """Fuse ranked channels by reciprocal rank and return the top ``k`` hits.

    Each channel contributes ``1 / (rrf_k + rank)`` for every chunk it contains, with ranks
    counted from 1. A chunk repeated inside one channel counts only at its first rank. Ties in
    score are broken by the best single-channel rank, then by first-seen order.
    """
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    first_hit: dict[str, Hit] = {}
    for channel in channels:
        seen: set[str] = set()
        for rank, hit in enumerate(channel, start=1):
            cid = hit.chunk.chunk_id
            if cid in seen:
                continue
            seen.add(cid)
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)
            best_rank[cid] = min(best_rank.get(cid, rank), rank)
            first_hit.setdefault(cid, hit)
    # ``scores`` is insertion-ordered (first seen), and ``sorted`` is stable.
    order = sorted(scores, key=lambda cid: (-scores[cid], best_rank[cid]))
    return [Hit(first_hit[cid].chunk, scores[cid], "rrf", "rrf") for cid in order[:k]]


def dedupe_by_text(hits: Sequence[Hit]) -> list[Hit]:
    """Keep the first hit for each distinct ``chunk.text``, preserving order."""
    seen: set[str] = set()
    kept: list[Hit] = []
    for hit in hits:
        if hit.chunk.text not in seen:
            seen.add(hit.chunk.text)
            kept.append(hit)
    return kept
