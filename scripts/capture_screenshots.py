"""Capture the four README screenshots from the sample documents only.

The script starts a throwaway stub-backend server with a fresh state folder under the system
temp folder, uploads the two sample PDFs from ``data/sample/pdf/`` and drives headless Chrome.
It uses only those sample PDFs, that temporary state folder and a fresh browser profile. It
never reads the owner's state folder, the running Docker app or any real document. Inherited
``CONSULTQA_*`` variables are dropped, so the server cannot pick up a real backend or state.

Usage, from the repository root (needs the ``e2e`` extra and Chrome or Chromium)::

    python scripts/make_sample_pdfs.py
    python scripts/capture_screenshots.py
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Iterator, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "sample" / "pdf"
OUT_DIR = ROOT / "assets" / "images"
SHOT_NAMES: tuple[str, ...] = (
    "workspace-overview.png",
    "answer-with-source.png",
    "viewer-highlight.png",
    "narrow-tabs.png",
)
SAMPLE_PDFS: tuple[str, ...] = ("order_guide.pdf", "stock_report.pdf")
READY_TIMEOUT_S = 60.0


def server_env(state_dir: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment of the throwaway server: no inherited CONSULTQA_* variable, a stub
    backend, the pdfium parser, offline models, and a state folder under the temp folder."""
    temp_root = Path(tempfile.gettempdir()).resolve()
    if temp_root not in state_dir.resolve().parents:
        raise ValueError(f"the state folder must be inside {temp_root}, not {state_dir}")
    source = os.environ if base is None else base
    env = {key: value for key, value in source.items() if not key.startswith("CONSULTQA_")}
    env.update(
        {
            "CONSULTQA_BACKEND": "stub",
            "CONSULTQA_PARSER": "pdfium",
            "CONSULTQA_STATE_DIR": str(state_dir),
            "HF_HUB_OFFLINE": "1",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    return env


def free_port() -> int:
    """A port that was free on 127.0.0.1 when asked for."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@contextlib.contextmanager
def running_server(state_dir: Path) -> Iterator[str]:
    """Start the stub server on a free port, wait until ``/api/ready`` answers, yield its URL."""
    state_dir.mkdir(parents=True, exist_ok=True)
    port = free_port()
    command = [
        sys.executable, "-m", "uvicorn", "consultqa.api.app:create_app", "--factory",
        "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning",
    ]  # fmt: skip
    log_path = state_dir / "server.log"
    url = f"http://127.0.0.1:{port}"
    with log_path.open("w") as log:
        process = subprocess.Popen(  # noqa: S603
            command, cwd=ROOT, env=server_env(state_dir), stdout=log, stderr=log
        )
        try:
            deadline = time.monotonic() + READY_TIMEOUT_S
            while True:
                if _is_ready(f"{url}/api/ready"):
                    break
                if process.poll() is not None:
                    raise RuntimeError(f"server exited:\n{log_path.read_text()[-2000:]}")
                if time.monotonic() > deadline:
                    raise RuntimeError(f"server not ready:\n{log_path.read_text()[-2000:]}")
                time.sleep(0.5)
            yield url
        finally:
            process.terminate()
            process.wait(timeout=10)


def _is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:  # noqa: S310
            return bool(response.status == 200)
    except OSError:
        return False


QUESTION = "Depo sayımı ne zaman tamamlanır?"
EXPECTED = "tamamlan"
VIEWPORT_DESKTOP = {"width": 1280, "height": 1100}
VIEWPORT_NARROW = {"width": 390, "height": 844}
DOCUMENT_READY_TEXT = "Ready to use"


def _launch(playwright):  # type: ignore[no-untyped-def]
    """Google Chrome when it is installed, otherwise the bundled Chromium (as the e2e tests)."""
    from playwright.sync_api import Error as PlaywrightError

    for options in ({"channel": "chrome"}, {}):
        try:
            return playwright.chromium.launch(**options)
        except PlaywrightError:
            continue
    raise RuntimeError("no headless Chrome or Chromium; install Chrome or run playwright install")


def _ask(page, expect) -> None:  # type: ignore[no-untyped-def]
    page.get_by_label("Your question", exact=True).fill(QUESTION)
    page.get_by_role("button", name="Find the answer").click()
    expect(page.locator(".citation-card mark").first).to_be_visible()


def capture(base_url: str, out_dir: Path) -> list[Path]:
    """Take the four screenshots against the server at ``base_url``, in ``SHOT_NAMES`` order."""
    from playwright.sync_api import expect, sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = [out_dir / name for name in SHOT_NAMES]
    with sync_playwright() as playwright:
        browser = _launch(playwright)
        try:
            # Desktop: overview, answer, and the viewer with the highlight.
            context = browser.new_context(
                viewport=VIEWPORT_DESKTOP,
                locale="en-US",
                color_scheme="light",
                device_scale_factor=2,
            )
            page = context.new_page()
            page.set_default_timeout(30_000)
            page.goto(f"{base_url}/")
            expect(page.locator("#system-chip")).to_have_class(re.compile(r"chip-ready"))
            expect(page.locator("#upload-files")).to_be_enabled()
            page.screenshot(path=str(paths[0]))

            page.locator("#upload-files").set_input_files(
                [str(DATA_DIR / name) for name in SAMPLE_PDFS]
            )
            for name in SAMPLE_PDFS:
                row = page.locator("#document-list li").filter(has_text=name)
                expect(row).to_contain_text(DOCUMENT_READY_TEXT, timeout=30_000)

            _ask(page, expect)
            marked = page.locator(".citation-card mark").first.inner_text()
            if EXPECTED not in marked:
                raise RuntimeError(f"the marked sentence does not contain {EXPECTED!r}: {marked!r}")
            expect(page.locator(".citation-card .page-button").first).to_be_visible()
            page.locator("#pane-chat").screenshot(path=str(paths[1]))

            page.locator(".citation-card .page-button").first.click()
            expect(page.locator("#viewer-canvas canvas").first).to_be_visible(timeout=15_000)
            expect(page.locator(".pdf-highlight").first).to_be_visible(timeout=15_000)
            page.wait_for_timeout(500)
            page.screenshot(path=str(paths[2]))
            context.close()

            # Narrow phone width: one pane at a time, the tab row at the top.
            context = browser.new_context(
                viewport=VIEWPORT_NARROW,
                locale="en-US",
                color_scheme="light",
                device_scale_factor=2,
            )
            page = context.new_page()
            page.set_default_timeout(30_000)
            page.goto(f"{base_url}/")
            expect(page.locator("#system-chip")).to_have_class(re.compile(r"chip-ready"))
            page.locator("#tab-chat").click()
            _ask(page, expect)
            page.screenshot(path=str(paths[3]))
            context.close()
        finally:
            browser.close()
    return paths


def main() -> None:
    missing = [name for name in SAMPLE_PDFS if not (DATA_DIR / name).is_file()]
    if missing:
        sys.exit(f"missing sample PDFs {missing}; run: python scripts/make_sample_pdfs.py")
    with tempfile.TemporaryDirectory(prefix="consultqa-shots-") as temp:
        state_dir = Path(temp) / "state"
        with running_server(state_dir) as base_url:
            for path in capture(base_url, OUT_DIR):
                print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
