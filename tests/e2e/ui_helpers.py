"""Helpers shared by the browser tests: unique names and the steps every test repeats."""

from __future__ import annotations

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


def open_page(page: Page, base_url: str) -> None:
    """Open the page and wait until the models report ready (the chip reads "Sistem hazır")."""
    page.goto(base_url + "/")
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")


def create_collection(page: Page, name: str) -> None:
    """Create a collection through the form and wait until it is the selected one."""
    page.get_by_label("Yeni koleksiyon adı").fill(name)
    page.get_by_role("button", name="Koleksiyon oluştur").click()
    expect(page.locator("#collection-select option:checked")).to_have_text(name)


SAMPLE = (
    "# Sipariş\n\nSipariş modülü tablo filtreleme.\n\n# Stok\n\n"
    "Stok modülü performans iyileştirmesi yapıldı.\n"
)


def mock_empty_collections(page: Page) -> None:
    """Make the collection list empty, for the first-visit states (other requests pass through)."""
    page.route(
        "**/api/collections",
        lambda route: route.fulfill(json=[]) if route.request.method == "GET" else route.fallback(),
    )


def upload_text(page: Page, filename: str, content: str = SAMPLE, mime: str = "text/plain") -> None:
    """Choose one file from memory and press the upload button."""
    page.locator("#upload-files").set_input_files(
        [{"name": filename, "mimeType": mime, "buffer": content.encode("utf-8")}]
    )
    page.get_by_role("button", name="Yükle", exact=True).click()


def collection_with_document(
    page: Page, base_url: str, filename: str = "ocak.md", content: str = SAMPLE
) -> str:
    """Open the page, create a collection, upload one document and wait until it is ready."""
    open_page(page, base_url)
    name = unique("Koleksiyon")
    create_collection(page, name)
    upload_text(page, filename, content)
    row = page.locator("#upload-list li").filter(has_text=filename)
    expect(row).to_contain_text("Hazır.")
    return name


def caps_without_llm(page: Page, base_url: str) -> dict[str, Any]:
    """The real capabilities with no LLM configured: every LLM method becomes unavailable."""
    caps = page.request.get(base_url + "/api/capabilities").json()
    caps["llm_configured"] = False
    for preset in caps["presets"]:
        if preset["uses_llm"]:
            preset["available"] = False
            preset["reason"] = "llm_not_configured"
    return caps
