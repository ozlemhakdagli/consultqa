import re
from types import SimpleNamespace

import pytest
import torch
from pdf_fixtures import write_pdf

from consultqa.ingest.parse import DoclingParser, DocumentParser, ParseError, TextParser, get_parser

TURKISH_SENTENCE = "Ölçü birimi kilogram veya litre olarak seçilir."


class _FakeConverter:
    """Stands in for Docling's DocumentConverter. Like Docling, it sets torch to 4 threads."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    def convert(self, source, **kwargs):
        from docling.datamodel.base_models import ConversionStatus

        torch.set_num_threads(4)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            input=SimpleNamespace(page_count=1),
            status=ConversionStatus.SUCCESS,
            document=SimpleNamespace(export_to_markdown=lambda: "# Başlık\nmetin"),
        )


@pytest.fixture
def eight_torch_threads():
    """Run the test with torch at 8 threads, then put the process-wide count back."""
    original = torch.get_num_threads()
    torch.set_num_threads(8)
    yield
    torch.set_num_threads(original)


def _pdf_parser_with(fake, monkeypatch):
    parser = DoclingParser(max_pages=10)
    monkeypatch.setattr(parser, "_get_converter", lambda: fake)
    return parser


# O1: Docling's 4 threads last only for its own conversion; the caller's count comes back.
def test_parse_restores_torch_threads_after_docling_converts(
    tmp_path, monkeypatch, eight_torch_threads
):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"fake pdf")
    parser = _pdf_parser_with(_FakeConverter(), monkeypatch)
    before = torch.get_num_threads()
    assert parser.parse(path) == "# Başlık\nmetin"
    assert torch.get_num_threads() == before


def test_parse_restores_torch_threads_when_conversion_raises(
    tmp_path, monkeypatch, eight_torch_threads
):
    path = tmp_path / "a.pdf"
    path.write_bytes(b"fake pdf")
    parser = _pdf_parser_with(_FakeConverter(error=RuntimeError("boom")), monkeypatch)
    before = torch.get_num_threads()
    with pytest.raises(ParseError) as info:
        parser.parse(path)
    assert info.value.code == "parse_failed"
    assert torch.get_num_threads() == before


class _WarmConverter:
    """Stands in for Docling's converter for ``warm_up``. Like Docling, it sets torch to 4 threads
    while it builds a pipeline, and it records each format it was asked for."""

    def __init__(self) -> None:
        self.formats: list[object] = []

    def initialize_pipeline(self, pipeline_format) -> None:
        torch.set_num_threads(4)
        self.formats.append(pipeline_format)


# O5: warm_up builds the PDF pipeline once, and gives back the caller's torch thread count.
def test_warm_up_builds_the_pdf_pipeline_once(monkeypatch, eight_torch_threads):
    from docling.datamodel.base_models import InputFormat

    fake = _WarmConverter()
    parser = _pdf_parser_with(fake, monkeypatch)
    parser.warm_up()
    parser.warm_up()
    assert fake.formats == [InputFormat.PDF]


def test_warm_up_restores_torch_threads(monkeypatch, eight_torch_threads):
    parser = _pdf_parser_with(_WarmConverter(), monkeypatch)
    before = torch.get_num_threads()
    parser.warm_up()
    assert torch.get_num_threads() == before


def test_failed_warm_up_raises_and_a_later_call_tries_again(monkeypatch):
    class Broken(_WarmConverter):
        def initialize_pipeline(self, pipeline_format) -> None:
            self.formats.append(pipeline_format)
            raise RuntimeError("models missing")

    fake = Broken()
    parser = _pdf_parser_with(fake, monkeypatch)
    with pytest.raises(RuntimeError):
        parser.warm_up()
    with pytest.raises(RuntimeError):
        parser.warm_up()
    assert len(fake.formats) == 2


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


def test_text_parser_parse_pages_is_one_page(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("Sipariş modülü", encoding="utf-8")
    assert TextParser().parse_pages(path) == ["Sipariş modülü"]


def test_markdown_parse_pages_is_one_page_without_docling(tmp_path):
    path = tmp_path / "n.md"
    path.write_text("# Giriş\nmetin", encoding="utf-8")
    assert DocumentParser(max_pages=10).parse_pages(path) == ["# Giriş\nmetin"]


@pytest.mark.model
def test_docling_per_page_matches_full_export(tmp_path):
    """Each page has a heading and two full sentences ending in periods, so no text runs across a
    page break. The per-page export then matches the real pages (Docling 2.137.0, pinned)."""
    words = ["zeytin", "kayısı", "nohut"]
    pages_blocks = [
        [
            ("h2", f"Bölüm {word}"),
            ("p", f"Bu sayfada {word} geçiyor. Cümle burada tamamen bitiyor."),
            ("p", f"Sayfanın ikinci paragrafı da {word} ile biter."),
        ]
        for word in words
    ]
    path = write_pdf(tmp_path / "three.pdf", pages_blocks)
    parser = DoclingParser(max_pages=10)
    pages = parser.parse_pages(path)
    assert len(pages) == 3
    for index, word in enumerate(words):
        assert word in pages[index]
        assert all(other not in pages[index] for other in words if other != word)
    full = parser.parse(path)
    assert sorted(full.split()) == sorted(" ".join(pages).split())


@pytest.mark.model
def test_docling_text_running_across_a_page_break_stays_on_its_first_page(tmp_path):
    """Characterization, not a wish: Docling 2.137.0 (pinned) merges one-word pages with no
    sentence end into one item, and the per-page export gives that item to the page it starts on.
    Each word still appears once, in order. This is the accepted cost in spec section 4."""
    words = ["zeytin", "kayısı", "nohut"]
    path = write_pdf(tmp_path / "three.pdf", [[("p", word)] for word in words])
    pages = DoclingParser(max_pages=10).parse_pages(path)
    tokens = " ".join(pages).split()
    positions = [tokens.index(word) for word in words]
    assert positions == sorted(positions)
    assert words[0] in pages[0]
    for word in words:
        assert sum(word in page.split() for page in pages) == 1
