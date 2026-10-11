import pytest
from playwright.sync_api import expect
from ui_helpers import (
    caps_without_llm,
    collection_with_document,
    create_collection,
    mock_empty_collections,
    open_page,
    unique,
    upload_text,
)

pytestmark = pytest.mark.e2e

ASK = "Cevabı bul"


def _ask(page, question="Stok modülü", method=None):
    if method:
        page.get_by_role("radio", name=method, exact=True).check()
    page.get_by_label("Sorunuz").fill(question)
    page.get_by_role("button", name=ASK).click()


def _mock_ask(page, status=200, **body):
    page.route("**/api/collections/*/ask", lambda route: route.fulfill(status=status, json=body))


def test_ask_is_locked_and_says_why(page, base_url):
    mock_empty_collections(page)
    open_page(page, base_url)
    expect(page.get_by_role("button", name=ASK)).to_be_disabled()
    expect(page.locator("#ask-reason")).to_have_text("Önce 1. adımda bir koleksiyon seçin.")
    page.unroute("**/api/collections")
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    create_collection(page, unique("Boş koleksiyon"))
    expect(page.locator("#ask-reason")).to_have_text(
        "Bu koleksiyonda belge yok. Önce 2. adımda en az bir belge yükleyin."
    )
    upload_text(page, "ocak.md")
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()
    expect(page.locator("#ask-reason")).to_be_hidden()


def test_methods_are_described_and_the_recommended_one_is_selected(page, base_url):
    open_page(page, base_url)
    radios = page.locator("#method-list input[type=radio]")
    expect(radios).to_have_count(6)
    expect(page.locator("#method-list input[type=radio]:disabled")).to_have_count(0)
    standard = page.get_by_role("radio", name="Standart", exact=True)
    expect(standard).to_be_checked()
    option = page.locator(".method-option").filter(has=standard)
    expect(option).to_contain_text("Önerilen")
    expect(option).to_contain_text("Hem anlam hem anahtar kelime benzerliğiyle arar")
    expect(
        page.locator(".method-option").filter(has_text="Dil modeli ile yaz (başlık bağlamlı)")
    ).to_contain_text("Dil modeli gerekir")


def test_llm_methods_are_disabled_with_the_reason_when_no_llm_is_configured(page, base_url):
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    for name in ("Dil modeli ile yaz (başlık bağlamlı)", "Dil modeli ile yaz (bağlantı grafikli)"):
        radio = page.get_by_role("radio", name=name, exact=True)
        expect(radio).to_be_disabled()
        expect(page.locator(".method-option").filter(has=radio)).to_contain_text(
            "Bu yöntem bir dil modeli gerektirir ve sunucuda dil modeli ayarlanmamış. "
            "Sistem yöneticisi ayarladığında kullanılabilir olur."
        )
    expect(page.get_by_role("radio", name="Standart", exact=True)).to_be_checked()
    expect(page.get_by_role("radio", name="Yeniden sıralamalı", exact=True)).to_be_enabled()


def test_answer_is_shown_as_cards_with_the_source_passage(page, base_url):
    collection_with_document(page, base_url)
    _ask(page)
    expect(page.locator("#result-title")).to_have_text("Cevap")
    expect(page.locator("#result-title")).to_be_focused()
    expect(page.locator(".answer-text")).to_contain_text("Stok modülü")
    expect(page.locator(".answer-card .note")).to_have_text(
        "Bu cevap, aşağıdaki kaynak paragraftan olduğu gibi alınmıştır."
    )
    expect(page.locator(".answer-card .meta")).to_contain_text("Yöntem: Standart (L2) · Süre:")
    card = page.locator("#cite-1")
    expect(card).to_contain_text("Kaynak 1")
    expect(card).to_contain_text("Belge: ocak.md · Bölüm: Stok")
    expect(card.locator("blockquote")).to_contain_text("Stok modülü performans")
    expect(page.locator("details.trace")).to_have_count(1)


def test_llm_answer_markers_link_to_their_sources(page, base_url):
    collection_with_document(page, base_url)
    _ask(page, method="Dil modeli ile yaz (başlık bağlamlı)")
    expect(page.locator(".answer-card .note")).to_contain_text("Bu cevabı bir dil modeli yazdı.")
    marker = page.get_by_role("button", name="1 numaralı kaynağa git")
    marker.click()
    expect(page.locator("#cite-1")).to_be_focused()
    expect(page.locator("#cite-1")).to_have_attribute("data-active", "true")


