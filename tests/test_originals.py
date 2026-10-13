"""Tests for the store that keeps the uploaded original of each document."""

from pathlib import Path

import pytest

from consultqa.store.originals import OriginalFiles

DOC_ID = "0123456789abcdef0123456789abcdef"


def test_save_then_path_returns_same_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4 original bytes")
    files = OriginalFiles(tmp_path / "originals")

    saved = files.save(DOC_ID, source)

    assert saved == tmp_path / "originals" / f"{DOC_ID}.pdf"
    assert files.path(DOC_ID) == saved
    assert saved.read_bytes() == b"%PDF-1.4 original bytes"


def test_unknown_id_gives_none(tmp_path: Path) -> None:
    files = OriginalFiles(tmp_path / "originals")

    assert files.path(DOC_ID) is None


def test_hostile_ids_give_none(tmp_path: Path) -> None:
    root = tmp_path / "originals"
    # Files outside the folder that a traversal id would reach.
    (tmp_path / "x.pdf").write_bytes(b"outside")
    (tmp_path / f"{DOC_ID}.pdf").write_bytes(b"outside")
    # Files inside the folder named with the exact malformed ids, so only the check can refuse them.
    root.mkdir()
    (root / f"{DOC_ID.upper()}.pdf").write_bytes(b"inside")
    (root / f"{'a' * 200}.pdf").write_bytes(b"inside")
    files = OriginalFiles(root)

    assert files.path("../x") is None
    assert files.path(f"../{DOC_ID}") is None
    assert files.path(DOC_ID.upper()) is None
    assert files.path("a" * 200) is None


def test_save_rejects_malformed_id_and_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("secret", encoding="utf-8")
    root = tmp_path / "originals"
    files = OriginalFiles(root)

    for bad_id in ("../escaped", DOC_ID.upper(), "a" * 200):
        with pytest.raises(ValueError):
            files.save(bad_id, source)

    assert not (tmp_path / "escaped.txt").exists()
    assert not root.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["source.txt"]


def test_delete_twice_does_not_raise(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("text", encoding="utf-8")
    files = OriginalFiles(tmp_path / "originals")
    files.save(DOC_ID, source)

    files.delete(DOC_ID)
    files.delete(DOC_ID)

    assert files.path(DOC_ID) is None


def test_delete_many_removes_all(tmp_path: Path) -> None:
    other_id = "fedcba9876543210fedcba9876543210"
    source = tmp_path / "source.md"
    source.write_text("# Title", encoding="utf-8")
    files = OriginalFiles(tmp_path / "originals")
    files.save(DOC_ID, source)
    files.save(other_id, source)

    files.delete_many([DOC_ID, other_id, "0" * 32])

    assert files.path(DOC_ID) is None
    assert files.path(other_id) is None


def test_save_keeps_lower_cased_suffix(tmp_path: Path) -> None:
    source = tmp_path / "Report.PDF"
    source.write_bytes(b"%PDF")
    files = OriginalFiles(tmp_path / "originals")

    saved = files.save(DOC_ID, source)

    assert saved.name == f"{DOC_ID}.pdf"


def test_media_type_for_each_suffix(tmp_path: Path) -> None:
    files = OriginalFiles(tmp_path)

    assert files.media_type(Path("a.pdf")) == "application/pdf"
    assert files.media_type(Path("a.txt")) == "text/plain; charset=utf-8"
    assert files.media_type(Path("a.md")) == "text/markdown; charset=utf-8"
