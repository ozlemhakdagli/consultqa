"""Turn uploaded files into Markdown text.

Parsers raise ``ParseError`` with a stable code, and the ingestion job stores that code.
"""

from pathlib import Path
from typing import Any, Protocol

import fitz
import pymupdf4llm


class ParseError(Exception):
    """A document could not be parsed. ``code`` is one of the public parse error codes."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Parser(Protocol):
    """Reads one uploaded file and returns its text as Markdown."""

    name: str
    suffixes: frozenset[str]

    def parse(self, path: Path) -> str: ...


def _check_suffix(path: Path, suffixes: frozenset[str]) -> None:
    if path.suffix.lower() not in suffixes:
        raise ParseError("unsupported_type")


class TextParser:
    """Plain text and Markdown, read as UTF-8."""

    name = "text"
    suffixes = frozenset({".txt", ".md"})

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError("parse_failed") from exc


class PyMuPDFParser:
    """PDF text through pymupdf4llm. Text and Markdown files are read as UTF-8."""

    name = "pymupdf4llm"
    suffixes = frozenset({".pdf", ".txt", ".md"})

    def __init__(self, max_pages: int) -> None:
        self.max_pages = max_pages

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        if path.suffix.lower() != ".pdf":
            return TextParser().parse(path)
        if _page_count(path) > self.max_pages:
            raise ParseError("too_many_pages")
        try:
            return pymupdf4llm.to_markdown(str(path))
        except Exception as exc:
            raise ParseError("parse_failed") from exc


def _page_count(path: Path) -> int:
    """Return the page count of a readable, unencrypted PDF."""
    try:
        with fitz.open(str(path)) as doc:
            locked = doc.needs_pass
            pages = doc.page_count
    except Exception as exc:
        raise ParseError("parse_failed") from exc
    if locked:
        raise ParseError("parse_failed")
    return pages


class DoclingParser:
    """PDF, DOCX, PPTX and HTML through Docling, on the CPU.

    Docling is imported on first use, so the default install does not need it. The converter is
    built once per parser and reused. Any failure, including a missing install, becomes
    ``parse_failed``.
    """

    name = "docling"
    suffixes = frozenset({".pdf", ".docx", ".pptx", ".html"})

    def __init__(self) -> None:
        self._converter: Any = None

    def _get_converter(self) -> Any:
        if self._converter is None:
            from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            pipeline = PdfPipelineOptions(
                accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU)
            )
            self._converter = DocumentConverter(
                format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
            )
        return self._converter

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        try:
            result = self._get_converter().convert(str(path))
            return result.document.export_to_markdown()
        except Exception as exc:
            raise ParseError("parse_failed") from exc


def get_parser(name: str, *, max_pages: int) -> Parser:
    """Return the parser registered under ``name``."""
    if name == "pymupdf4llm":
        return PyMuPDFParser(max_pages=max_pages)
    raise ValueError(f"unknown parser: {name!r}")
