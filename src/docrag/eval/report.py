"""Render the evaluation ladder as Markdown: cluster-bootstrap intervals and paired verdicts."""

from collections.abc import Mapping, Sequence

from docrag.eval.stats import Interval, cluster_bootstrap, verdict

# Primary metrics of the protocol: retrieval MRR@10, answer EM and F1.
PRIMARY_METRICS = ("mrr10", "em", "f1")
ANECDOTAL_MAX_N = 20

_HEADER = (
    "| system | n | clusters | MRR@10 [95% CI] | EM [95% CI] | F1 [95% CI] "
    "| Δ MRR@10 vs {baseline} [95% CI] | verdict |"
)
_FOOTNOTE = (
    "Primary intervals are paired against {baseline}, per question, clustered by cluster_id. "
    "Verdict: worse if any primary interval lies entirely below zero; better if every primary "
    "interval lies entirely above zero; otherwise undecided. Slices with n <= 20 are anecdotal."
)


def _fmt(interval: Interval) -> str:
    """Format a mean with its interval, three decimals."""
    return f"{interval.mean:.3f} [{interval.low:.3f}, {interval.high:.3f}]"


def _fmt_diff(interval: Interval) -> str:
    """Format a signed paired difference with its interval, three decimals."""
    return f"{interval.mean:+.3f} [{interval.low:+.3f}, {interval.high:+.3f}]"


def _aligned_baseline(rows: Sequence[dict], baseline_rows: Sequence[dict]) -> list[dict]:
    """Return the baseline row for each row, matched by ``qid``."""
    by_qid = {row["qid"]: row for row in baseline_rows}
    aligned = []
    for row in rows:
        if row["qid"] not in by_qid:
            raise ValueError(f"question {row['qid']!r} is missing from the baseline")
        aligned.append(by_qid[row["qid"]])
    return aligned


def render_ladder(tables: Mapping[str, list[dict]], *, baseline: str) -> str:
    """Return a Markdown table with one row per system, from rows keyed by system name.

    Each cell of the metric columns is the mean of the system's rows with a cluster-bootstrap
    95% interval. The Δ column and the verdict use paired per-question differences against the
    baseline table, matched by ``qid``. A system whose slice has 20 or fewer questions is labelled
    anecdotal.
    """
    if baseline not in tables:
        raise ValueError(f"baseline {baseline!r} is not one of the tables")
    baseline_rows = tables[baseline]
    names = [baseline, *(name for name in tables if name != baseline)]

    lines = [_HEADER.format(baseline=baseline), "|" + "---|" * 8]
    for name in names:
        rows = tables[name]
        clusters = [row["cluster_id"] for row in rows]
        label = f"{name} (anecdotal)" if len(rows) <= ANECDOTAL_MAX_N else name
        cells = [label, f"n={len(rows)}", str(len(set(clusters)))]
        for metric in PRIMARY_METRICS:
            values = [row[metric] for row in rows]
            cells.append(_fmt(cluster_bootstrap(values, clusters)))
        if name == baseline:
            cells += ["—", "baseline"]
        else:
            aligned = _aligned_baseline(rows, baseline_rows)
            diff_intervals = {
                metric: cluster_bootstrap(
                    [row[metric] - base[metric] for row, base in zip(rows, aligned, strict=True)],
                    clusters,
                )
                for metric in PRIMARY_METRICS
            }
            cells += [_fmt_diff(diff_intervals["mrr10"]), verdict(diff_intervals)]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n" + _FOOTNOTE.format(baseline=baseline) + "\n"
