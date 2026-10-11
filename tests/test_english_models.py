"""English checks with the real models. They need the pinned weights in the local Hugging Face
cache, so they are marked ``model`` and run only with ``pytest -m model``."""

import numpy as np
import pytest

from consultqa.generate.extractive import ExtractiveReader
from consultqa.retrieve.dense import ENCODER_SPECS, SentenceEncoder

INVOICE = "Invoices are paid within 30 days of receipt."
SHIPPING = "Shipping takes five working days."


@pytest.mark.model
def test_bge_m3_places_an_english_question_nearest_its_answer():
    encoder = SentenceEncoder(ENCODER_SPECS["bge-m3"])
    question = np.ravel(encoder.encode_query("How many days do invoices take to be paid?"))
    passages = encoder.encode_passages([INVOICE, SHIPPING])
    scores = np.asarray(passages @ question).ravel()
    assert scores[0] > scores[1]


@pytest.mark.model
def test_the_real_reader_finds_the_english_answer():
    answer, _score = ExtractiveReader().answer_span(
        "Within how many days are invoices paid?", INVOICE
    )
    assert "30" in answer
