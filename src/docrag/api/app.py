"""FastAPI application factory for the docrag API."""

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

from docrag.api.routes import build_router
from docrag.api.services import Services, build_services, load_in_background
from docrag.config import load_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _error(status_code: int, code: str) -> JSONResponse:
    """Return an error response whose body is the single error code."""
    return JSONResponse(status_code=status_code, content={"detail": code})


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
    semaphore = threading.BoundedSemaphore(1)
    app.state.inference_semaphore = semaphore
    app.include_router(build_router(services, semaphore))
    # Mounted after the API router, so /api routes take precedence over the page.
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

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

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, __: Exception) -> JSONResponse:
        """Report unexpected failures without leaking details."""
        return _error(500, "internal_error")

    return app
