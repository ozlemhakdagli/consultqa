# tests/test_judge.py
import hashlib
from pathlib import Path

import pytest

from docrag.eval import judge as judge_module
from docrag.eval.judge import JUDGE_PROMPT, JUDGE_PROMPT_SHA256, judge_correct


class FakeLLM:
    def __init__(self, reply):
        self.reply = reply
        self.sent = []

    def chat(self, messages):
        self.sent.append(messages)
        return self.reply


def test_judge_reads_a_yes_or_no_reply():
    assert judge_correct("q", "Stok", ["Stok"], judge=FakeLLM("EVET")) is True
    assert judge_correct("q", "Raporlama", ["Stok"], judge=FakeLLM("HAYIR")) is False


def test_reply_is_matched_without_case_or_surrounding_whitespace():
    assert judge_correct("q", "Stok", ["Stok"], judge=FakeLLM("  Evet\n")) is True


@pytest.mark.parametrize("reply", ["", "belki", "EVET, kısmen"])
def test_any_other_reply_is_false(reply):
    assert judge_correct("q", "Stok", ["Stok"], judge=FakeLLM(reply)) is False


def test_judge_gets_the_fixed_prompt_and_the_three_inputs():
    judge = FakeLLM("HAYIR")
    judge_correct("Soru metni", "Model yanıtı", ["Kabul A", "Kabul B"], judge=judge)
    system, user = judge.sent[0]
    assert system == {"role": "system", "content": JUDGE_PROMPT}
    assert user["role"] == "user"
    for text in ("Soru metni", "Model yanıtı", "Kabul A", "Kabul B"):
        assert text in user["content"]


def test_prompt_file_matches_its_pinned_sha256():
    prompt_path = Path(judge_module.__file__).with_name("judge_prompt.txt")
    assert hashlib.sha256(prompt_path.read_bytes()).hexdigest() == JUDGE_PROMPT_SHA256
