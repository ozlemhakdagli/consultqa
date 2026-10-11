"""Write three synthetic Turkish PDFs and their Markdown ground truth for the parser bake-off.

Each PDF has headings, paragraphs and a ruled text table, and together they contain every
Turkish letter in ``TURKISH_LETTERS``. The content is written in this file. It is invented and
must not contain private material.

The PDFs embed a TrueType font, because the built-in PDF fonts cannot show İ, ı, Ş, ş, Ğ or ğ.
By default it is the Vera font that reportlab bundles, which has every Turkish letter. Set
``CONSULTQA_SAMPLE_FONT`` to another TTF with Turkish glyphs to use a different font.

Usage, from the repository root::

    python scripts/make_sample_pdfs.py
"""

import os
from pathlib import Path

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "sample" / "pdf"
BUNDLED_FONT = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"
TURKISH_LETTERS = "İıŞşĞğÇçÖöÜü"

PAGE_WIDTH = 595
PAGE_HEIGHT = 842
MARGIN = 56
FONT = "sample"
HEADING_SIZES = {"h1": 18, "h2": 14}
BODY_SIZE = 11
TABLE_SIZE = 10
ROW_HEIGHT = 20

# A block is ("h1" | "h2", text), ("p", [lines]) or ("table", [header cells], [[row cells]]).
DOCUMENTS: dict[str, tuple[str, list[tuple]]] = {
    "order_guide": (
        "Sipariş Kılavuzu",
        [
            ("h1", "Sipariş Kılavuzu"),
            (
                "p",
                [
                    "Bu kılavuz sipariş girişini, onayını ve iptalini anlatır.",
                    "Şubat ayında yapılan değişiklikler aşağıda özetlenmiştir.",
                ],
            ),
            ("h2", "Stok Girişi"),
            (
                "p",
                [
                    "Ürün kodu ve adet bilgisi sipariş formuna eksiksiz girilir.",
                    "Ölçü birimi kilogram veya litre olarak seçilir.",
                ],
            ),
            (
                "table",
                ["Kod", "Ürün", "Adet"],
                [["A-101", "Çiğ köfte", "12"], ["B-204", "Pirinç", "40"], ["C-330", "Üzüm", "7"]],
            ),
            ("h2", "Onay ve İptal"),
            (
                "p",
                [
                    "Onay yetkisi olan kullanıcı siparişi onaylar.",
                    "İptal edilen sipariş için gerekçe yazılır.",
                ],
            ),
        ],
    ),
    "stock_report": (
        "Stok Raporu",
        [
            ("h1", "Stok Raporu"),
            (
                "p",
                [
                    "Depo sayımı her ayın ilk haftasında tamamlanır.",
                    "Sayım farkları ayrı bir tabloda listelenir.",
                ],
            ),
            ("h2", "Depo Sayımı"),
            (
                "table",
                ["Depo", "Sayılan", "Fark"],
                [["Merkez", "350", "-4"], ["Güney Depo", "128", "0"], ["Işıklar", "76", "2"]],
            ),
            ("h2", "Notlar"),
            (
                "p",
                [
                    "Negatif fark değerleri iade bekleyen ürünleri gösterir.",
                    "Düzeltme kayıtları haftalık olarak İş birimine gönderilir.",
                ],
            ),
        ],
    ),
    "invoice_notes": (
        "Fatura Notları",
        [
            ("h1", "Fatura Notları"),
            ("h2", "Ödeme Koşulları"),
            (
                "p",
                [
                    "Vade tarihi fatura tarihinden itibaren otuz gündür.",
                    "Gecikme durumunda yalnızca hatırlatma yapılır.",
                ],
            ),
            (
                "table",
                ["Fatura No", "Tarih", "Tutar"],
                [
                    ["F-2026-001", "03.02.2026", "1.250,00"],
                    ["F-2026-002", "17.02.2026", "980,50"],
                    ["F-2026-003", "02.03.2026", "4.310,75"],
                ],
            ),
            ("h2", "Düzeltmeler"),
            (
                "p",
                [
                    "Fatura DOĞRULAMA adımında tutarlar kontrol edilir.",
                    "Hatalı tutarlar düzeltme faturasıyla kapatılır.",
                ],
            ),
        ],
    ),
}


