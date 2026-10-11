"""Turn uploaded files into Markdown text.

Parsers raise ``ParseError`` with a stable code, and the ingestion job stores that code.
"""

import threading
from pathlib import Path
from typing import Any, Protocol


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

    def warm_up(self) -> None:
        """Load what the parser needs before its first file. Calling it again does nothing."""


def _check_suffix(path: Path, suffixes: frozenset[str]) -> None:
    if path.suffix.lower() not in suffixes:
        raise ParseError("unsupported_type")


class TextParser:
    """Plain text and Markdown, read as UTF-8."""

    name = "text"
    suffixes = frozenset({".txt", ".md"})

    def warm_up(self) -> None:
        """Nothing to load: text is read from the file."""

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError("parse_failed") from exc


class DoclingParser:
    """PDF, DOCX, PPTX and HTML through Docling, on the CPU.

    Docling is imported on first use, so importing this module loads no model. The converter is
    built once per parser and reused. A PDF with more than ``max_pages`` pages is rejected before
    any page is converted, and a failure of any other kind becomes ``parse_failed``.

    ``artifacts_path`` is the folder that holds the Docling models (``scripts/fetch_models.py``
    fills it). When it is None, Docling reads them from the Hugging Face cache instead.
    """

    name = "docling"
    suffixes = frozenset({".pdf", ".docx", ".pptx", ".html"})

    def __init__(self, max_pages: int, artifacts_path: Path | None = None) -> None:
        self.max_pages = max_pages
        self.artifacts_path = artifacts_path
        self._converter: Any = None
        self._warmed = False
        # The converter and torch's thread count are process-wide. A warm-up that runs while an
        # upload is parsed must not build a second converter or leave the thread count wrong.
        self._lock = threading.RLock()

    def _get_converter(self) -> Any:
        with self._lock:
            if self._converter is None:
                from docling.datamodel.accelerator_options import (
                    AcceleratorDevice,
                    AcceleratorOptions,
                )
                from docling.datamodel.base_models import InputFormat
                from docling.datamodel.pipeline_options import PdfPipelineOptions
                from docling.document_converter import DocumentConverter, PdfFormatOption

                pipeline = PdfPipelineOptions(
                    accelerator_options=AcceleratorOptions(device=AcceleratorDevice.CPU),
                    artifacts_path=self.artifacts_path,
                )
                self._converter = DocumentConverter(
                    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline)}
                )
            return self._converter

    def warm_up(self) -> None:
        """Build the converter and its PDF pipeline now, so the first PDF does not wait for them.

        Docling sets torch to its thread count while it builds the pipeline, so the caller's count
        is put back, as in ``parse``. A second call does nothing. A failure is raised and the
        pipeline is built by the first PDF instead.
        """
        import torch
        from docling.datamodel.base_models import InputFormat

        with self._lock:
            if self._warmed:
                return
            threads = torch.get_num_threads()
            try:
                self._get_converter().initialize_pipeline(InputFormat.PDF)
            finally:
                torch.set_num_threads(threads)
            self._warmed = True

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        import torch

        with self._lock:
            # Docling sets torch to its own thread count (4) for the whole process after the first
            # PDF. Keep the caller's count, so only the conversion runs at Docling's count.
            threads = torch.get_num_threads()
            try:
                from docling.datamodel.base_models import ConversionStatus

                # Docling checks the page count before it converts anything, and reports the count
                # on the input even when it rejects the file, so the limit is enforced here.
                result = self._get_converter().convert(
                    str(path), max_num_pages=self.max_pages, raises_on_error=False
                )
                pages = result.input.page_count
                converted = result.status in (
                    ConversionStatus.SUCCESS,
                    ConversionStatus.PARTIAL_SUCCESS,
                )
                markdown = result.document.export_to_markdown() if converted else None
            except Exception as exc:
                raise ParseError("parse_failed") from exc
            finally:
                torch.set_num_threads(threads)
        if pages > self.max_pages:
            raise ParseError("too_many_pages")
        if markdown is None:
            raise ParseError("parse_failed")
        return markdown


class DocumentParser:
    """The service parser: PDF through Docling, Text and Markdown read as UTF-8."""

    name = "docling"
    suffixes = frozenset({".pdf", ".txt", ".md"})

    def __init__(self, max_pages: int, artifacts_path: Path | None = None) -> None:
        self._pdf = DoclingParser(max_pages=max_pages, artifacts_path=artifacts_path)
        self._text = TextParser()

    def warm_up(self) -> None:
        self._pdf.warm_up()

    def parse(self, path: Path) -> str:
        _check_suffix(path, self.suffixes)
        if path.suffix.lower() == ".pdf":
            return self._pdf.parse(path)
        return self._text.parse(path)


def get_parser(name: str, *, max_pages: int, artifacts_path: Path | None = None) -> Parser:
    """Return the parser registered under ``name``. The only registered name is ``docling``."""
    if name == "docling":
        return DocumentParser(max_pages=max_pages, artifacts_path=artifacts_path)
    raise ValueError(f"unknown parser: {name!r}")
