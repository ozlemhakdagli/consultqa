"""Paired cluster-bootstrap statistics and the verdict on the primary metrics.

Questions are grouped into clusters (for example, questions generated from the same
template). The bootstrap resamples whole clusters with replacement, so questions that
share a cluster do not shrink the interval artificially.
"""

from collections.abc import Mapping, Sequence
from typing import NamedTuple

import numpy as np


class Interval(NamedTuple):
    """A mean with its 95% percentile interval."""

    mean: float
    low: float
    high: float


def cluster_bootstrap(
    values: Sequence[float],
    clusters: Sequence[str],
    *,
    n_resamples: int = 2000,
    seed: int = 0,
) -> Interval:
    """Return the mean of ``values`` with a 95% cluster-bootstrap interval.

    Each resample draws whole clusters with replacement. Its statistic is the mean of the
    values of every question in the drawn clusters. For a paired comparison, pass the
    per-question differences as ``values``.
    """
    if len(values) != len(clusters):
        raise ValueError(f"values and clusters differ in length: {len(values)} != {len(clusters)}")
    if len(values) == 0:
        raise ValueError("bootstrap input is empty")

    data = np.asarray(values, dtype=float)
    _, codes = np.unique(np.asarray(clusters, dtype=object), return_inverse=True)
    codes = np.ravel(codes)
    n_clusters = int(codes.max()) + 1
    cluster_sums = np.bincount(codes, weights=data, minlength=n_clusters)
    cluster_counts = np.bincount(codes, minlength=n_clusters).astype(float)

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, n_clusters, size=(n_resamples, n_clusters))
    resample_means = cluster_sums[draws].sum(axis=1) / cluster_counts[draws].sum(axis=1)
    low, high = np.quantile(resample_means, [0.025, 0.975])
    return Interval(float(data.mean()), float(low), float(high))


def verdict(primary: Mapping[str, Interval]) -> str:
    """Return ``"worse"``, ``"better"`` or ``"undecided"`` for the primary intervals.

    ``"worse"`` wins when any interval lies entirely below zero. ``"better"`` needs every
    interval to lie entirely above zero. Anything else is ``"undecided"``.
    """
    if not primary:
        raise ValueError("verdict needs at least one primary interval")
    intervals = list(primary.values())
    if any(interval.high < 0 for interval in intervals):
        return "worse"
    if all(interval.low > 0 for interval in intervals):
        return "better"
    return "undecided"
