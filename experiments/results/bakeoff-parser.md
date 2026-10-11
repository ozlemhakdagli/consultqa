# Parser bake-off: PyMuPDF4LLM and Docling

Run on 2026-10-11. Input: the three synthetic Turkish PDFs in `data/sample/pdf/`, written by `scripts/make_sample_pdfs.py`. Ground truth: the Markdown file beside each PDF. Scored with `docrag.eval.bakeoff.parser_scores` for `PyMuPDFParser(max_pages=10)` and `DoclingParser()`, on every pdf/md pair in that folder.

**Sample size: 3 files.** Every number here is anecdotal (Global Constraints label slices with n <= 20 as anecdotal). No interval is reported.

## Summary

| Parser | Files | Failed | Mean word F1 | Mean heading recall | Mean seconds per file |
|---|---|---|---|---|---|
| pymupdf4llm | 3 | 0 | 1.000 | 1.000 | 0.28 |
| docling | 3 | 0 | 1.000 | 1.000 | 3.87 |

## Per file

| Parser | File | Failed | Word F1 | Heading recall | Seconds |
|---|---|---|---|---|---|
| pymupdf4llm | invoice_notes.pdf | no | 1.000 | 1.000 | 0.55 |
| pymupdf4llm | order_guide.pdf | no | 1.000 | 1.000 | 0.15 |
| pymupdf4llm | stock_report.pdf | no | 1.000 | 1.000 | 0.14 |
| docling | invoice_notes.pdf | no | 1.000 | 1.000 | 6.84 |
| docling | order_guide.pdf | no | 1.000 | 1.000 | 2.57 |
| docling | stock_report.pdf | no | 1.000 | 1.000 | 2.21 |

## Decision

Rule (plan Task 27): highest mean word F1; ties go to the faster parser. Result: **pymupdf4llm** (mean word F1 1.000).

Both parsers scored 1.000 on both measures, so these three clean text-layer PDFs do not separate them. The result comes from the speed tie-break alone. After the first file, Docling took 2.21 to 2.57 seconds per file and pymupdf4llm took 0.14 to 0.15 seconds. Scanned pages, complex layouts and real documents were not tested, so this table does not show that Docling is worse on them.

The default parser is unchanged: `get_parser` still returns `pymupdf4llm`, and `DoclingParser` is not registered there. Changing the default waits for the owner to read this table, as the plan requires.

## Turkish OCR

The Turkish OCR claim is checked at engine level only (`docs/verification.md`, item 4). End-to-end Turkish OCR was not run. These PDFs have a text layer, so OCR does not decide any score here. Docling's OCR settings were left at their defaults.

## Environment

CPU only. `CUDA_VISIBLE_DEVICES` was empty for the run, and `DoclingParser` sets the accelerator to CPU. The first Docling call includes model loading, so the first file's seconds (6.84 in this run) are far above the rest, and they drive the Docling mean. The first run, which also downloaded the models, took 97.33 seconds for that file.

Docling downloaded its models on first use, once, with network access outside pytest. The Hugging Face cache holds `docling-project/docling-layout-heron` at revision `8f39ad3c0b4c58e9c2d2c84a38465abf757272d8` and `docling-project/docling-models` at revision `fc0f2d45e2218ea24bce5045f58a389aed16dc23`. The model-marked test `tests/test_bakeoff.py::test_docling_extracts_text_from_a_text_pdf` passes on CPU from this cache.

- python: Python 3.11.17
- pymupdf: 1.28.2
- pymupdf4llm: 1.28.2
- docling: 2.137.0 (pyproject extra `docling`)
- docling-core: 2.101.1
