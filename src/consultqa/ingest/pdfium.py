"""A text-layer PDF parser with pypdfium2, for files whose text is already selectable.

It reads the text each page holds and loads no layout or table model, so it is fast and needs no
downloaded models. It finds no headings and no tables: the text comes out as plain paragraphs.
Text and Markdown files are read as UTF-8, as in ``TextParser``.
"""

from pathlib import Path

from consultqa.ingest.parse import ParseError, TextParser, _check_suffix


class PdfiumParser:
    """PDF text read page by page with pypdfium2, and text files read as UTF-8."""

    name = "pdfium"
    suffixes = frozenset({".pdf", ".txt", ".md"})

    def __init__(self, max_pages: int) -> None:
        self.max_pages = max_pages
        self._text = TextParser()

    def warm_up(self) -> None:
        """Nothing to load: pypdfium2 needs no model."""

    def parse(self, path: Path) -> str:
        return "\n\n".join(self.parse_pages(path))

    def parse_pages(self, path: Path) -> list[str]:
        _check_suffix(path, self.suffixes)
        if path.suffix.lower() != ".pdf":
            return self._text.parse_pages(path)
        import pypdfium2 as pdfium

        try:
            document = pdfium.PdfDocument(str(path))
        except Exception as exc:
            raise ParseError("parse_failed") from exc
        try:
            count = len(document)
            if count > self.max_pages:
                raise ParseError("too_many_pages")
            return [self._page_text(document, index) for index in range(count)]
        finally:
            document.close()

    @staticmethod
    def _page_text(document, index: int) -> str:
        try:
            page = document[index]
            try:
                textpage = page.get_textpage()
                try:
                    return textpage.get_text_bounded()
                finally:
                    textpage.close()
            finally:
                page.close()
        except Exception as exc:
            raise ParseError("parse_failed") from exc
