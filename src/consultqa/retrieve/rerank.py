"""Cross-encoder and causal-LM reranking of the first hits of a ranked list."""

from collections.abc import Callable, Sequence

import numpy as np

from consultqa.config import MODEL_PINS
from consultqa.models import Hit

Scorer = Callable[[str, Sequence[str]], Sequence[float]]

QWEN3_INSTRUCTION = "Given a web search query, retrieve relevant passages that answer the query"
QWEN3_MAX_LENGTH = 8192
_QWEN3_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".'
    "<|im_end|>\n<|im_start|>user\n"
)
_QWEN3_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


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


def format_qwen3_pair(query: str, document: str, instruction: str = QWEN3_INSTRUCTION) -> str:
    """Return the user turn that the Qwen3-Reranker model card gives for one pair."""
    return f"<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}"


def yes_minus_no(yes_logits: Sequence[float], no_logits: Sequence[float]) -> list[float]:
    """Return the 'yes' logit minus the 'no' logit of each pair at the answer position.

    The sigmoid of this difference is the probability of "yes" that the model card reports, so
    the two rank pairs identically. The difference is kept because the probability rounds to
    exactly 1.0 for confident pairs, which would tie them.
    """
    yes = np.asarray(yes_logits, dtype=np.float64)
    no = np.asarray(no_logits, dtype=np.float64)
    if yes.shape != no.shape:
        raise ValueError(f"yes and no logits differ in length: {yes.shape} != {no.shape}")
    return [float(score) for score in yes - no]


def load_causal_reranker(model_key: str = "qwen3-reranker-0.6b", *, batch_size: int = 8) -> Scorer:
    """Load a pinned Qwen3-Reranker and return a scorer that reads its yes/no logits.

    Each pair is wrapped in the model card's chat prompt: a fixed system turn, the user turn from
    ``format_qwen3_pair``, and an empty thinking block. The score is ``yes_minus_no`` of the
    logits at the last position. Inputs are truncated to ``QWEN3_MAX_LENGTH`` tokens and
    left-padded, so the last position is the answer position for every row.

    ``torch`` and ``transformers`` are imported here, not at module import.
    """
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_id, revision = MODEL_PINS[model_key]
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, padding_side="left")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AutoModelForCausalLM.from_pretrained(model_id, revision=revision).to(device).eval()
    prefix_ids = tokenizer.encode(_QWEN3_PREFIX, add_special_tokens=False)
    suffix_ids = tokenizer.encode(_QWEN3_SUFFIX, add_special_tokens=False)
    yes_id = tokenizer.convert_tokens_to_ids("yes")
    no_id = tokenizer.convert_tokens_to_ids("no")
    body_budget = QWEN3_MAX_LENGTH - len(prefix_ids) - len(suffix_ids)

    def scorer(query: str, texts: Sequence[str]) -> Sequence[float]:
        scores: list[float] = []
        for start in range(0, len(texts), batch_size):
            pairs = [format_qwen3_pair(query, text) for text in texts[start : start + batch_size]]
            bodies = tokenizer(
                pairs, add_special_tokens=False, truncation=True, max_length=body_budget
            )["input_ids"]
            ids = [prefix_ids + body + suffix_ids for body in bodies]
            batch = tokenizer.pad({"input_ids": ids}, padding=True, return_tensors="pt").to(device)
            with torch.no_grad():
                last = model(**batch, logits_to_keep=1).logits[:, -1, :].float().cpu()
            scores.extend(yes_minus_no(last[:, yes_id].tolist(), last[:, no_id].tolist()))
        return scores

    return scorer
