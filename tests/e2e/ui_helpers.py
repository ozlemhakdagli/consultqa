"""Helpers shared by the browser tests: unique names and the steps every test repeats."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from playwright.sync_api import expect

if TYPE_CHECKING:
    from playwright.sync_api import Page


def unique(prefix: str) -> str:
    """A name that no earlier test used, so tests can share one server and one store."""
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def run_js(page: Page, base_url: str, body: str) -> Any:
    """Run ``body`` as the body of an async function on a same-origin page; return its result.

    The page is the JSON health endpoint: it has no inline script and no page headers, and it
    lets the body use ``import('/js/...')`` on the server's own origin.
    """
    page.goto(base_url + "/api/health")
    return page.evaluate(f"(async () => {{ {body} }})()")


def open_page(page: Page, base_url: str, *, library: bool = True) -> None:
    """Open the page and wait until the models report ready (the chip reads "Sistem hazır").
    With ``library`` the page also waits until its library is chosen and the upload is enabled."""
    page.goto(base_url + "/")
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    if library:
        expect(page.locator("#upload-files")).to_be_enabled()


def open_advanced(page: Page) -> None:
    """Open the closed "Gelişmiş seçenekler" section unless it is open already."""
    if not page.evaluate("document.getElementById('advanced').open"):
        page.locator("#advanced > summary").click()


def choose_method(page: Page, name: str) -> None:
    """Open the advanced section and choose one answer method by its plain name."""
    open_advanced(page)
    page.get_by_role("radio", name=name, exact=True).check()


def create_collection(page: Page, name: str) -> None:
    """Create a folder through the advanced form and wait until it is the selected one."""
    open_advanced(page)
    page.get_by_label("Yeni klasör adı").fill(name)
    page.get_by_role("button", name="Klasör oluştur").click()
    expect(page.locator("#collection-select option:checked")).to_have_text(name)


SAMPLE = (
    "# Sipariş\n\nSipariş modülü tablo filtreleme.\n\n# Stok\n\n"
    "Stok modülü performans iyileştirmesi yapıldı.\n"
)


def mock_collections_unavailable(page: Page) -> None:
    """Make the folder list fail, for the states of a page without a library."""
    page.route(
        "**/api/collections",
        lambda route: (
            route.fulfill(status=500, json={"detail": "internal_error"})
            if route.request.method == "GET"
            else route.fallback()
        ),
    )


def new_library(page: Page, base_url: str) -> str:
    """Create a uniquely named folder on the server and make the page open on it.

    The page keeps its choice in localStorage; the init script sets that choice only while the page
    has none, so a test can still change it. Returns the folder id.
    """
    created = page.request.post(base_url + "/api/collections", data={"name": unique("Klasör")})
    cid = created.json()["id"]
    page.add_init_script(
        "try { if (!localStorage.getItem('docrag.collection')) "
        f"localStorage.setItem('docrag.collection', {json.dumps(cid)}); }} catch (e) {{}}"
    )
    return cid


def upload_text(page: Page, filename: str, content: str = SAMPLE, mime: str = "text/plain") -> None:
    """Choose one file from memory; the file is sent as soon as it is chosen."""
    page.locator("#upload-files").set_input_files(
        [{"name": filename, "mimeType": mime, "buffer": content.encode("utf-8")}]
    )


def collection_with_document(
    page: Page, base_url: str, filename: str = "ocak.md", content: str = SAMPLE
) -> str:
    """Open the page on a new library, upload one document and wait until it is ready."""
    cid = new_library(page, base_url)
    open_page(page, base_url)
    upload_text(page, filename, content)
    row = page.locator("#document-list li").filter(has_text=filename)
    expect(row).to_contain_text("Kullanıma hazır")
    return cid


def caps_without_llm(page: Page, base_url: str) -> dict[str, Any]:
    """The real capabilities with no LLM configured: every LLM method becomes unavailable."""
    caps = page.request.get(base_url + "/api/capabilities").json()
    caps["llm_configured"] = False
    for preset in caps["presets"]:
        if preset["uses_llm"]:
            preset["available"] = False
            preset["reason"] = "llm_not_configured"
    return caps
