import json
import re

import pytest
from playwright.sync_api import expect
from ui_helpers import (
    create_collection,
    mock_collections_unavailable,
    open_advanced,
    open_page,
    unique,
)

pytestmark = pytest.mark.e2e


def test_first_visit_creates_the_default_library_once(make_page, fresh_server):
    page = make_page()
    open_page(page, fresh_server)

    def names():
        return [c["name"] for c in page.request.get(fresh_server + "/api/collections").json()]

    assert names() == ["Belgelerim"]
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    assert names() == ["Belgelerim"]


def test_a_library_that_cannot_be_opened_is_explained_where_the_user_looks(page, base_url):
    mock_collections_unavailable(page)
    open_page(page, base_url, library=False)
    expect(page.locator("#documents-message")).to_be_visible()
    expect(page.locator("#documents-message")).to_have_class(re.compile("message-error"))


def test_folders_stay_hidden_until_advanced_options_are_opened(page, base_url):
    open_page(page, base_url)
    expect(page.locator("#collection-select")).to_be_hidden()
    open_advanced(page)
    expect(page.locator("#collection-select")).to_be_visible()
    expect(page.get_by_label("Kullanılan klasör")).to_be_visible()


def test_a_folder_that_is_not_the_default_is_announced(page, base_url):
    name = unique("Başka")
    open_page(page, base_url)
    expect(page.locator("#library-notice")).to_be_hidden()
    create_collection(page, name)
    expect(page.locator("#library-notice")).to_have_text(
        f"Şu anda “{name}” klasörünü kullanıyorsunuz. Varsayılan klasöre dönmek için "
        "Gelişmiş seçeneklerden “Belgelerim” klasörünü seçin."
    )
    page.locator("#collection-select").select_option(label="Belgelerim")
    expect(page.locator("#library-notice")).to_be_hidden()


def test_create_folder_selects_it_and_confirms(page, base_url):
    name = unique("Şirket Kılavuzları İşlem")
    open_page(page, base_url)
    create_collection(page, name)
    expect(page.locator("#collection-message")).to_have_text(
        f"“{name}” klasörü oluşturuldu ve seçildi."
    )
    expect(page.get_by_label("Yeni klasör adı")).to_have_value("")


def test_duplicate_and_blank_names_are_explained(page, base_url):
    name = unique("Kopya")
    open_page(page, base_url)
    create_collection(page, name)
    page.get_by_label("Yeni klasör adı").fill(name)
    page.get_by_role("button", name="Klasör oluştur").click()
    expect(page.locator("#collection-message")).to_have_text(
        "Bu adda bir klasör zaten var. Başka bir ad yazın ya da listeden o klasörü seçin."
    )
    page.get_by_label("Yeni klasör adı").fill("   ")
    page.get_by_role("button", name="Klasör oluştur").click()
    expect(page.locator("#collection-message")).to_have_text("Lütfen klasör için bir ad yazın.")


def test_choosing_another_folder_lasts_for_this_visit_only(page, base_url):
    name = unique("Birinci")
    open_page(page, base_url)
    create_collection(page, name)
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    expect(page.locator("#collection-select option").filter(has_text=name)).to_have_count(1)


def test_a_folder_remembered_by_an_older_page_is_ignored_and_forgotten(make_page, base_url):
    page = make_page()
    other = page.request.post(base_url + "/api/collections", data={"name": unique("Eski")})
    page.add_init_script(
        "try { localStorage.setItem('docrag.collection', "
        f"{json.dumps(other.json()['id'])}); }} catch (e) {{}}"
    )
    open_page(page, base_url)
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    assert page.evaluate("localStorage.getItem('docrag.collection')") is None
