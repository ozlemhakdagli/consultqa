"""Turn monthly update-report PDFs into the structured JSON used by retrieval.

Method (see docs/paper.pdf, section 2.1.2):
1. Extract the text of every page with PyMuPDF.
2. Read the version from the "update-report Versiyon: V..." line.
3. Collect the numbered items under the "... Geliştirmeleri" headings.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pymupdf

from hybrid_qa.config import RAW_PDF_DIR

VERSION_PATTERN = re.compile(r"\S+ Versiyon:\s*(V[\d.]+)")
ITEM_PATTERN = re.compile(r"^(\d+)\.\s*(.*)$")
SECTION_START_PATTERN = re.compile(r"Yenilikler|Geliştirmeleri|Yapılan Geliştirmeler")


def extract_text(pdf_path: Path) -> str:
    """Return the cleaned text of all pages of a PDF, joined in page order."""
    with pymupdf.open(pdf_path) as document:
        raw = "".join(page.get_text("text") for page in document)
    return _clean_text(raw)


def _clean_text(text: str) -> str:
    """Collapse runs of spaces and tabs and drop trailing blanks on each line.

    Line breaks are kept, because the item parser relies on them.
    """
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines())


def parse_document(text: str, doc_id: str) -> dict:
    """Build one document record from the extracted text of an update report."""
    version = _find_version(text)
    descriptions = _find_update_descriptions(text)
    return {
        "id": doc_id,
        "version_info": {
            "version": version,
            "date": datetime.now().isoformat(sep=" "),
        },
        "updates": [
            {"id": f"update_{number}", "description": description}
            for number, description in enumerate(descriptions, start=1)
        ],
    }


def build_dataset(pdf_dir: Path = RAW_PDF_DIR, output_path: Path | None = None) -> list[dict]:
    """Parse every PDF in ``pdf_dir`` (sorted by name) and optionally save the result."""
    pdf_paths = sorted(pdf_dir.glob("*.pdf"))
    dataset = [
        parse_document(extract_text(pdf_path), doc_id=f"document_{index}")
        for index, pdf_path in enumerate(pdf_paths, start=1)
    ]

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            json.dump(dataset, file, ensure_ascii=False, indent=2)

    return dataset


def _find_version(text: str) -> str:
    match = VERSION_PATTERN.search(text)
    if match is None:
        raise ValueError("Version line '<name> Versiyon: V...' not found")
    return match.group(1)


def _find_update_descriptions(text: str) -> list[str]:
    """Return the numbered items found under the update section headings."""
    descriptions: list[str] = []
    in_update_section = False
    current: list[str] | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if not in_update_section:
            in_update_section = bool(SECTION_START_PATTERN.search(line))
            continue

        if SECTION_START_PATTERN.search(line) and not ITEM_PATTERN.match(line):
            # Section heading between groups of items
            current = None
            continue

        item = ITEM_PATTERN.match(line)
        if item:
            current = [item.group(2)]
            descriptions.append(current)  # type: ignore[arg-type]
        elif current is not None:
            # Wrapped line of the current item
            current.append(line)

    return [" ".join(parts).strip() for parts in descriptions]
