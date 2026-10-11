"""Fixtures for the browser tests: a stub-backend server and a headless Chrome."""

from __future__ import annotations

import importlib.util
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Browser, BrowserContext, Page, Playwright

# The browser tests need `pip install -e ".[e2e]"`; without Playwright they are not collected.
if importlib.util.find_spec("playwright") is None:
    collect_ignore_glob = ["test_*.py"]

ROOT = Path(__file__).resolve().parents[2]
IGNORED_CONSOLE_PREFIX = "Failed to load resource"
# The short job poll of the opt-in fixture, in milliseconds. The page default is 1000.
FAST_JOB_POLL_MS = 50
_JOB_POLL_LINE = re.compile(r"^export const JOB_POLL_MS = \d+;$", re.MULTILINE)


@pytest.fixture(scope="session")
def playwright_driver() -> Iterator[Playwright]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        yield driver


@pytest.fixture(scope="session")
def browser(playwright_driver: Playwright) -> Iterator[Browser]:
    from playwright.sync_api import Error as PlaywrightError

    launched = None
    for options in ({"channel": "chrome"}, {}):
        try:
            launched = playwright_driver.chromium.launch(**options)
            break
        except PlaywrightError:
            continue
    if launched is None:
        pytest.skip("no headless Chrome or Chromium is available")
    yield launched
    launched.close()


@contextmanager
def _running_server(driver: Playwright, state_dir: Path) -> Iterator[str]:
    """A stub-backend server on a free port with its own state directory, polled until ready.
    Readiness is polled through Playwright's HTTP client, because the repository's block_network
    fixture stops Python sockets from connecting."""
    from playwright.sync_api import Error as PlaywrightError

    state_dir.mkdir(parents=True, exist_ok=True)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {
        **os.environ,
        "CONSULTQA_BACKEND": "stub",
        "CONSULTQA_STATE_DIR": str(state_dir),
        "CONSULTQA_MAX_UPLOAD_MB": "1",
        "PYTHONPATH": str(ROOT / "src"),
        "HF_HUB_OFFLINE": "1",
    }
    log_path = state_dir / "server.log"
    command = [
        sys.executable, "-m", "uvicorn", "consultqa.api.app:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
    ]  # fmt: skip
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)  # noqa: S603
        url = f"http://127.0.0.1:{port}"
        client = driver.request.new_context()
        try:
            for _ in range(120):
                try:
                    if client.get(f"{url}/api/ready").status == 200:
                        break
                except PlaywrightError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError(f"server exited:\n{log_path.read_text()[-2000:]}")
                time.sleep(0.5)
            else:
                raise RuntimeError(f"server did not become ready:\n{log_path.read_text()[-2000:]}")
            yield url
        finally:
            client.dispose()
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture(scope="session")
def base_url(
    playwright_driver: Playwright, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[str]:
    """One stub-backend server shared by the tests of the session."""
    with _running_server(playwright_driver, tmp_path_factory.mktemp("consultqa-state")) as url:
        yield url


@pytest.fixture
def fresh_server(playwright_driver: Playwright, tmp_path: Path) -> Iterator[str]:
    """A stub-backend server with an empty state, for the first-visit tests."""
    with _running_server(playwright_driver, tmp_path / "state") as url:
        yield url


def _serve_fast_job_polling(context: BrowserContext) -> None:
    """Serve /js/config.js with a short JOB_POLL_MS to every page of this browser context.

    The module is the file the server serves (frontend/js/config.js); only the poll line changes.
    """
    source = (ROOT / "frontend" / "js" / "config.js").read_text(encoding="utf-8")
    fast, count = _JOB_POLL_LINE.subn(f"export const JOB_POLL_MS = {FAST_JOB_POLL_MS};", source)
    assert count == 1, "frontend/js/config.js must export JOB_POLL_MS exactly once"
    context.route(
        "**/js/config.js",
        lambda route: route.fulfill(status=200, content_type="text/javascript", body=fast),
    )


@pytest.fixture
def make_page(browser: Browser) -> Iterator[Callable[..., Page]]:
    """Open pages in fresh contexts; fail the test on console errors and page errors.
    With ``fast_jobs=True`` the page polls ingestion jobs every FAST_JOB_POLL_MS (opt-in)."""
    contexts = []
    problems: list[str] = []

    def make(
        *,
        width: int = 1280,
        height: int = 900,
        color_scheme: str = "light",
        reduced_motion: str = "no-preference",
        locale: str = "tr-TR",
        fast_jobs: bool = False,
    ) -> Page:
        context = browser.new_context(
            viewport={"width": width, "height": height},
            locale=locale,
            timezone_id="Europe/Istanbul",
            color_scheme=color_scheme,
            reduced_motion=reduced_motion,
        )
        contexts.append(context)
        if fast_jobs:
            _serve_fast_job_polling(context)
        page = context.new_page()
        page.set_default_timeout(10_000)
        page.on(
            "console",
            lambda message: (
                problems.append(message.text)
                if message.type == "error" and not message.text.startswith(IGNORED_CONSOLE_PREFIX)
                else None
            ),
        )
        page.on("pageerror", lambda error: problems.append(str(error)))
        return page

    yield make
    for context in contexts:
        context.close()
    assert problems == [], problems


@pytest.fixture
def page(make_page: Callable[..., Page]) -> Page:
    return make_page()


@pytest.fixture
def fast_job_polling(page: Page) -> None:
    """Opt-in for the tests that upload through the UI: the page polls an ingestion job every
    FAST_JOB_POLL_MS instead of 1 s. Request it with ``pytest.mark.usefixtures``; the polling
    tests leave it out and keep the default timing."""
    _serve_fast_job_polling(page.context)
