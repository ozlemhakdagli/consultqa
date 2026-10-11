import re

import pytest
from pdf_fixtures import write_pdf

from consultqa.ingest.parse import DocumentParser, ParseError, TextParser, get_parser

TURKISH_SENTENCE = "Ölçü birimi kilogram veya litre olarak seçilir."


def test_text_parser_keeps_turkish_characters(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Sipariş modülü İstanbul ığüşöç", encoding="utf-8")
    assert "Sipariş" in TextParser().parse(path)


def test_get_parser_returns_the_docling_parser():
    parser = get_parser("docling", max_pages=10)
    assert parser.name == "docling"
    assert parser.suffixes == frozenset({".pdf", ".txt", ".md"})


@pytest.mark.parametrize("name", ["nope", "pymupdf4llm", ""])
def test_get_parser_rejects_unknown_names(name):
    with pytest.raises(ValueError):
        get_parser(name, max_pages=1)


def test_text_and_markdown_are_read_without_docling(tmp_path):
    path = tmp_path / "n.md"
    path.write_text("# Giriş\nmetin", encoding="utf-8")
    assert DocumentParser(max_pages=10).parse(path) == "# Giriş\nmetin"


def test_word_documents_are_not_accepted(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"not read")
    with pytest.raises(ParseError) as info:
        DocumentParser(max_pages=10).parse(path)
    assert info.value.code == "unsupported_type"


# [R3] A corrupt PDF raises a coded error, never a bare exception.
def test_corrupt_pdf_raises_parse_failed(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ParseError) as info:
        DocumentParser(max_pages=10).parse(path)
    assert info.value.code == "parse_failed"


def test_page_limit_is_enforced(tmp_path):
    path = write_pdf(
        tmp_path / "three.pdf",
        [[("h1", "Birinci sayfa")], [("h1", "İkinci sayfa")], [("h1", "Üçüncü sayfa")]],
    )
    with pytest.raises(ParseError) as info:
        DocumentParser(max_pages=2).parse(path)
    assert info.value.code == "too_many_pages"


@pytest.mark.model
def test_pdf_with_two_headings_and_turkish_becomes_markdown(tmp_path):
    path = write_pdf(
        tmp_path / "a.pdf",
        [
            [
                ("h1", "Sipariş Kılavuzu"),
                ("p", TURKISH_SENTENCE),
                ("h2", "Stok Girişi"),
                ("p", "İ ı Ş ş Ğ ğ Ç ç Ö ö Ü ü"),
            ]
        ],
    )
    text = DocumentParser(max_pages=10).parse(path)
    assert TURKISH_SENTENCE in text
    assert re.search(r"^#+ Sipariş Kılavuzu$", text, flags=re.MULTILINE)
    assert re.search(r"^#+ Stok Girişi$", text, flags=re.MULTILINE)
