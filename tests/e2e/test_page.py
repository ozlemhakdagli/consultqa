import pytest
from playwright.sync_api import expect
from ui_helpers import open_page

pytestmark = pytest.mark.e2e


def test_page_shows_the_turkish_title_and_three_numbered_steps(page, base_url):
    open_page(page, base_url)
    assert page.title() == "Belge Soru-Cevap"
    expect(page.get_by_role("heading", level=1)).to_have_text("Belge Soru-Cevap")
    expect(page.get_by_role("heading", level=2)).to_have_text(
        ["1 Koleksiyon seçin", "2 Belge yükleyin", "3 Soru sorun"]
    )
    expect(page.locator("#system-banner")).to_be_hidden()


def test_banner_explains_the_model_loading_and_disappears_when_ready(page, base_url):
    real = page.request.get(base_url + "/api/capabilities").json()
    calls = {"n": 0}

    def handler(route):
        calls["n"] += 1
        route.fulfill(json={**real, "ready": calls["n"] > 1})

    page.route("**/api/capabilities", handler)
    page.goto(base_url + "/")
    expect(page.locator("#system-chip")).to_have_text("Modeller yükleniyor")
    expect(page.locator("#system-banner")).to_contain_text("Yapay zekâ modelleri yükleniyor")
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır", timeout=8000)
    expect(page.locator("#system-banner")).to_be_hidden()


def test_unreachable_server_is_reported_and_recovers(page, base_url):
    page.route("**/api/capabilities", lambda route: route.abort())
    page.goto(base_url + "/")
    expect(page.locator("#system-chip")).to_have_text("Sunucuya ulaşılamıyor")
    expect(page.locator("#system-banner")).to_contain_text("Sunucunun çalıştığından emin olun")
    page.unroute("**/api/capabilities")
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır", timeout=8000)
