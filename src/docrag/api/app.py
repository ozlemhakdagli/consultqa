"""FastAPI application factory for the docrag API."""

import logging
import re
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from docrag.api.routes import build_router, upload_limit_bytes
from docrag.api.services import Services, build_services, load_in_background
from docrag.config import load_settings

logger = logging.getLogger(__name__)

# The page lives in the repository root; the image sets DOCRAG_FRONTEND_DIR instead.
DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[3] / "frontend"
PAGE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    # Static files carry old modification times, so a browser could otherwise keep a stale page.
    "Cache-Control": "no-cache",
}
_UPLOAD_PATH = re.compile(r"^/api/collections/[^/]+/documents$")


class FrontendFiles(StaticFiles):
    """The page's static files, sent with security and revalidation headers (API routes are not)."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers.update(PAGE_HEADERS)
        return response


def _error(status_code: int, code: str) -> JSONResponse:
    """Return an error response whose body is the single error code."""
    return JSONResponse(status_code=status_code, content={"detail": code})


class DeclaredLengthLimit:
    """Refuse an upload whose Content-Length header is above the limit, before its body is read.

    FastAPI parses a form body before any route code runs, so the check has to sit in front of
    the application. A body with no usable length header is left to the streaming check in the
    upload route.
    """

    def __init__(self, app: ASGIApp, limit_bytes: int) -> None:
        self.app = app
        self.limit_bytes = limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and _UPLOAD_PATH.match(scope["path"])
        ):
            declared = _declared_length(scope)
            if declared is not None and declared > self.limit_bytes:
                await _error(413, "file_too_large")(scope, receive, send)
                return
        await self.app(scope, receive, send)


def _declared_length(scope: Scope) -> int | None:
    """The Content-Length of a request as an integer, or None when absent or not a number."""
    for name, value in scope["headers"]:
        if name == b"content-length":
            text = value.decode("latin-1").strip()
            return int(text) if text.isdigit() else None
    return None


def create_app(services: Services | None = None) -> FastAPI:
    """Build the API around ``services``. By default they are built from ``DOCRAG_*`` settings."""
    if services is None:
        services = build_services(load_settings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        """Load the models in a background thread while the server runs."""
        load_in_background(services)
        yield

    app = FastAPI(lifespan=lifespan)
    app.add_middleware(DeclaredLengthLimit, limit_bytes=upload_limit_bytes(services))
    semaphore = threading.BoundedSemaphore(1)
    app.state.inference_semaphore = semaphore
    app.include_router(build_router(services, semaphore))
    # Mounted after the API router, so /api routes take precedence over the page.
    frontend_dir = services.settings.frontend_dir or DEFAULT_FRONTEND_DIR
    if frontend_dir.is_dir():
        app.mount("/", FrontendFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        logger.warning(
            "frontend folder %s not found; serving the API only (set DOCRAG_FRONTEND_DIR)",
            frontend_dir,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, __: RequestValidationError) -> JSONResponse:
        """Report every request validation failure with one error code."""
        return _error(422, "validation_error")

    @app.exception_handler(StarletteHTTPException)
    async def http_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Report HTTP errors with a snake_case code instead of the reason phrase."""
        detail = exc.detail
        try:
            phrase = HTTPStatus(exc.status_code).phrase
        except ValueError:
            phrase = None
        if isinstance(detail, str) and detail == phrase:
            detail = detail.lower().replace(" ", "_")
        return JSONResponse(status_code=exc.status_code, content={"detail": detail})

    @app.exception_handler(ConnectionError)
    async def unreachable_handler(_: Request, __: ConnectionError) -> JSONResponse:
        """A vector store that cannot be reached is an outage, not a bug: answer 503 and retry."""
        return _error(503, "vector_store_unavailable")

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, __: Exception) -> JSONResponse:
        """Report unexpected failures without leaking details."""
        return _error(500, "internal_error")

    return app