def _find_font() -> Path:
    font = Path(os.environ.get("CONSULTQA_SAMPLE_FONT") or BUNDLED_FONT)
    if not font.is_file():
        raise SystemExit(f"font file not found: {font}; set CONSULTQA_SAMPLE_FONT")
    return font


def _flip(y: float) -> float:
    """Convert a distance from the top of the page into reportlab's bottom-up coordinate."""
    return PAGE_HEIGHT - y


def _draw_table(pdf: canvas.Canvas, top: float, header: list[str], rows: list[list[str]]) -> float:
    cells = [header, *rows]
    columns = len(header)
    width = (PAGE_WIDTH - 2 * MARGIN) / columns
    pdf.setFont(FONT, TABLE_SIZE)
    for row_index, row in enumerate(cells):
        baseline = top + row_index * ROW_HEIGHT + 14
        for column_index, cell in enumerate(row):
            x = MARGIN + column_index * width + 4
            pdf.drawString(x, _flip(baseline), cell)
    bottom = top + len(cells) * ROW_HEIGHT
    for row_index in range(len(cells) + 1):
        y = top + row_index * ROW_HEIGHT
        pdf.line(MARGIN, _flip(y), MARGIN + columns * width, _flip(y))
    for column_index in range(columns + 1):
        x = MARGIN + column_index * width
        pdf.line(x, _flip(top), x, _flip(bottom))
    return bottom


def _write_pdf(path: Path, title: str, blocks: list[tuple], font_file: Path) -> None:
    pdfmetrics.registerFont(TTFont(FONT, str(font_file)))
    pdf = canvas.Canvas(str(path), pagesize=(PAGE_WIDTH, PAGE_HEIGHT), pageCompression=1)
    pdf.setTitle(title)
    y = float(MARGIN)
    for block in blocks:
        kind = block[0]
        if kind in HEADING_SIZES:
            size = HEADING_SIZES[kind]
            y += size + 4
            pdf.setFont(FONT, size)
            pdf.drawString(MARGIN, _flip(y), block[1])
            y += 8
        elif kind == "p":
            pdf.setFont(FONT, BODY_SIZE)
            for line in block[1]:
                y += BODY_SIZE + 4
                pdf.drawString(MARGIN, _flip(y), line)
            y += 8
        elif kind == "table":
            y = _draw_table(pdf, y + 6, block[1], block[2]) + 12
        else:
            raise ValueError(f"unknown block kind: {kind}")
        if y > PAGE_HEIGHT - MARGIN:
            raise ValueError(f"{path.name} does not fit on one page")
    pdf.save()


def _markdown(blocks: list[tuple]) -> str:
    parts = []
    for block in blocks:
        kind = block[0]
        if kind == "h1":
            parts.append(f"# {block[1]}")
        elif kind == "h2":
            parts.append(f"## {block[1]}")
        elif kind == "p":
            parts.append(" ".join(block[1]))
        elif kind == "table":
            header, rows = block[1], block[2]
            lines = ["| " + " | ".join(header) + " |"]
            lines.append("| " + " | ".join("---" for _ in header) + " |")
            lines.extend("| " + " | ".join(row) + " |" for row in rows)
            parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def main() -> None:
    all_markdown = {stem: _markdown(blocks) for stem, (_, blocks) in DOCUMENTS.items()}
    joined = "".join(all_markdown.values())
    missing = [letter for letter in TURKISH_LETTERS if letter not in joined]
    if missing:
        raise SystemExit(f"sample content lacks Turkish letters: {missing}")

    font_file = _find_font()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for stem, (title, blocks) in DOCUMENTS.items():
        pdf_path = OUT_DIR / f"{stem}.pdf"
        md_path = OUT_DIR / f"{stem}.md"
        _write_pdf(pdf_path, title, blocks, font_file)
        md_path.write_text(all_markdown[stem], encoding="utf-8")
        print(f"wrote {pdf_path.relative_to(ROOT)} and {md_path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
