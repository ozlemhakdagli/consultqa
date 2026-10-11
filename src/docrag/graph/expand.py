"""Graph expansion by personalised PageRank over the evidence graph. No model is involved."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import numpy as np
import scipy.sparse

from docrag.graph.build import EvidenceGraph
from docrag.models import Chunk, Hit


def expand(
    graph: EvidenceGraph,
    seeds: Mapping[str, float],
    query_terms: Iterable[str],
    chunks_by_id: Mapping[str, Chunk],
    *,
    restart: float,
    k: int,
    iterations: int = 50,
) -> list[Hit]:
    """Rank chunks by personalised PageRank from the seed chunks and the query terms.

    The reset vector has a seed half and a term half, each carrying 0.5 of the mass when
    present; an absent half hands its mass to the other. Seeds are included in the ranking.
    """
    reset = _reset_vector(graph, seeds, query_terms)
    if reset is None:
        return []

    transition = _column_normalised(graph.adjacency)
    mass = reset.copy()
    for _ in range(iterations):
        mass = (1.0 - restart) * (transition @ mass) + restart * reset

    ranked: list[tuple[float, str]] = []
    for chunk_id in graph.chunk_ids:
        score = float(mass[graph.node_index[f"c:{chunk_id}"]])
        if score > 0.0:
            ranked.append((score, chunk_id))
    # Python's sort is stable, so ties keep the graph's chunk order.
    ranked.sort(key=lambda item: -item[0])
    return [
        Hit(chunk=chunks_by_id[chunk_id], score=score, score_type="ppr", channel="graph")
        for score, chunk_id in ranked[:k]
    ]


def _reset_vector(
    graph: EvidenceGraph, seeds: Mapping[str, float], query_terms: Iterable[str]
) -> np.ndarray | None:
    """Reset distribution over graph nodes, or ``None`` when neither half is present."""
    seed_weights: dict[int, float] = {}
    for chunk_id, score in seeds.items():
        index = graph.node_index.get(f"c:{chunk_id}")
        if index is not None and score > 0.0:
            seed_weights[index] = float(score)

    term_indices = sorted(
        {graph.node_index[f"t:{term}"] for term in query_terms if f"t:{term}" in graph.node_index}
    )

    halves = int(bool(seed_weights)) + int(bool(term_indices))
    if halves == 0:
        return None

    share = 1.0 / halves
    reset = np.zeros(graph.adjacency.shape[0])
    if seed_weights:
        seed_total = sum(seed_weights.values())
        for index, weight in seed_weights.items():
            reset[index] += share * weight / seed_total
    if term_indices:
        for index in term_indices:
            reset[index] += share / len(term_indices)
    return reset


def _column_normalised(adjacency: scipy.sparse.spmatrix) -> scipy.sparse.csr_matrix:
    """Return ``A · D⁻¹``. A column with zero degree stays zero."""
    matrix = scipy.sparse.csr_matrix(adjacency, dtype=float)
    degree = np.asarray(matrix.sum(axis=0)).ravel()
    inverse = np.zeros_like(degree)
    nonzero = degree > 0.0
    inverse[nonzero] = 1.0 / degree[nonzero]
    return (matrix @ scipy.sparse.diags(inverse)).tocsr()
