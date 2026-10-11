# tests/test_stats.py
import pytest

from consultqa.eval.stats import Interval, cluster_bootstrap, verdict


def test_bootstrap_is_seeded():
    values = [1.0, 0.0, 1.0, 1.0]
    clusters = ["a", "a", "b", "c"]
    first = cluster_bootstrap(values, clusters, seed=0)
    assert first == cluster_bootstrap(values, clusters, seed=0)


def test_constant_values_give_a_point_interval():
    assert cluster_bootstrap([1.0, 1.0], ["a", "b"]) == Interval(1.0, 1.0, 1.0)


def test_resampling_keeps_clusters_whole():
    # Both questions share one cluster, so every resample has the same mean.
    assert cluster_bootstrap([1.0, 0.0], ["a", "a"]) == Interval(0.5, 0.5, 0.5)


def test_interval_brackets_the_mean():
    values = [1.0, 0.0, 1.0, 0.0, 1.0, 1.0]
    clusters = ["a", "b", "c", "d", "e", "f"]
    interval = cluster_bootstrap(values, clusters)
    assert interval.mean == pytest.approx(4 / 6)
    assert interval.low <= interval.mean <= interval.high


@pytest.mark.parametrize(("values", "clusters"), [([], []), ([1.0], ["a", "b"])])
def test_bad_bootstrap_inputs_are_rejected(values, clusters):
    with pytest.raises(ValueError):
        cluster_bootstrap(values, clusters)


def test_verdict_order():
    assert verdict({"mrr": Interval(0.1, 0.02, 0.2)}) == "better"
    assert verdict({"mrr": Interval(0.1, 0.02, 0.2), "em": Interval(-0.1, -0.2, -0.01)}) == "worse"
    assert verdict({"mrr": Interval(0.0, -0.1, 0.1)}) == "undecided"


def test_worse_wins_over_undecided():
    primary = {"mrr": Interval(0.0, -0.1, 0.1), "em": Interval(-0.1, -0.2, -0.01)}
    assert verdict(primary) == "worse"


def test_an_interval_touching_zero_is_not_better():
    assert verdict({"mrr": Interval(0.0, 0.0, 0.1)}) == "undecided"


def test_verdict_rejects_an_empty_primary_set():
    with pytest.raises(ValueError):
        verdict({})
