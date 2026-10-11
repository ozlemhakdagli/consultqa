import json

import pytest

from docrag.config import PRESETS
from docrag.eval import run_header
from docrag.eval.cli import main
from docrag.eval.datasets import file_sha256
from docrag.eval.run_header import build_run_header


def test_help_exits_cleanly():
    with pytest.raises(SystemExit) as info:
        main(["run", "--help"])
    assert info.value.code == 0


def test_verify_protocol_passes_when_hashes_match(tmp_path):
    data = tmp_path / "a.txt"
    data.write_text("x", encoding="utf-8")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps({"files": {"a": {"sha256": file_sha256(data)}}}), encoding="utf-8"
    )
    assert main(["verify-protocol", "--protocol", str(protocol), "--file", f"a={data}"]) == 0


def test_verify_protocol_reports_a_changed_file(tmp_path, capsys):
    data = tmp_path / "a.txt"
    data.write_text("x", encoding="utf-8")
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps({"files": {"a": {"sha256": "0" * 64}}}), encoding="utf-8")
    code = main(["verify-protocol", "--protocol", str(protocol), "--file", f"a={data}"])
    assert code == 1
    assert "a: sha256 differs from protocol" in capsys.readouterr().err


def test_run_rejects_an_unknown_preset(tmp_path):
    with pytest.raises(SystemExit) as info:
        main(
            [
                "run",
                "--corpus",
                str(tmp_path / "c.jsonl"),
                "--eval",
                str(tmp_path / "e.jsonl"),
                "--presets",
                "L9",
            ]
        )
    assert info.value.code == 2


def test_run_rejects_a_baseline_that_is_not_run(tmp_path):
    with pytest.raises(SystemExit) as info:
        main(
            [
                "run",
                "--corpus",
                str(tmp_path / "c.jsonl"),
                "--eval",
                str(tmp_path / "e.jsonl"),
                "--presets",
                "L2,L3",
                "--baseline",
                "L0",
            ]
        )
    assert info.value.code == 2


def test_run_with_an_llm_preset_needs_an_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv("DOCRAG_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("DOCRAG_LLM_MODEL", raising=False)
    with pytest.raises(SystemExit) as info:
        main(
            [
                "run",
                "--corpus",
                str(tmp_path / "c.jsonl"),
                "--eval",
                str(tmp_path / "e.jsonl"),
                "--presets",
                "L2,L4+llm",
                "--baseline",
                "L2",
            ]
        )
    assert info.value.code == 2


def test_run_header_records_hashes_and_configs():
    header = build_run_header(corpus_sha="a" * 64, eval_sha="b" * 64, configs={"L2": PRESETS["L2"]})
    assert header["corpus_sha"] == "a" * 64
    assert header["eval_sha"] == "b" * 64
    assert header["configs"]["L2"]["name"] == "L2"
    assert set(header["libraries"]) == {"torch", "transformers", "sentence-transformers"}
    assert set(header["git"]) == {"head", "dirty"}


def test_missing_libraries_are_reported_as_none(monkeypatch):
    def _absent(name):
        raise run_header.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(run_header.metadata, "version", _absent)
    header = build_run_header(corpus_sha="a", eval_sha="b", configs={})
    assert all(value is None for value in header["libraries"].values())
    assert header["cuda_available"] is None
