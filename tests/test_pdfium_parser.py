import pytest
from pdf_fixtures import write_pdf

from consultqa.ingest.parse import ParseError, get_parser
from consultqa.ingest.pdfium import PdfiumParser


@pytest.fixture
def three_pages(tmp_path):
    """Page 2 is blank, so later pages must keep their true numbers."""
    return write_pdf(
        tmp_path / "three.pdf",
        [
            [("h1", "Alpha heading"), ("p", "alpha one")],
            [],
            [("p", "gamma three")],
        ],
    )


def test_parse_pages_gives_one_string_per_page(three_pages):
    pages = PdfiumParser(max_pages=10).parse_pages(three_pages)
    assert len(pages) == 3
    assert "alpha one" in pages[0]
    assert pages[1].strip() == ""
    assert "gamma three" in pages[2]


def test_parse_joins_the_pages_with_blank_lines(three_pages):
    parser = PdfiumParser(max_pages=10)
    assert parser.parse(three_pages) == "\n\n".join(parser.parse_pages(three_pages))


def test_too_many_pages(three_pages):
    with pytest.raises(ParseError) as info:
        PdfiumParser(max_pages=2).parse_pages(three_pages)
    assert info.value.code == "too_many_pages"


def test_garbage_pdf_is_parse_failed(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ParseError) as info:
        PdfiumParser(max_pages=10).parse_pages(path)
    assert info.value.code == "parse_failed"


def test_text_file_is_one_page(tmp_path):
    path = tmp_path / "n.md"
    path.write_text("# Giriş\nmetin", encoding="utf-8")
    assert PdfiumParser(max_pages=10).parse_pages(path) == ["# Giriş\nmetin"]


def test_unsupported_type_is_rejected(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"not read")
    with pytest.raises(ParseError) as info:
        PdfiumParser(max_pages=10).parse_pages(path)
    assert info.value.code == "unsupported_type"


def test_warm_up_does_nothing():
    PdfiumParser(max_pages=10).warm_up()


def test_get_parser_pdfium(three_pages):
    parser = get_parser("pdfium", max_pages=10, artifacts_path=None)
    assert isinstance(parser, PdfiumParser)
    assert parser.name == "pdfium"
    assert parser.suffixes == frozenset({".pdf", ".txt", ".md"})
    assert len(parser.parse_pages(three_pages)) == 3
