"""Tests for hybrid_qa.data_loader."""

import json
from pathlib import Path

import pytest

from hybrid_qa.config import PROCESSED_JSON_PATH
from hybrid_qa.data_loader import Passage, load_passages


def _write_fixture(path: Path) -> Path:
    data = [
        {
            "id": "document_1",
            "version_info": {"version": "V1.0", "date": "2024-01-01", "changes": "x"},
            "updates": [
                {"id": "update_1", "description": "Birinci güncelleme"},
                {"id": "update_2", "description": "İkinci güncelleme"},
            ],
        },
        {
            "id": "document_2",
            "version_info": {"version": "V2.0", "date": "2024-02-01", "changes": "y"},
            "updates": [{"id": "update_1", "description": "Üçüncü güncelleme"}],
        },
    ]
    json_path = path / "data.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return json_path


def test_count_and_order(tmp_path: Path) -> None:
    passages = load_passages(_write_fixture(tmp_path))

    assert len(passages) == 3
    assert [(p.doc_id, p.update_id) for p in passages] == [
        ("document_1", "update_1"),
        ("document_1", "update_2"),
        ("document_2", "update_1"),
    ]
    assert passages[0].version == "V1.0"
    assert passages[2].version == "V2.0"
    assert passages[1].description == "İkinci güncelleme"


def test_text_format(tmp_path: Path) -> None:
    passage = Passage(doc_id="d", update_id="u", version="V9.9.9", description="Açıklama")

    assert passage.text == "Açıklama (Versiyon: V9.9.9)"


def test_passage_is_frozen(tmp_path: Path) -> None:
    passage = load_passages(_write_fixture(tmp_path))[0]

    try:
        passage.description = "changed"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("Passage should be immutable")


@pytest.mark.skipif(not PROCESSED_JSON_PATH.exists(), reason="private data not available")
def test_real_data_counts() -> None:
    documents = json.loads(PROCESSED_JSON_PATH.read_text(encoding="utf-8"))
    passages = load_passages()

    assert len(documents) == 23
    assert len(passages) == 904
