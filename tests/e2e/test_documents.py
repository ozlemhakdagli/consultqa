import pytest
from playwright.sync_api import expect
from ui_helpers import (
    collection_with_document,
    mock_collections_unavailable,
    new_library,
    open_page,
    upload_text,
)

pytestmark = pytest.mark.e2e


def _row(page, filename):
    return page.locator("#document-list li").filter(has_text=filename)


def test_first_visit_shows_the_drop_area_and_says_there_are_no_documents(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    expect(page.locator("#documents-empty")).to_have_text("Henüz belge eklemediniz.")
    expect(page.get_by_text("Dosyalarınızı buraya sürükleyip bırakın")).to_be_visible()
    expect(page.get_by_label("Dosya seçin")).to_be_enabled()
    expect(page.locator("#upload-hint")).to_have_text(
        "Desteklenen dosyalar: MD, PDF, TXT. En büyük dosya boyutu: 1 MB."
    )
    expect(page.locator("#documents-title")).to_be_hidden()


def test_upload_is_locked_until_a_collection_is_chosen(page, base_url):
    mock_collections_unavailable(page)
    open_page(page, base_url, library=False)
    expect(page.locator("#upload-files")).to_be_disabled()
    expect(page.locator("#upload-reason")).to_have_text(
        "Belge alanı henüz hazır değil. Birkaç saniye bekleyin; olmazsa sayfayı yenileyin."
    )
    expect(page.locator("#upload-hint")).to_contain_text(
        "Desteklenen dosyalar: MD, PDF, TXT. En büyük dosya boyutu: 1 MB."
    )


def test_the_drop_area_is_locked_while_the_system_opens(page, base_url):
    new_library(page, base_url)
    real = page.request.get(base_url + "/api/capabilities").json()
    page.route("**/api/capabilities", lambda route: route.fulfill(json={**real, "ready": False}))
    page.goto(base_url + "/")
    expect(page.locator("#upload-files")).to_be_disabled()
    expect(page.locator("#upload-reason")).to_have_text(
        "Sistem açılırken belge eklenemez. Birkaç dakika bekleyin."
    )


def test_status_is_honest_while_the_file_is_sent_and_prepared(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    held = []

    def hold(route):
        if route.request.method == "POST":
            held.append(route)
        else:
            route.fallback()

    page.route("**/api/collections/*/documents", hold)
    upload_text(page, "ocak.md")
    row = _row(page, "ocak.md")
    expect(row.locator(".doc-status")).to_have_text("Yükleniyor…")
    expect(row.locator("progress")).to_be_visible()
    assert row.locator("progress").get_attribute("value") is None
    expect(row).not_to_contain_text("%")
    polls = {"n": 0}

    def job(route):
        polls["n"] += 1
        if polls["n"] <= 2:
            route.fulfill(json={"state": "embedding", "error": None, "document_id": "pending"})
        else:
            route.fallback()

    page.route("**/api/jobs/*", job)
    held[0].continue_()
    expect(row.locator(".doc-status")).to_have_text("Hazırlanıyor…")
    expect(row).to_contain_text("Büyük belgelerde bu birkaç dakika sürebilir.")
    expect(row.locator(".doc-status")).to_have_text("Kullanıma hazır", timeout=20000)
    expect(page.locator("#document-list li[data-status=ready]")).to_have_count(1)
    expect(page.locator("#documents-live")).to_have_text("ocak.md: Kullanıma hazır")


@pytest.mark.usefixtures("fast_job_polling")
def test_drop_adds_files_like_the_button(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    page.evaluate(
        """() => {
          const transfer = new DataTransfer();
          transfer.items.add(new File(['Garanti süresi iki yıldır.'], 'birakilan.txt', { type: 'text/plain' }));
          document.getElementById('dropzone').dispatchEvent(
            new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true }));
        }"""
    )
    expect(_row(page, "birakilan.txt").locator(".doc-status")).to_have_text(
        "Kullanıma hazır", timeout=20000
    )


# Review Focus 1: a file dropped beside the drop area must not open in the browser.
def test_a_file_dropped_outside_the_area_does_not_open_in_the_browser(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    url = page.url
    prevented = page.evaluate(
        """() => {
          const transfer = new DataTransfer();
          transfer.items.add(new File(['x'], 'fuera.txt', { type: 'text/plain' }));
          const event = new DragEvent('drop', { dataTransfer: transfer, bubbles: true, cancelable: true });
          document.body.dispatchEvent(event);
          return event.defaultPrevented;
        }"""
    )
    assert prevented is True
    assert page.url == url


@pytest.mark.usefixtures("fast_job_polling")
def test_rejected_files_get_a_clear_message_and_the_others_continue(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    page.locator("#upload-files").set_input_files(
        [
            {"name": "virus.exe", "mimeType": "application/octet-stream", "buffer": b"MZ"},
            {"name": "buyuk.txt", "mimeType": "text/plain", "buffer": b"a" * 1_500_000},
            {
                "name": "iyi.txt",
                "mimeType": "text/plain",
                "buffer": "Garanti süresi iki yıldır.".encode(),
            },
        ]
    )
    expect(_row(page, "virus.exe")).to_contain_text("Okunamadı: Bu dosya türü desteklenmiyor.")
    expect(_row(page, "buyuk.txt")).to_contain_text("Okunamadı: Dosya çok büyük.")
    expect(_row(page, "iyi.txt")).to_contain_text("Kullanıma hazır", timeout=20000)


@pytest.mark.usefixtures("fast_job_polling")
def test_server_side_failures_are_explained(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    page.locator("#upload-files").set_input_files(
        [
            {"name": "bozuk.pdf", "mimeType": "application/pdf", "buffer": b"nope"},
            {"name": "bosluk.txt", "mimeType": "text/plain", "buffer": b"  \n"},
        ]
    )
    expect(_row(page, "bozuk.pdf")).to_contain_text(
        "Okunamadı: Dosya açılamadı. Bozuk ya da şifreli olabilir."
    )
    expect(_row(page, "bosluk.txt")).to_contain_text(
        "Okunamadı: Dosyada okunabilir yazı bulunamadı. Resimden oluşan (taranmış) bir PDF olabilir."
    )
    _row(page, "bozuk.pdf").get_by_role("button", name="bozuk.pdf satırını kapat").click()
    _row(page, "bosluk.txt").get_by_role("button", name="bosluk.txt satırını kapat").click()
    expect(page.locator("#document-list li")).to_have_count(0)
    expect(page.locator("#documents-empty")).to_have_text("Henüz belge eklemediniz.")


@pytest.mark.usefixtures("fast_job_polling")
def test_uploading_the_same_content_twice_is_reported(page, base_url):
    collection_with_document(page, base_url, filename="ilk.md")
    upload_text(page, "kopya.md")
    expect(_row(page, "kopya.md")).to_contain_text("Bu belge zaten ekli; yeniden eklenmedi.")
    expect(page.locator("#document-list li[data-status=ready]")).to_have_count(1)
    _row(page, "kopya.md").get_by_role("button", name="kopya.md satırını kapat").click()
    expect(_row(page, "kopya.md")).to_have_count(0)


@pytest.mark.usefixtures("fast_job_polling")
def test_delete_asks_for_confirmation_first(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_role("button", name="ocak.md belgesini sil").click()
    expect(page.locator(".doc-confirm")).to_contain_text(
        "“ocak.md” silinsin mi? Bu işlem geri alınamaz."
    )
    expect(page.get_by_role("button", name="Vazgeç")).to_be_focused()
    page.get_by_role("button", name="Vazgeç").click()
    expect(page.locator("#document-list li")).to_have_count(1)
    page.get_by_role("button", name="ocak.md belgesini sil").click()
    page.get_by_role("button", name="Evet, sil").click()
    expect(page.locator("#documents-message")).to_have_text("“ocak.md” silindi.")
    expect(page.locator("#documents-empty")).to_have_text("Henüz belge eklemediniz.")


# Review Focus 1: server-provided text is never interpreted as HTML.
@pytest.mark.usefixtures("fast_job_polling")
def test_file_and_document_names_are_shown_as_text_never_as_html(page, base_url):
    name = "<img src=x onerror=window.__pwned=1>.txt"
    new_library(page, base_url)
    open_page(page, base_url)
    upload_text(page, name, content="Garanti süresi iki yıldır.")
    expect(_row(page, "<img src=x")).to_contain_text("Kullanıma hazır")
    expect(page.locator("#document-list")).to_contain_text(
        "<img src=x onerror=window.__pwned=1>.txt"
    )
    expect(page.locator("#document-list img")).to_have_count(0)
    assert page.evaluate("window.__pwned") is None
