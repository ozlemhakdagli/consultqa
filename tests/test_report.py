import pytest

from docrag.eval.report import render_ladder


def _row(qid, cluster, mrr, em, f1):
    return {"qid": qid, "cluster_id": cluster, "mrr10": mrr, "em": em, "f1": f1}


def test_small_slices_are_marked_anecdotal():
    rows = [{"qid": "q", "cluster_id": "c", "mrr10": 0.5, "em": 0.0, "f1": 0.2}]
    text = render_ladder({"L0": rows, "L2": rows}, baseline="L0")
    assert "anecdotal" in text and "n=1" in text


def test_large_slices_are_not_marked_anecdotal():
    rows = [_row(str(i), f"c{i}", 0.5, 0.5, 0.5) for i in range(30)]
    text = render_ladder({"L0": rows}, baseline="L0")
    assert "L0 (anecdotal)" not in text and "n=30" in text


def test_paired_difference_on_every_primary_metric_gives_better():
    base = [_row(str(i), f"c{i}", 0.0, 0.0, 0.0) for i in range(30)]
    system = [_row(str(i), f"c{i}", 1.0, 1.0, 1.0) for i in range(30)]
    text = render_ladder({"L0": base, "L2": system}, baseline="L0")
    assert "+1.000 [+1.000, +1.000]" in text
    assert "better" in text


def test_one_primary_interval_below_zero_gives_worse():
    base = [_row(str(i), f"c{i}", 0.0, 1.0, 1.0) for i in range(30)]
    system = [_row(str(i), f"c{i}", 1.0, 0.0, 1.0) for i in range(30)]
    text = render_ladder({"L0": base, "L2": system}, baseline="L0")
    assert "worse" in text


def test_baseline_must_be_one_of_the_tables():
    rows = [_row("q", "c", 0.5, 0.5, 0.5)]
    with pytest.raises(ValueError, match="baseline"):
        render_ladder({"L2": rows}, baseline="L0")
