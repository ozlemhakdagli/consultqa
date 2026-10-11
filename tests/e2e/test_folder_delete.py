"""Deleting a folder from the advanced section: the confirmation, the list, the default library."""

import re

import pytest
from playwright.sync_api import expect
from ui_helpers import (
    SAMPLE,
    create_collection,
    open_advanced,
    open_page,
    unique,
    upload_and_wait,
)

pytestmark = pytest.mark.e2e


def _folder_names(page, base_url) -> list[str]:
    return [c["name"] for c in page.request.get(base_url + "/api/collections").json()]


def _folder_row(page, name):
    return page.locator("#folder-list li").filter(has_text=name)


def _delete_button(page, name):
    return _folder_row(page, name).get_by_role("button", name=f"{name} klasörünü sil", exact=True)


@pytest.mark.usefixtures("fast_job_polling")
def test_confirming_the_deletion_removes_the_folder_and_its_documents(page, base_url):
    name = unique("Silinecek")
    document = unique("belge") + ".md"
    open_page(page, base_url)
    create_collection(page, name)
    upload_and_wait(page, document, SAMPLE)
    open_advanced(page)
    expect(_folder_row(page, name)).to_contain_text("Belge sayısı: 1")
    asked = []

    def accept(dialog):
        asked.append(dialog.message)
        dialog.accept()

    page.on("dialog", accept)
    _delete_button(page, name).click()
    expect(page.locator("#collection-message")).to_have_text(
        f"“{name}” klasörü ve içindeki belgeler silindi."
    )
    assert asked == [
        f"“{name}” klasörü ve içindeki tüm belgeler silinsin mi? Bu işlem geri alınamaz."
    ]
    assert name not in _folder_names(page, base_url)
    expect(_folder_row(page, name)).to_have_count(0)
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    expect(page.locator("#library-notice")).to_be_hidden()
    expect(page.locator("#document-list li").filter(has_text=document)).to_have_count(0)


@pytest.mark.usefixtures("fast_job_polling")
def test_dismissing_the_confirmation_deletes_nothing(page, base_url):
    name = unique("Kalacak")
    document = unique("belge") + ".md"
    open_page(page, base_url)
    create_collection(page, name)
    upload_and_wait(page, document, SAMPLE)
    page.on("dialog", lambda dialog: dialog.dismiss())
    _delete_button(page, name).click()
    expect(page.locator("#collection-select option:checked")).to_have_text(name)
    expect(page.locator("#document-list li").filter(has_text=document)).to_be_visible()
    assert name in _folder_names(page, base_url)


def test_a_folder_that_is_still_being_prepared_is_kept_and_explained(page, base_url):
    name = unique("Hazırlanan")
    open_page(page, base_url)
    create_collection(page, name)
    refused = []

    def refuse(route):
        refused.append(route.request.url)
        route.fulfill(status=409, json={"detail": "collection_busy"})

    page.route(
        re.compile(r".*/api/collections/[^/]+$"),
        lambda route: refuse(route) if route.request.method == "DELETE" else route.fallback(),
    )
    page.on("dialog", lambda dialog: dialog.accept())
    _delete_button(page, name).click()
    expect(page.locator("#collection-message")).to_have_text(
        "Bu klasörde belge hazırlanıyor. Bittikten sonra tekrar deneyin."
    )
    expect(_folder_row(page, name)).to_have_count(1)
    assert len(refused) == 1
    page.unroute(re.compile(r".*/api/collections/[^/]+$"))
    assert name in _folder_names(page, base_url)


def test_the_default_library_can_be_deleted_and_is_created_again(make_page, fresh_server):
    page = make_page()
    open_page(page, fresh_server)
    before = page.request.get(fresh_server + "/api/collections").json()
    old_id = before[0]["id"]
    page.on("dialog", lambda dialog: dialog.accept())
    open_advanced(page)
    _delete_button(page, "Belgelerim").click()
    expect(page.locator("#collection-message")).to_have_text(
        "“Belgelerim” klasörü ve içindeki belgeler silindi."
    )
    expect(page.locator("#collection-select option:checked")).to_have_text("Belgelerim")
    after = page.request.get(fresh_server + "/api/collections").json()
    assert [c["name"] for c in after] == ["Belgelerim"]
    assert after[0]["id"] != old_id


def test_the_folder_deletion_is_explained_in_english(make_page, base_url):
    # A browser that prefers English gets the English page, so no language is chosen here.
    page = make_page(locale="en-GB")
    name = unique("Remove")
    open_page(page, base_url)
    create_collection_en(page, name)
    page.on("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name=f"Delete the folder {name}", exact=True).click()
    expect(page.locator("#collection-message")).to_have_text(
        f"The folder “{name}” and the documents in it were deleted."
    )


def create_collection_en(page, name):
    open_advanced(page)
    page.get_by_label("New folder name").fill(name)
    page.get_by_role("button", name="Create folder").click()
    expect(page.locator("#collection-select option:checked")).to_have_text(name)
