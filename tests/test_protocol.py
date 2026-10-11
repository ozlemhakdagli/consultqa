import json

from docrag.eval.datasets import file_sha256
from docrag.eval.protocol import load_protocol, verify_protocol


def test_hash_mismatch_is_reported(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    protocol = {"files": {"a": {"sha256": "0" * 64}}}
    problems = verify_protocol(protocol, {"a": f})
    assert len(problems) == 1 and "a" in problems[0]


def test_matching_hashes_verify_to_empty_list(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    protocol = {"files": {"a": {"sha256": file_sha256(f)}}}
    assert verify_protocol(protocol, {"a": f}) == []


def test_declared_file_without_a_path_is_reported(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    protocol = {"files": {"a": {"sha256": file_sha256(f)}, "b": {"sha256": "0" * 64}}}
    problems = verify_protocol(protocol, {"a": f})
    assert len(problems) == 1 and "b" in problems[0]


def test_load_protocol_reads_json(tmp_path):
    payload = {"primary_metric": "mrr@10", "files": {"a": {"sha256": "0" * 64}}}
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_protocol(path) == payload
