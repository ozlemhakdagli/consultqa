import pytest
from playwright.sync_api import expect
from ui_helpers import create_collection, open_page, unique

pytestmark = pytest.mark.e2e


def test_first_visit_explains_what_to_do(page, base_url):
    page.route(
        "**/api/collections",
        lambda route: route.fulfill(json=[]) if route.request.method == "GET" else route.fallback(),
    )
    open_page(page, base_url)
    expect(page.locator("#collection-select")).to_be_disabled()
    expect(page.locator("#collection-select option")).to_have_text(
        "Henüz koleksiyon yok. Aşağıdan bir ad yazıp oluşturun."
    )


def test_create_collection_selects_it_and_confirms(page, base_url):
    name = unique("Şirket Kılavuzları İşlem")
    open_page(page, base_url)
    create_collection(page, name)
    expect(page.locator("#collection-message")).to_have_text(
        f"“{name}” koleksiyonu oluşturuldu. Şimdi 2. adımda belge yükleyebilirsiniz."
    )
    expect(page.get_by_label("Yeni koleksiyon adı")).to_have_value("")


def test_duplicate_and_blank_names_are_explained(page, base_url):
    name = unique("Kopya")
    open_page(page, base_url)
    create_collection(page, name)
    page.get_by_label("Yeni koleksiyon adı").fill(name)
    page.get_by_role("button", name="Koleksiyon oluştur").click()
    expect(page.locator("#collection-message")).to_have_text(
        "Bu adda bir koleksiyon zaten var. Başka bir ad yazın veya listeden onu seçin."
    )
    page.get_by_label("Yeni koleksiyon adı").fill("   ")
    page.get_by_role("button", name="Koleksiyon oluştur").click()
    expect(page.locator("#collection-message")).to_have_text("Lütfen koleksiyon için bir ad yazın.")


def test_selected_collection_is_remembered_after_a_reload(page, base_url):
    first, second = unique("Birinci"), unique("İkinci")
    open_page(page, base_url)
    create_collection(page, first)
    create_collection(page, second)
    page.locator("#collection-select").select_option(label=first)
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    expect(page.locator("#collection-select option:checked")).to_have_text(first)
