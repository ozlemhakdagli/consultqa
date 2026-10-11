"""Routes under ``/api``: collections, documents and jobs, questions and passage search.

Inference calls (ask and search) run under one semaphore: a call that finds it taken gets
``429 busy``, and any call made before the models have loaded gets ``503 not_ready``.
"""

import logging
import tempfile
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, BinaryIO, TypeVar

from fastapi import APIRouter, File, HTTPException, Response, UploadFile
from fastapi.responses import JSONResponse

from consultqa.api.schemas import (
    AskRequest,
    AskResponse,
    Capabilities,
    Citation,
    CreateCollection,
    PresetInfo,
    SearchRequest,
    SearchResponse,
    TraceItem,
)
from consultqa.api.services import (
    DEFAULT_PRESET,
    PAPER_PRESET,
    Answer,
    LLMFailed,
    Services,
)
from consultqa.config import PRESETS, PipelineConfig
from consultqa.ingest.pipeline import delete_document, ingest_file
from consultqa.models import Chunk
from consultqa.retrieve.pipeline import TraceEntry
from consultqa.store.sqlite_store import CollectionExists

logger = logging.getLogger(__name__)

_READ_BYTES = 1024 * 1024
LLM_NOT_CONFIGURED = "llm_not_configured"
ResultT = TypeVar("ResultT")