# Review Focus 2: a marker without a source and an index such as arr[3] stay plain text.
def test_unknown_markers_stay_plain_text(page, base_url):
    collection_with_document(page, base_url)
    _mock_ask(
        page,
        answer="Metin [1, 2] ve [7] ile arr[3].",
        citations=[
            {
                "number": 1,
                "chunk_id": "x",
                "doc_id": "yok",
                "heading_path": ["Bölüm"],
                "text": "Kaynak metni",
            },
            {
                "number": 2,
                "chunk_id": "y",
                "doc_id": "yok",
                "heading_path": [],
                "text": "Başka metin",
            },
        ],
        trace=[],
        preset="L2",
        latency_ms=5.0,
    )
    _ask(page)
    expect(page.get_by_role("button", name="1 numaralı kaynağa git")).to_have_count(1)
    expect(page.get_by_role("button", name="2 numaralı kaynağa git")).to_have_count(1)
    expect(page.locator(".answer-text")).to_contain_text("[7] ile arr[3].")
    expect(page.locator("#cite-1")).to_contain_text("Belge: bilinmeyen belge · Bölüm: Bölüm")
    expect(page.locator("#cite-2")).to_contain_text("Bölüm: başlıksız")


def test_answer_not_found_is_a_calm_state_with_tips(page, base_url):
    collection_with_document(page, base_url)
    _mock_ask(page, answer=None, citations=[], trace=[], preset="L2", latency_ms=12.0)
    _ask(page)
    expect(page.locator("#result-title")).to_have_text("Belgelerde bu soruya cevap bulunamadı")
    expect(page.locator(".notfound-card li")).to_have_count(3)
    expect(page.locator(".error-card")).to_have_count(0)


@pytest.mark.parametrize(
    ("status", "body", "text"),
    [
        (429, {"detail": "busy"}, "Sistem şu anda başka bir soruyu yanıtlıyor. Birkaç saniye sonra yeniden deneyin."),
        (503, {"detail": "not_ready"}, "Modeller henüz yüklenmedi. Birkaç dakika sonra yeniden deneyin."),
        (503, {"detail": "vector_store_unavailable"}, "Vektör veritabanına (Qdrant) ulaşılamıyor. Birkaç saniye sonra yeniden deneyin."),
        (500, {"detail": "internal_error"}, "Sunucuda beklenmeyen bir hata oluştu. Yeniden deneyin; sürerse sistem yöneticisine bildirin."),
    ],
)  # fmt: skip
def test_errors_are_explained_in_turkish(page, base_url, status, body, text):
    collection_with_document(page, base_url)
    _mock_ask(page, status=status, **body)
    _ask(page)
    card = page.locator("#result .error-card")
    expect(card).to_contain_text("Cevap alınamadı")
    expect(card).to_contain_text(text)
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()


def test_unreachable_server_during_a_question_is_explained(page, base_url):
    collection_with_document(page, base_url)
    page.route("**/api/collections/*/ask", lambda route: route.abort())
    _ask(page)
    expect(page.locator(".error-card")).to_contain_text("Sunucuya ulaşılamadı.")


def test_llm_failure_keeps_the_search_details(page, base_url):
    collection_with_document(page, base_url)
    trace = [
        {
            "stage": "pool",
            "chunk_id": "c1",
            "rank": 1,
            "score": 0.5,
            "score_type": "rrf",
            "channel": "rrf",
        }
    ]
    _mock_ask(page, status=503, detail="llm_unavailable", trace=trace)
    _ask(page, method="Dil modeli ile yaz (başlık bağlamlı)")
    expect(page.locator(".error-card")).to_contain_text("Dil modeli şu anda yanıt vermiyor.")
    page.locator("details.trace summary").click()
    expect(page.locator("details.trace")).to_contain_text("Aday havuzu")
    expect(page.locator("details.trace")).to_contain_text("0,5000")


def test_blank_question_is_explained(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#ask-message")).to_have_text("Lütfen bir soru yazın.")


# Review Focus 4
def test_double_click_sends_one_request(page, base_url):
    collection_with_document(page, base_url)
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/ask") else None)
    page.get_by_label("Sorunuz").fill("Stok modülü")
    page.get_by_role("button", name=ASK).dblclick()
    expect(page.locator("#result-title")).to_be_visible()
    assert len(requests) == 1


# Review Focus 1
def test_passage_text_is_shown_as_text_never_as_html(page, base_url):
    collection_with_document(
        page, base_url, content="# Not\n\nBu paragraf <script>window.__pwned = 1</script> içerir.\n"
    )
    _ask(page, question="paragraf")
    expect(page.locator("#cite-1 blockquote")).to_contain_text(
        "<script>window.__pwned = 1</script>"
    )
    expect(page.locator(".answer-text")).to_contain_text("<script>")
    assert page.evaluate("window.__pwned") is None
