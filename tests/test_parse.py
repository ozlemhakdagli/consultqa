import fitz
import pytest

from docrag.ingest.parse import ParseError, PyMuPDFParser, TextParser, get_parser


def test_text_parser_keeps_turkish_characters(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Sipariş modülü İstanbul ığüşöç", encoding="utf-8")
    assert "Sipariş" in TextParser().parse(path)


def test_pdf_text_is_extracted(tmp_path):
    path = tmp_path / "a.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Siparis modulu guncellendi")
    doc.save(path)
    assert "guncellendi" in PyMuPDFParser(max_pages=10).parse(path)


# [R3] A corrupt PDF raises a coded error, never a bare exception.
def test_corrupt_pdf_raises_parse_failed(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(ParseError) as info:
        PyMuPDFParser(max_pages=10).parse(path)
    assert info.value.code == "parse_failed"


def test_page_limit_is_enforced(tmp_path):
    path = tmp_path / "two.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    doc.save(path)
    with pytest.raises(ParseError) as info:
        PyMuPDFParser(max_pages=1).parse(path)
    assert info.value.code == "too_many_pages"


def test_get_parser_rejects_unknown_names():
    with pytest.raises(ValueError):
        get_parser("nope", max_pages=1)