def build_router(services: Services, semaphore: threading.BoundedSemaphore) -> APIRouter:
    """Return the ``/api`` router for ``services``, sharing ``semaphore`` for inference calls."""
    router = APIRouter(prefix="/api")

    def require_ready() -> None:
        """Refuse a call made before the models have loaded."""
        if not services.ready.is_set():
            raise HTTPException(status_code=503, detail="not_ready")

    def run_inference(call: Callable[[], ResultT]) -> ResultT:
        """Run one inference call under the semaphore, refusing when busy."""
        require_ready()
        if not semaphore.acquire(blocking=False):
            raise HTTPException(status_code=429, detail="busy")
        try:
            return call()
        finally:
            semaphore.release()

    def require_collection(cid: str) -> None:
        if services.store.get_collection(cid) is None:
            raise HTTPException(status_code=404, detail="collection_not_found")

    def llm_missing(cfg: PipelineConfig) -> bool:
        """True for a preset that needs an LLM when none is configured."""
        return cfg.reader == "llm" and services.llm is None

    def resolve_preset(name: str) -> PipelineConfig | None:
        """Return the pipeline of a preset, or None for the published method.

        Raises 422 for an unknown preset or for ``paper`` when it is not enabled, and 503 when
        an LLM preset has no LLM configured.
        """
        if name == PAPER_PRESET:
            if not services.paper_enabled:
                raise HTTPException(status_code=422, detail="preset_unavailable")
            return None
        cfg = PRESETS.get(name)
        if cfg is None:
            raise HTTPException(status_code=422, detail="unknown_preset")
        if llm_missing(cfg):
            raise HTTPException(status_code=503, detail="llm_unavailable")
        return cfg

    @router.get("/health")
    def health() -> dict[str, str]:
        """Report that the process is alive."""
        return {"status": "ok"}

    @router.get("/ready")
    def ready() -> dict[str, str]:
        """Report whether the models have finished loading."""
        if not services.ready.is_set():
            raise HTTPException(status_code=503, detail="not_ready")
        return {"status": "ready"}

    @router.get("/presets")
    def presets() -> list[str]:
        """List the preset names, with ``paper`` when the published method is enabled."""
        names = list(PRESETS)
        return [*names, PAPER_PRESET] if services.paper_enabled else names

    @router.get("/capabilities", response_model=Capabilities)
    def capabilities() -> Capabilities:
        """What the page may offer: readiness, upload limits and which methods can be used."""
        presets = [
            PresetInfo(
                name=name,
                available=not llm_missing(cfg),
                reason=LLM_NOT_CONFIGURED if llm_missing(cfg) else None,
                uses_llm=cfg.reader == "llm",
            )
            for name, cfg in PRESETS.items()
        ]
        if services.paper_enabled:
            presets.append(
                PresetInfo(name=PAPER_PRESET, available=True, reason=None, uses_llm=False)
            )
        return Capabilities(
            ready=services.ready.is_set(),
            llm_configured=services.llm is not None,
            max_upload_mb=services.settings.max_upload_mb,
            extensions=sorted(services.parser.suffixes),
            default_preset=DEFAULT_PRESET,
            presets=presets,
        )

    @router.post("/collections", status_code=201)
    def create_collection(body: CreateCollection) -> dict[str, str]:
        try:
            row = services.store.create_collection(body.name)
        except CollectionExists:
            raise HTTPException(status_code=409, detail="collection_exists") from None
        return {"id": row["id"], "name": row["name"]}

    @router.get("/collections")
    def list_collections() -> list[dict]:
        return services.store.list_collections()

    @router.post("/collections/{cid}/documents", status_code=202)
    def upload(cid: str, file: Annotated[UploadFile, File()]) -> dict[str, str]:
        """Accept an upload and start its ingestion job; the job reports the final state."""
        # Ingestion needs the models, so nothing is accepted before they are loaded.
        require_ready()
        require_collection(cid)
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in services.parser.suffixes:
            raise HTTPException(status_code=415, detail="unsupported_type")
        limit = upload_limit_bytes(services)
        # The job reads the staged file later, so the staging directory is removed by the job.
        staging = tempfile.TemporaryDirectory()
        try:
            # The staged name is random; the name the user chose is kept for display only.
            path = Path(staging.name) / f"{uuid.uuid4().hex}{suffix}"
            _save_limited(file.file, path, limit)
            document_id = uuid.uuid4().hex
            job_id = services.store.create_job(cid, document_id)
            services.jobs.submit(
                _ingest_job,
                services,
                cid,
                job_id,
                document_id,
                path,
                display_name(file.filename),
                staging,
            )
        except BaseException:
            staging.cleanup()
            raise
        return {"job_id": job_id, "document_id": document_id}

    @router.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, str | None]:
        job = services.store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job_not_found")
        return {"state": job["state"], "error": job["error"], "document_id": job["document_id"]}

    @router.get("/collections/{cid}/documents")
    def list_documents(cid: str) -> list[dict[str, str]]:
        require_collection(cid)
        return [
            {"id": doc["id"], "filename": doc["filename"], "created_at": doc["created_at"]}
            for doc in services.store.list_documents(cid)
        ]

    @router.delete("/collections/{cid}/documents/{doc_id}", status_code=204)
    def remove_document(cid: str, doc_id: str) -> Response:
        """Delete a document with its vectors, chunks and graph rows."""
        require_ready()
        require_collection(cid)
        deleted = delete_document(
            store=services.store, dense=services.dense(cid), collection_id=cid, doc_id=doc_id
        )
        services.invalidate(cid)
        if not deleted:
            raise HTTPException(status_code=404, detail="document_not_found")
        return Response(status_code=204)

    @router.post("/collections/{cid}/ask", response_model=AskResponse)
    def ask(cid: str, body: AskRequest) -> AskResponse | JSONResponse:
        """Answer a question. An LLM that fails returns 503 with the retrieval trace attached."""
        require_collection(cid)
        cfg = resolve_preset(body.preset)

        def call() -> AskResponse:
            started = time.perf_counter()
            if cfg is None:
                answer = services.ask_paper(cid, body.question)
            else:
                answer = services.ask(cid, cfg, body.question, body.k)
            return _ask_response(answer, body.preset, started)

        try:
            return run_inference(call)
        except LLMFailed as exc:
            trace = [_trace_item(entry).model_dump() for entry in exc.trace]
            return JSONResponse(
                status_code=503, content={"detail": "llm_unavailable", "trace": trace}
            )

    @router.post("/collections/{cid}/search", response_model=SearchResponse)
    def search(cid: str, body: SearchRequest) -> SearchResponse:
        """Return the best passages of the default pipeline, without answering."""
        require_collection(cid)
        cfg = PRESETS[DEFAULT_PRESET]

        def call() -> SearchResponse:
            started = time.perf_counter()
            entries = services.search(cid, cfg, body.query, body.k)
            return SearchResponse(
                hits=[_trace_item(entry) for entry in entries],
                preset=cfg.name,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        return run_inference(call)

    return router


def upload_limit_bytes(services: Services) -> int:
    """The largest accepted upload, in bytes."""
    return int(services.settings.max_upload_mb * 1024 * 1024)


def display_name(raw: str | None) -> str:
    """The name to show for an upload: its last path component, or ``upload`` if none is left.

    Both separators are treated as path separators, so a client cannot store a directory part.
    """
    name = Path((raw or "").replace("\\", "/")).name
    return name if name not in ("", ".", "..") else "upload"


def _ingest_job(
    services: Services,
    cid: str,
    job_id: str,
    document_id: str,
    path: Path,
    filename: str,
    staging: tempfile.TemporaryDirectory,
) -> None:
    """Run one ingestion job, then drop the cached retrieval state and the staged upload."""
    try:
        ingest_file(
            store=services.store,
            parser=services.parser,
            encoder=services.encoder,
            dense=services.dense(cid),
            job_id=job_id,
            collection_id=cid,
            doc_id=document_id,
            path=path,
            filename=filename,
            max_tokens=services.settings.chunk_max_tokens,
            count_tokens=services.count_tokens,
        )
    except Exception:
        logger.exception("ingestion job %s could not start", job_id)
        services.store.set_job(job_id, "failed", "internal_error")
    finally:
        services.invalidate(cid)
        staging.cleanup()


def _save_limited(source: BinaryIO, path: Path, limit: int) -> None:
    """Copy an upload to ``path`` in blocks. Stops with 413 once it exceeds ``limit`` bytes."""
    written = 0
    with path.open("wb") as target:
        while block := source.read(_READ_BYTES):
            written += len(block)
            if written > limit:
                raise HTTPException(status_code=413, detail="file_too_large")
            target.write(block)


def _ask_response(answer: Answer, preset: str, started: float) -> AskResponse:
    return AskResponse(
        answer=answer.text,
        citations=[_citation(number, chunk) for number, chunk in answer.cited],
        trace=[_trace_item(entry) for entry in answer.trace],
        preset=preset,
        latency_ms=(time.perf_counter() - started) * 1000,
    )


def _citation(number: int, chunk: Chunk) -> Citation:
    return Citation(
        number=number,
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        heading_path=list(chunk.heading_path),
        text=chunk.text,
    )


def _trace_item(entry: TraceEntry) -> TraceItem:
    return TraceItem(
        stage=entry.stage,
        chunk_id=entry.chunk_id,
        rank=entry.rank,
        score=entry.score,
        score_type=entry.score_type,
        channel=entry.channel,
    )
