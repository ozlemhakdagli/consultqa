"""Ingestion: parse, chunk, embed and index one uploaded file, rolling back on failure.

Ingestion makes no LLM calls and stores no evidence graph: a graph preset builds it from the chunks
when it first needs it. Each stage is written to the job row, so ``GET /jobs/{job_id}`` can report
progress. A failed job leaves no document row and no vector behind.
"""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from consultqa.ingest.chunk import chunk_markdown
from consultqa.ingest.parse import ParseError, Parser
from consultqa.retrieve.dense import DenseBackend, Encoder
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
) -> bool:
    """Index ``path`` as document ``doc_id``. The job ends in state ``done`` or ``failed``.

    ``path`` is the staged copy, whose name means nothing to the user; ``filename`` is the name
    the user uploaded and is what the document is listed under. Identical content already in the
    collection ends the job as ``done`` without a new document. Text with no chunks (an empty
    file, or a PDF without text) ends the job as ``failed`` with ``no_text``.

    Returns True if the job wrote chunks or vectors, which makes the collection's retrieval state
    stale, and False if it wrote nothing. A job that failed after it started writing returns True.
    """
    vector_ids: list[str] = []
    document_written = False
    wrote = False
    try:
        store.set_job(job_id, "parsing")
        try:
            text = parser.parse(path)
        except ParseError as exc:
            store.set_job(job_id, "failed", exc.code)
            return False
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = store.find_document_by_hash(collection_id, sha)
        if existing is not None:
            store.set_job_document(job_id, existing)
            store.set_job(job_id, "done")
            return False
        chunks = chunk_markdown(doc_id, text, max_tokens=max_tokens, count_tokens=count_tokens)
        if not chunks:
            store.set_job(job_id, "failed", "no_text")
            return False
        vector_ids = [chunk.chunk_id for chunk in chunks]
        store.set_job(job_id, "embedding")
        vectors = encoder.encode_passages([chunk.text for chunk in chunks])
        wrote = True
        dense.upsert(vector_ids, vectors)
        store.add_document(collection_id, doc_id, sha, filename, chunks)
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
        return wrote


def delete_document(
    *, store: SqliteStore, dense: DenseBackend, collection_id: str, doc_id: str
) -> bool:
    """Delete a document with its vectors and chunks.

    Returns False if the document does not exist.
    """
    vector_ids = store.document_chunk_ids(collection_id, doc_id)
    if vector_ids:
        dense.delete(vector_ids)
    return store.delete_document(collection_id, doc_id)
