"""Ingestion: parse, chunk, embed and index one uploaded file, rolling back on failure.

Ingestion makes no LLM calls and stores no evidence graph: a graph preset builds it from the chunks
when it first needs it. Each stage is written to the job row, so ``GET /jobs/{job_id}`` can report
progress. A failed job leaves no document row and no vector behind.
"""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from consultqa.ingest.chunk import chunk_markdown, chunk_pages
from consultqa.ingest.parse import ParseError, Parser
from consultqa.retrieve.dense import DenseBackend, Encoder
from consultqa.store.originals import OriginalFiles
from consultqa.store.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)


def ingest_file(
    *,
    store: SqliteStore,
    parser: Parser,
    encoder: Encoder,
    dense: DenseBackend,
    job_id: str,
    collection_id: str,
    doc_id: str,
    path: Path,
    filename: str,
    max_tokens: int,
    count_tokens: Callable[[str], int],
    originals: OriginalFiles,
) -> bool:
    """Index ``path`` as document ``doc_id``. The job ends in state ``done`` or ``failed``.

    ``path`` is the staged copy, whose name means nothing to the user; ``filename`` is the name
    the user uploaded and is what the document is listed under. Identical content already in the
    collection ends the job as ``done`` without a new document. Text with no chunks (an empty
    file, or a PDF without text) ends the job as ``failed`` with ``no_text``. Neither of those
    keeps a copy of the file.

    A PDF is chunked page by page, so its chunks carry page numbers and the document records its
    page count. Other files have no pages. Once the vectors are written, the file is copied into
    ``originals`` under ``doc_id``; a failure after that removes the copy.

    Returns True if the job wrote chunks or vectors, which makes the collection's retrieval state
    stale, and False if it wrote nothing. A job that failed after it started writing returns True.
    """
    vector_ids: list[str] = []
    document_written = False
    original_saved = False
    wrote = False
    try:
        store.set_job(job_id, "parsing")
        try:
            pages = parser.parse_pages(path)
        except ParseError as exc:
            store.set_job(job_id, "failed", exc.code)
            return False
        is_pdf = path.suffix.lower() == ".pdf"
        text = "\n\n".join(pages)
        # Blank pages add no content, so they are left out of the hash: a whole-document export of
        # the same text has none and must be recognised as the same document.
        content = "\n\n".join(page for page in pages if page.strip())
        sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = store.find_document_by_hash(collection_id, sha)
        if existing is not None:
            store.set_job_document(job_id, existing)
            store.set_job(job_id, "done")
            return False
        if is_pdf:
            chunks = chunk_pages(doc_id, pages, max_tokens=max_tokens, count_tokens=count_tokens)
        else:
            chunks = chunk_markdown(doc_id, text, max_tokens=max_tokens, count_tokens=count_tokens)
        if not chunks:
            store.set_job(job_id, "failed", "no_text")
            return False
        vector_ids = [chunk.chunk_id for chunk in chunks]
        store.set_job(job_id, "embedding")
        vectors = encoder.encode_passages([chunk.text for chunk in chunks])
        wrote = True
        dense.upsert(vector_ids, vectors)
        original_saved = True
        originals.save(doc_id, path)
        store.add_document(
            collection_id,
            doc_id,
            sha,
            filename,
            chunks,
            page_count=len(pages) if is_pdf else None,
            has_original=True,
        )
        document_written = True
        store.set_job(job_id, "done")
        return True
    except Exception:
        logger.exception("ingestion job %s failed", job_id)
        if document_written:
            store.delete_document(collection_id, doc_id)
        if vector_ids:
            dense.delete(vector_ids)
        store.set_job(job_id, "failed", "internal_error")
        if original_saved:
            try:
                originals.delete(doc_id)
            except OSError:
                logger.warning(
                    "could not remove the original of document %s", doc_id, exc_info=True
                )
        return wrote


def delete_document(
    *,
    store: SqliteStore,
    dense: DenseBackend,
    collection_id: str,
    doc_id: str,
    originals: OriginalFiles,
) -> bool:
    """Delete a document with its vectors, its chunks and its kept original.

    Returns False if the document does not exist in this collection, and then keeps the original.
    """
    vector_ids = store.document_chunk_ids(collection_id, doc_id)
    if vector_ids:
        dense.delete(vector_ids)
    deleted = store.delete_document(collection_id, doc_id)
    if deleted:
        originals.delete(doc_id)
    return deleted
