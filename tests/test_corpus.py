"""Tests for the corpus schema and the JSONL passage loader."""

import json
from pathlib import Path

from hybrid_qa.corpus import Passage, load_jsonl_passages, save_jsonl_passages


def test_passage_id_joins_doc_and_update() -> None:
    passage = Passage("document_1", "update_2", "V1", "x")

    assert passage.passage_id == "document_1:update_2"


def test_passage_text_appends_version() -> None:
    passage = Passage("document_1", "update_2", "V1", "x")

    assert passage.text == "x (Versiyon: V1)"


def test_jsonl_roundtrip_preserves_all_fields(tmp_path: Path) -> None:
    passages = [
        Passage("d1", "u1", "V1.0", "Stok ekranı güncellendi", tool="Stok", section="Raporlar"),
        Passage("d2", "u2", "V2.0", "Açıklama ÇĞİÖŞÜ"),
    ]
    path = tmp_path / "corpus.jsonl"

    save_jsonl_passages(passages, path)

    assert load_jsonl_passages(path) == passages


def test_jsonl_writes_one_object_per_line_without_ascii_escapes(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"

    save_jsonl_passages([Passage("d1", "u1", "V1", "ğüş")], path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "ğüş" in lines[0]
    assert set(json.loads(lines[0])) == {
        "doc_id",
        "update_id",
        "version",
        "description",
        "tool",
        "section",
    }


def test_load_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        '{"doc_id": "d1", "update_id": "u1", "version": "V1", "description": "x"}\n'
        "\n"
        "   \n"
        '{"doc_id": "d2", "update_id": "u2", "version": "V2", "description": "y",'
        ' "tool": null, "section": null}\n',
        encoding="utf-8",
    )

    passages = load_jsonl_passages(path)

    assert [p.passage_id for p in passages] == ["d1:u1", "d2:u2"]


def test_old_positional_constructor_still_works() -> None:
    passage = Passage("d", "u", "V", "desc")

    assert passage.tool is None
    assert passage.section is None
    assert passage.text == "desc (Versiyon: V)"
