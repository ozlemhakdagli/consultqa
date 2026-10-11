import json

import pytest

from docrag.eval.records import EvalRecord, load_eval_jsonl, save_eval_jsonl


def test_unknown_answer_type_is_rejected(tmp_path):
    row = {
        "question": "q",
        "accepted_answers": ["a"],
        "gold_passage_ids": ["d:u"],
        "answer_type": "essay",
        "tag": "keyword",
        "family_id": "f",
        "cluster_id": "c",
        "split": "dev",
        "origin": "generated",
        "overlap": 0.1,
    }
    path = tmp_path / "e.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_eval_jsonl(path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("tag", "fuzzy"), ("split", "val"), ("origin", "human")],
)
def test_unknown_enum_values_are_rejected(field, value):
    fields = {
        "question": "q",
        "accepted_answers": ["a"],
        "gold_passage_ids": ["d:u"],
        "answer_type": "span",
        "tag": "keyword",
        "family_id": "f",
        "cluster_id": "c",
        "split": "dev",
        "origin": "generated",
        "overlap": 0.1,
    }
    fields[field] = value
    with pytest.raises(ValueError):
        EvalRecord(**fields)


def test_round_trip_keeps_turkish_text_and_skips_blank_lines(tmp_path):
    record = EvalRecord(
        question="İlk sürüm için hangi işlem yapıldı?",
        accepted_answers=["Işık ayarı", "ışık ayarı"],
        gold_passage_ids=["d1:u1", "d1:u2"],
        answer_type="set",
        tag="semantic",
        family_id="fam-1",
        cluster_id="fam-1|Modül",
        split="test",
        origin="agent-written",
        overlap=0.25,
    )
    path = tmp_path / "round.jsonl"
    save_eval_jsonl([record], path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n")

    assert load_eval_jsonl(path) == [record]
    assert "İlk sürüm" in path.read_text(encoding="utf-8")
