import hashlib
import json
from pathlib import Path

from consultqa.eval.datasets import file_sha256, load_corpus_jsonl

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample" / "corpus.jsonl"


def test_sample_corpus_has_unique_chunk_ids_and_reference_text():
    chunks = load_corpus_jsonl(SAMPLE)
    assert len(chunks) == 480
    assert len({c.chunk_id for c in chunks}) == 480
    assert chunks[0].text.endswith(" (Versiyon: V2.1.0)")


def test_positions_count_per_document_and_heading_path_drops_empty_parts(tmp_path):
    rows = [
        {
            "doc_id": "d1",
            "update_id": "u1",
            "version": "V1",
            "description": "birinci",
            "tool": "Modül A",
            "section": None,
        },
        {
            "doc_id": "d2",
            "update_id": "u1",
            "version": "V2",
            "description": "ikinci",
            "tool": None,
            "section": "Bölüm",
        },
        {
            "doc_id": "d1",
            "update_id": "u2",
            "version": "V1",
            "description": "üçüncü",
            "tool": "Modül A",
            "section": "Liste",
        },
    ]
    path = tmp_path / "corpus.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n\n", encoding="utf-8"
    )

    chunks = load_corpus_jsonl(path)

    assert [c.chunk_id for c in chunks] == ["d1:u1", "d2:u1", "d1:u2"]
    assert [c.position for c in chunks] == [0, 0, 1]
    assert [c.heading_path for c in chunks] == [("Modül A",), ("Bölüm",), ("Modül A", "Liste")]
    assert chunks[1].text == "ikinci (Versiyon: V2)"


def test_file_sha256_matches_hashlib(tmp_path):
    path = tmp_path / "blob.bin"
    path.write_bytes(b"\x00merhaba\n" * 1000)
    assert file_sha256(path) == hashlib.sha256(path.read_bytes()).hexdigest()
