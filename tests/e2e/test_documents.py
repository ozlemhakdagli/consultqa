import pytest
from playwright.sync_api import expect
from ui_helpers import (
    collection_with_document,
    create_collection,
    mock_empty_collections,
    open_page,
    unique,
    upload_text,
)

pytestmark = pytest.mark.e2e


def _row(page, filename):
    return page.locator("#upload-list li").filter(has_text=filename)


def test_upload_is_locked_until_a_collection_is_chosen(page, base_url):
    mock_empty_collections(page)
    open_page(page, base_url)
    expect(page.locator("#upload-submit")).to_be_disabled()
    expect(page.locator("#upload-files")).to_be_disabled()
    expect(page.locator("#upload-reason")).to_have_text(
        "Önce 1. adımda bir koleksiyon seçin veya oluşturun."
    )
    expect(page.locator("#upload-hint")).to_contain_text(
        "Desteklenen türler: .md, .pdf, .txt. En büyük dosya boyutu: 1 MB."
    )


def test_upload_shows_each_stage_until_the_document_is_ready_and_lists_it(page, base_url):
    open_page(page, base_url)
    create_collection(page, unique("Aşamalar"))
    stages = ["queued", "parsing", "embedding", "graph"]
    polls = {"n": 0}

    def job(route):
        index = polls["n"]
        polls["n"] += 1
        if index < len(stages):
            route.fulfill(json={"state": stages[index], "error": None, "document_id": "pending"})
        else:
            route.fallback()

    page.route("**/api/jobs/*", job)
    upload_text(page, "ocak.md")
    row = _row(page, "ocak.md")
    for text in (
        "Sırada bekliyor",
        "Dosya okunuyor",
        "aranabilir hale getiriliyor",
        "bağlantılar kuruluyor",
    ):
        expect(row).to_contain_text(text)
        expect(row.locator("progress")).to_be_visible()
    expect(row).to_contain_text(
        "Hazır. Artık bu belge hakkında soru sorabilirsiniz.", timeout=15000
    )
    expect(row.locator("progress")).to_be_hidden()
    expect(page.locator("#documents-title")).to_have_text("Koleksiyondaki belgeler (1)")
    expect(page.locator("#document-list li")).to_have_count(1)
    expect(page.locator("#document-list li")).to_contain_text("ocak.md")
    row.get_by_role("button", name="ocak.md satırını kapat").click()
    expect(row).to_have_count(0)


def test_rejected_files_get_a_clear_message_and_the_others_continue(page, base_url):
    open_page(page, base_url)
    create_collection(page, unique("Reddedilen"))
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
    page.get_by_role("button", name="Yükle", exact=True).click()
    expect(_row(page, "virus.exe")).to_contain_text("Yüklenemedi: Bu dosya türü desteklenmiyor.")
    expect(_row(page, "buyuk.txt")).to_contain_text(
        "Yüklenemedi: Dosya izin verilen boyuttan büyük."
    )
    expect(_row(page, "iyi.txt")).to_contain_text("Hazır.")


def test_server_side_failures_are_explained(page, base_url):
    open_page(page, base_url)
    create_collection(page, unique("Hatalar"))
    page.locator("#upload-files").set_input_files(
        [
            {"name": "bozuk.pdf", "mimeType": "application/pdf", "buffer": b"nope"},
            {"name": "bosluk.txt", "mimeType": "text/plain", "buffer": b"  \n"},
        ]
    )
    page.get_by_role("button", name="Yükle", exact=True).click()
    expect(_row(page, "bozuk.pdf")).to_contain_text(
        "Yüklenemedi: Dosya okunamadı. Bozuk, şifreli veya metin içermeyen bir dosya olabilir."
    )
    expect(_row(page, "bosluk.txt")).to_contain_text(
        "Yüklenemedi: Dosyada dizinlenecek metin bulunamadı. Taranmış (resim) bir PDF olabilir."
    )
    expect(page.locator("#document-list li")).to_have_count(0)
    expect(page.locator("#documents-empty")).to_have_text(
        "Bu koleksiyonda henüz belge yok. Yukarıdan bir dosya yükleyin."
    )


def test_uploading_the_same_content_twice_is_reported(page, base_url):
    collection_with_document(page, base_url, filename="ilk.md")
    upload_text(page, "kopya.md")
    expect(_row(page, "kopya.md")).to_contain_text(
        "Bu içerik koleksiyonda zaten var; belge yeniden eklenmedi."
    )
    expect(page.locator("#document-list li")).to_have_count(1)


def test_choosing_no_file_is_explained(page, base_url):
    open_page(page, base_url)
    create_collection(page, unique("Boş"))
    page.get_by_role("button", name="Yükle", exact=True).click()
    expect(page.locator("#documents-message")).to_have_text(
        "Lütfen yüklenecek en az bir dosya seçin."
    )


def test_delete_asks_for_confirmation_first(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_role("button", name="ocak.md belgesini sil").click()
    expect(page.locator(".doc-confirm")).to_contain_text(
        "“ocak.md” silinsin mi? Belge ve arama kayıtları kalıcı olarak silinir."
    )
    expect(page.get_by_role("button", name="Vazgeç")).to_be_focused()
    page.get_by_role("button", name="Vazgeç").click()
    expect(page.locator("#document-list li")).to_have_count(1)
    page.get_by_role("button", name="ocak.md belgesini sil").click()
    page.get_by_role("button", name="Evet, sil").click()
    expect(page.locator("#documents-message")).to_have_text("“ocak.md” silindi.")
    expect(page.locator("#documents-empty")).to_have_text(
        "Bu koleksiyonda henüz belge yok. Yukarıdan bir dosya yükleyin."
    )


# Review Focus 1: server-provided text is never interpreted as HTML.
def test_file_and_document_names_are_shown_as_text_never_as_html(page, base_url):
    name = "<img src=x onerror=window.__pwned=1>.txt"
    open_page(page, base_url)
    create_collection(page, unique("Güvenlik"))
    upload_text(page, name, content="Garanti süresi iki yıldır.")
    expect(_row(page, "<img src=x")).to_contain_text("Hazır.")
    expect(page.locator("#document-list")).to_contain_text(
        "<img src=x onerror=window.__pwned=1>.txt"
    )
    expect(page.locator("#document-list img, #upload-list img")).to_have_count(0)
    assert page.evaluate("window.__pwned") is None
