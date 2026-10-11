"""Retrieval and answer metrics: recall, reciprocal rank, EM, token F1, lenient and set F1.

Answer metrics take the prediction and a list of accepted answers and return the best score
over that list. An empty accepted list raises ``ValueError`` rather than scoring 0.0.
"""

from collections import Counter
from collections.abc import Collection, Sequence

from docrag.text import normalize_answer, tokenize_tr


def recall_at_k(ranked_ids: Sequence[str], gold_ids: Collection[str], k: int) -> float:
    """Return 1.0 when any gold id appears in the top k ranked ids, else 0.0."""
    gold = set(gold_ids)
    return 1.0 if any(item in gold for item in ranked_ids[:k]) else 0.0


def reciprocal_rank_at_k(
    ranked_ids: Sequence[str], gold_ids: Collection[str], k: int = 10
) -> float:
    """Return 1 / rank of the first gold id within the top k, or 0.0 when absent."""
    gold = set(gold_ids)
    for rank, item in enumerate(ranked_ids[:k], start=1):
        if item in gold:
            return 1.0 / rank
    return 0.0


def _require_accepted(accepted: Sequence[str]) -> None:
    """Raise ValueError when the accepted answer list is empty."""
    if not accepted:
        raise ValueError("accepted answers must not be empty")


def exact_match(prediction: str | None, accepted: Sequence[str]) -> float:
    """Return 1.0 when the normalised prediction equals any normalised accepted answer."""
    _require_accepted(accepted)
    normalized = normalize_answer(prediction)
    if not normalized:
        return 0.0
    return 1.0 if any(normalized == normalize_answer(answer) for answer in accepted) else 0.0


def _token_f1_pair(prediction_tokens: list[str], gold_tokens: list[str]) -> float:
    """Return multiset token F1 between two token lists."""
    if not prediction_tokens or not gold_tokens:
        return 0.0
    overlap = sum((Counter(prediction_tokens) & Counter(gold_tokens)).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(prediction_tokens)
    recall = overlap / len(gold_tokens)
    return 2 * precision * recall / (precision + recall)


def token_f1(prediction: str | None, accepted: Sequence[str]) -> float:
    """Return the maximum multiset token F1 of the prediction against accepted answers."""
    _require_accepted(accepted)
    prediction_tokens = tokenize_tr(prediction or "")
    return max(_token_f1_pair(prediction_tokens, tokenize_tr(answer)) for answer in accepted)


def _contains_run(haystack: list[str], needle: list[str]) -> bool:
    """Return True when ``needle`` occurs as a contiguous run of tokens inside ``haystack``."""
    width = len(needle)
    starts = range(len(haystack) - width + 1)
    return any(haystack[start : start + width] == needle for start in starts)


def lenient_match(prediction: str | None, accepted: Sequence[str], cap_ratio: float = 2.0) -> float:
    """Return 1.0 when an accepted answer appears in the prediction as a run of tokens.

    Matching is on ``tokenize_tr`` tokens, so a Turkish suffix after a name ("İstanbul'da")
    still contains the bare name. The prediction must not have more than ``cap_ratio`` times
    the accepted answer's token count, so long answers that merely mention the gold text
    do not score.
    """
    _require_accepted(accepted)
    prediction_tokens = tokenize_tr(prediction or "")
    if not prediction_tokens:
        return 0.0
    for answer in accepted:
        answer_tokens = tokenize_tr(answer)
        if not answer_tokens:
            continue
        if len(prediction_tokens) > cap_ratio * len(answer_tokens):
            continue
        if _contains_run(prediction_tokens, answer_tokens):
            return 1.0
    return 0.0


def set_f1(predicted: Collection[str], gold: Collection[str]) -> float:
    """Return F1 between two sets; two empty sets score 1.0 and one empty set scores 0.0."""
    predicted_set = set(predicted)
    gold_set = set(gold)
    if not predicted_set and not gold_set:
        return 1.0
    overlap = len(predicted_set & gold_set)
    if overlap == 0:
        return 0.0
    precision = overlap / len(predicted_set)
    recall = overlap / len(gold_set)
    return 2 * precision * recall / (precision + recall)
