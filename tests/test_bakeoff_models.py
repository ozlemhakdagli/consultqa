# tests/test_bakeoff_models.py
import numpy as np
import pytest

from docrag.config import MODEL_PINS
from docrag.eval.bakeoff_models import choose, pinned_revision
from docrag.retrieve.dense import ENCODER_SPECS, SentenceEncoder
from docrag.retrieve.rerank import format_qwen3_pair, load_causal_reranker, yes_minus_no


def test_highest_mrr_wins_and_ties_go_to_the_smaller_model():
    table = {
        "a": {"mrr10": 0.5, "size_mb": 2000},
        "b": {"mrr10": 0.5, "size_mb": 500},
        "c": {"mrr10": 0.4, "size_mb": 100},
    }
    assert choose(table) == "b"


def test_float_noise_in_a_mean_is_a_tie():
    table = {
        "big": {"mrr10": 0.5 + 1e-15, "size_mb": 2000},
        "small": {"mrr10": 0.5, "size_mb": 500},
    }
    assert choose(table) == "small"


def test_choose_rejects_an_empty_table():
    with pytest.raises(ValueError):
        choose({})


def test_pinned_revision_returns_the_pin_only_when_the_sha_matches():
    pinned = MODEL_PINS["qwen3-reranker-0.6b"][1]
    assert pinned_revision("qwen3-reranker-0.6b", pinned) == pinned
    with pytest.raises(ValueError):
        pinned_revision("qwen3-reranker-0.6b", "0" * 40)


def test_new_candidates_have_pins_and_encoder_specs():
    for key in ("e5-large-instruct", "qwen3-embedding-0.6b", "qwen3-reranker-0.6b"):
        assert key in MODEL_PINS
    for key in ("e5-large-instruct", "qwen3-embedding-0.6b"):
        assert ENCODER_SPECS[key].model_key == key
        assert key in MODEL_PINS


def test_qwen3_pair_follows_the_model_card_format():
    text = format_qwen3_pair("soru", "belge")
    assert text == (
        "<Instruct>: Given a web search query, retrieve relevant passages that answer the query\n"
        "<Query>: soru\n<Document>: belge"
    )


def test_yes_minus_no_orders_like_the_card_probability():
    yes = np.array([2.0, -1.0, 0.5, 30.0])
    no = np.array([0.0, 0.0, 0.5, 0.0])
    scores = yes_minus_no(yes, no)
    assert scores == [2.0, -1.0, 0.0, 30.0]
    probability = 1.0 / (1.0 + np.exp(-np.asarray(scores)))  # the card's P(yes)
    assert list(np.argsort(scores)) == list(np.argsort(probability))


def test_yes_minus_no_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        yes_minus_no([1.0, 2.0], [1.0])


@pytest.mark.model
def test_qwen3_reranker_scores_the_relevant_text_first_and_is_padding_invariant():
    texts = [
        "Stok raporu depo bazında toplam miktarları gösterir.",
        "Kedi sabah saatlerinde bahçede uyudu ve sonra evin içine girdi.",
        "Sipariş formunda teslim tarihi ve adres alanları zorunludur.",
    ]
    query = "Sipariş formunda hangi alanlar zorunludur?"
    scorer_small_batch = load_causal_reranker("qwen3-reranker-0.6b", batch_size=2)
    small = list(scorer_small_batch(query, texts))
    assert len(small) == 3
    assert int(np.argmax(small)) == 2
    scorer_large_batch = load_causal_reranker("qwen3-reranker-0.6b", batch_size=8)
    large = list(scorer_large_batch(query, texts))
    assert np.allclose(small, large, atol=1e-3)


@pytest.mark.model
def test_qwen3_embedder_is_padding_invariant_under_last_token_pooling():
    encoder = SentenceEncoder(ENCODER_SPECS["qwen3-embedding-0.6b"])
    alone = encoder.encode_passages(["Stok raporu"])[0]
    batched = encoder.encode_passages(
        ["Stok raporu", "çok daha uzun bir cümle burada yer alıyor ve devam ediyor"]
    )[0]
    assert float(np.dot(alone, batched)) > 0.999
