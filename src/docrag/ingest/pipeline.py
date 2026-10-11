"""Ingestion: parse, chunk, embed and index one uploaded file, rolling back on failure.

Ingestion makes no LLM calls. Each stage is written to the job row, so ``GET /jobs/{job_id}``
can report progress. A failed job leaves no document row and no vector behind.
"""

import hashlib
import logging
from collections.abc import Callable
from pathlib import Path

from docrag.graph.build import build_graph
from docrag.ingest.chunk import chunk_markdown
from docrag.ingest.parse import ParseError, Parser
from docrag.retrieve.dense import DenseBackend, Encoder
from docrag.store.sqlite_store import SqliteStore

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
    max_tokens: int,
    count_tokens: Callable[[str], int],
) -> None:
    """Index ``path`` as document ``doc_id``. The job ends in state ``done`` or ``failed``.

    Identical content already in the collection ends the job as ``done`` without a new document.
    """
    vector_ids: list[str] = []
    document_written = False
    try:
        store.set_job(job_id, "parsing")
        try:
            text = parser.parse(path)
        except ParseError as exc:
            store.set_job(job_id, "failed", exc.code)
            return
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        existing = store.find_document_by_hash(collection_id, sha)
        if existing is not None:
            store.set_job_document(job_id, existing)
            store.set_job(job_id, "done")
            return
        chunks = chunk_markdown(doc_id, text, max_tokens=max_tokens, count_tokens=count_tokens)
        vector_ids = [chunk.chunk_id for chunk in chunks]
        store.set_job(job_id, "embedding")
        vectors = encoder.encode_passages([chunk.text for chunk in chunks])
        dense.upsert(vector_ids, vectors)
        store.add_document(collection_id, doc_id, sha, path.name, chunks)
        document_written = True
        store.set_job(job_id, "graph")
        _save_graph(store, collection_id)
        store.set_job(job_id, "done")
    except Exception:
        logger.exception("ingestion job %s failed", job_id)
        if document_written:
            store.delete_document(collection_id, doc_id)
        if vector_ids:
            dense.delete(vector_ids)
        store.set_job(job_id, "failed", "internal_error")


def delete_document(
    *, store: SqliteStore, dense: DenseBackend, collection_id: str, doc_id: str
) -> bool:
    """Delete a document with its vectors and chunks, then rebuild the collection's graph.

    Returns False if the document does not exist.
    """
    vector_ids = store.document_chunk_ids(collection_id, doc_id)
    if vector_ids:
        dense.delete(vector_ids)
    deleted = store.delete_document(collection_id, doc_id)
    _save_graph(store, collection_id)
    return deleted


def _save_graph(store: SqliteStore, collection_id: str) -> None:
    """Store the evidence graph of the collection's current chunks, empty if none remain."""
    store.save_graph(collection_id, build_graph(store.list_chunks(collection_id)).to_bytes())
