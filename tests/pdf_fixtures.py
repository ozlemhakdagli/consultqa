"""Write small text PDFs for the parser tests, with reportlab and the Vera font it bundles.

The PDFs are generated at test time and never committed: ``*.pdf`` is ignored, and the privacy
test forbids tracked PDFs. Vera has every Turkish letter, so no system font is needed.
"""

from pathlib import Path

import reportlab
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

_FONTS = Path(reportlab.__file__).resolve().parent / "fonts"
_REGULAR = "ConsultqaVera"
_BOLD = "ConsultqaVeraBold"
pdfmetrics.registerFont(TTFont(_REGULAR, str(_FONTS / "Vera.ttf")))
pdfmetrics.registerFont(TTFont(_BOLD, str(_FONTS / "VeraBd.ttf")))

_LEFT = 56
_TOP = A4[1] - 72

# A block is ("h1", text), ("h2", text), ("p", text) or ("table", [[cell, ...], ...]).
Block = tuple[str, object]


def _heading(pdf: canvas.Canvas, y: float, text: str, size: int) -> float:
    pdf.setFont(_BOLD, size)
    pdf.drawString(_LEFT, y, text)
    return y - size - 18


def _paragraph(pdf: canvas.Canvas, y: float, text: str) -> float:
    pdf.setFont(_REGULAR, 11)
    for line in text.split("\n"):
        pdf.drawString(_LEFT, y, line)
        y -= 16
    return y - 14


def _table(pdf: canvas.Canvas, y: float, rows: list[list[str]]) -> float:
    row_height = 20
    column_width = 300 / max(len(row) for row in rows)
    for row in rows:
        x = _LEFT
        for cell in row:
            pdf.rect(x, y - row_height, column_width, row_height, stroke=1, fill=0)
            pdf.setFont(_REGULAR, 10)
            pdf.drawString(x + 4, y - 14, cell)
            x += column_width
        y -= row_height
    return y - 18


def write_pdf(path: Path, pages: list[list[Block]]) -> Path:
    """Write one PDF page per list of blocks and return the path."""
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for blocks in pages:
        y = _TOP
        for kind, content in blocks:
            if kind == "h1":
                y = _heading(pdf, y, str(content), 18)
            elif kind == "h2":
                y = _heading(pdf, y, str(content), 14)
            elif kind == "p":
                y = _paragraph(pdf, y, str(content))
            elif kind == "table":
                y = _table(pdf, y, content)
            else:
                raise ValueError(f"unknown block kind: {kind}")
        pdf.showPage()
    pdf.save()
    return path
