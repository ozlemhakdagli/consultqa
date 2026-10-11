import pytest
from pdf_fixtures import write_pdf

from consultqa.eval.bakeoff import parser_scores
from consultqa.ingest.parse import DoclingParser, ParseError, TextParser


def test_perfect_parser_scores_one(tmp_path):
    truth = tmp_path / "t.md"
    truth.write_text("# Giriş\nSipariş modülü güncellendi", encoding="utf-8")
    source = tmp_path / "t.txt"
    source.write_text(truth.read_text(encoding="utf-8"), encoding="utf-8")
    scores = parser_scores(TextParser(), [(source, truth)])
    assert scores["word_f1"] == pytest.approx(1.0)


def test_word_f1_counts_repeated_words_as_a_multiset(tmp_path):
    truth = tmp_path / "t.md"
    truth.write_text("a a b", encoding="utf-8")
    source = tmp_path / "t.txt"
    source.write_text("a b b", encoding="utf-8")
    # Overlap is min(2, 1) + min(1, 2) = 2; precision and recall are both 2/3.
    scores = parser_scores(TextParser(), [(source, truth)])
    assert scores["word_f1"] == pytest.approx(2 / 3)


def test_heading_recall_counts_only_lines_marked_as_headings(tmp_path):
    truth = tmp_path / "t.md"
    truth.write_text("# Giriş\n## Stok\nmetin", encoding="utf-8")
    no_headings = tmp_path / "none.txt"
    no_headings.write_text("Giriş\nStok\nmetin", encoding="utf-8")
    one_heading = tmp_path / "one.txt"
    one_heading.write_text("# Giriş\nStok\nmetin", encoding="utf-8")

    none_scores = parser_scores(TextParser(), [(no_headings, truth)])
    one_scores = parser_scores(TextParser(), [(one_heading, truth)])

    assert none_scores["heading_recall"] == pytest.approx(0.0)
    assert one_scores["heading_recall"] == pytest.approx(0.5)


class _FailingParser:
    name = "failing"
    suffixes = frozenset({".txt"})

    def parse(self, path):
        raise ParseError("parse_failed")


def test_failed_parse_scores_zero_and_is_counted(tmp_path):
    truth = tmp_path / "t.md"
    truth.write_text("# Giriş\nmetin", encoding="utf-8")
    source = tmp_path / "t.txt"
    source.write_text("# Giriş\nmetin", encoding="utf-8")
    scores = parser_scores(_FailingParser(), [(source, truth)])
    assert scores["failed"] == 1
    assert scores["word_f1"] == pytest.approx(0.0)
    assert scores["heading_recall"] == pytest.approx(0.0)


def test_parser_scores_rejects_an_empty_pair_list():
    with pytest.raises(ValueError):
        parser_scores(TextParser(), [])


def test_docling_rejects_unsupported_suffix_before_converting(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("metin", encoding="utf-8")
    with pytest.raises(ParseError) as info:
        DoclingParser(max_pages=10).parse(path)
    assert info.value.code == "unsupported_type"


def test_docling_conversion_error_becomes_parse_failed(tmp_path, monkeypatch):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"not a pdf")

    class _BrokenConverter:
        def convert(self, _source, **_options):
            raise RuntimeError("conversion failed")

    parser = DoclingParser(max_pages=10)
    monkeypatch.setattr(parser, "_get_converter", lambda: _BrokenConverter())
    with pytest.raises(ParseError) as info:
        parser.parse(path)
    assert info.value.code == "parse_failed"


@pytest.mark.model
def test_docling_extracts_text_from_a_text_pdf(tmp_path):
    path = write_pdf(tmp_path / "a.pdf", [[("p", "Sipariş modülü güncellendi")]])
    assert "güncellendi" in DoclingParser(max_pages=10).parse(path)
