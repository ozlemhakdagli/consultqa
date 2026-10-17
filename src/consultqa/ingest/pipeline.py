"""Ingestion: parse, chunk, embed and index one uploaded file, rolling back on failure.

Ingestion makes no LLM calls and stores no evidence graph: a graph preset builds it from the chunks
when it first needs it. Each stage is written to the job row, so ``GET /jobs/{job_id}`` can report
progress. A failed job leaves no document row and no vector behind.
"""

import hashlib
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from consultqa.ingest.chunk import chunk_markdown, chunk_pages
from consultqa.ingest.parse import ParseError, Parser
from consultqa.models import Chunk
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
    collection ends the job as ``done`` without a new document. A legacy document (one uploaded
    before originals were kept, so ``has_original`` is false) of the same folder is replaced when
    it has the same content hash, or the same filename and no page count. The new vectors and
    original are saved first, then the legacy row is replaced in one transaction. Only after that
    are the old vectors removed, best effort. Text with no chunks (an empty file, or a PDF without
    text) ends the job as ``failed`` with ``no_text``. Neither of those keeps a copy of the file.

    A PDF is chunked page by page, so its chunks carry page numbers and the document records its
    page count. Other files have no pages. Once the vectors are written, the file is copied into
    ``originals`` under ``doc_id``; a failure after that removes the copy.

    Returns True if the job wrote chunks or vectors, which makes the collection's retrieval state
    stale, and False if it wrote nothing. A job that failed after it started writing returns True.
    A replacement writes the new document, so it returns True too.
    """
    vector_ids: list[str] = []
    document_written = False
    replace_committed = False
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
        folder = store.list_documents(collection_id)
        same = next((d for d in folder if d["has_original"] and d["content_sha256"] == sha), None)
        if same is not None:
            store.set_job_document(job_id, same["id"])
            store.set_job(job_id, "done")
            return False
        replaced = [d["id"] for d in folder if _is_legacy_copy(d, sha, filename)]
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
        page_count = len(pages) if is_pdf else None
        # The old chunk ids are read before a replace, which removes them with the rows.
        old_vectors = {
            old_id: store.document_chunk_ids(collection_id, old_id) for old_id in replaced
        }
        removed = _replace_matches(
            store,
            collection_id,
            replaced,
            doc_id,
            sha,
            filename,
            chunks,
            page_count=page_count,
        )
        if removed is None:
            store.add_document(
                collection_id,
                doc_id,
                sha,
                filename,
                chunks,
                page_count=page_count,
                has_original=True,
            )
        else:
            # The replace is the commit point: from here the new document is kept.
            replace_committed = True
            _drop_vectors(dense, [v for old_id in removed for v in old_vectors[old_id]])
        document_written = True
        store.set_job(job_id, "done")
        return True
    except Exception:
        logger.exception("ingestion job %s failed", job_id)
        if replace_committed:
            _finish_after_commit(store, job_id)
            return True
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


def _replace_matches(
    store: SqliteStore,
    collection_id: str,
    matches: list[str],
    doc_id: str,
    sha: str,
    filename: str,
    chunks: Sequence[Chunk],
    *,
    page_count: int | None,
) -> list[str] | None:
    """Replace the first match still stored, removing the other matches in the same transaction.

    A match deleted while the job ran is skipped and the next one is tried. Returns the matches
    the committed replace removed, or None if every match had vanished, in which case nothing was
    removed.
    """
    remaining = list(matches)
    while remaining:
        try:
            store.replace_document(
                collection_id,
                remaining[0],
                doc_id,
                sha,
                filename,
                chunks,
                page_count=page_count,
                has_original=True,
                also_delete=remaining[1:],
            )
        except LookupError:
            remaining.pop(0)
            continue
        return remaining
    return None


def _drop_vectors(dense: DenseBackend, vector_ids: list[str]) -> None:
    """Remove the vectors of replaced documents once their replacement is stored.

    Best effort: a failure is logged and does not fail the job. Leftover vectors are harmless,
    because retrieval ignores ids that have no chunk row.
    """
    if not vector_ids:
        return
    try:
        dense.delete(vector_ids)
    except Exception:
        logger.warning("could not remove the vectors of a replaced document", exc_info=True)


def _finish_after_commit(store: SqliteStore, job_id: str) -> None:
    """Mark a job whose replacement committed. The new document is not rolled back.

    The job is marked done; if that fails too it is marked failed, and if even that fails the
    failure is logged.
    """
    try:
        store.set_job(job_id, "done")
    except Exception:
        logger.exception("could not mark job %s done after its replacement", job_id)
        try:
            store.set_job(job_id, "failed", "internal_error")
        except Exception:
            logger.exception("could not mark job %s failed", job_id)


def _is_legacy_copy(document: dict, sha: str, filename: str) -> bool:
    """True if an upload of this content and name replaces ``document``.

    Only a document without an original can be replaced. Docling merges text across page breaks,
    so an old PDF can differ in hash from its new upload; the same name with no page count is
    then the same document.
    """
    if document["has_original"]:
        return False
    if document["content_sha256"] == sha:
        return True
    return document["filename"] == filename and document["page_count"] is None


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
