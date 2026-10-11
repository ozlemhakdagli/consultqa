import pytest
from playwright.sync_api import expect
from ui_helpers import (
    caps_without_llm,
    choose_method,
    collection_with_document,
    mock_collections_unavailable,
    new_library,
    open_advanced,
    open_page,
    upload_text,
)

pytestmark = pytest.mark.e2e

ASK = "Cevabı bul"


def _ask(page, question="Stok modülü", method=None):
    if method:
        choose_method(page, method)
    page.get_by_label("Sorunuz", exact=True).fill(question)
    page.get_by_role("button", name=ASK).click()


def _mock_ask(page, status=200, **body):
    page.route("**/api/collections/*/ask", lambda route: route.fulfill(status=status, json=body))


def test_ask_is_locked_and_says_why(page, base_url):
    mock_collections_unavailable(page)
    open_page(page, base_url, library=False)
    expect(page.get_by_role("button", name=ASK)).to_be_disabled()
    expect(page.locator("#ask-reason")).to_have_text(
        "Belge alanı henüz hazır değil. Birkaç saniye bekleyin; olmazsa sayfayı yenileyin."
    )
    page.unroute("**/api/collections")
    new_library(page, base_url)
    open_page(page, base_url)
    expect(page.locator("#ask-reason")).to_have_text("Soru sormak için önce bir belge ekleyin.")
    upload_text(page, "ocak.md")
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()
    expect(page.locator("#ask-reason")).to_be_hidden()


def test_only_the_recommended_mode_is_chosen_until_advanced_options_are_opened(page, base_url):
    open_page(page, base_url)
    assert page.evaluate("document.getElementById('advanced').open") is False
    expect(page.locator("#advanced").get_by_role("radio")).to_have_count(0)  # closed section


def test_methods_have_plain_names_and_the_recommended_one_is_selected(page, base_url):
    open_page(page, base_url)
    open_advanced(page)
    expect(page.locator("#method-list input[type=radio]")).to_have_count(5)
    expect(page.locator("#method-list .method-title")).to_have_text(
        [
            "Hızlı ve doğru",
            "Bulunanları bir kez daha kontrol eder",
            "Bölüm başlıklarına da bakar",
            "Birbiriyle ilgili bölümleri de tarar",
            "Yapay zekâ ile yazılmış cevap",
        ]
    )
    fast = page.get_by_role("radio", name="Hızlı ve doğru", exact=True)
    expect(fast).to_be_checked()
    option = page.locator(".method-option").filter(has=fast)
    expect(option).to_contain_text("Önerilen")
    expect(option).to_contain_text(
        "Belgelerinizde sorunuza en uygun yeri bulur ve cevabı oradan alır."
    )
    other = page.locator(".method-option").filter(has_text="Bulunanları bir kez daha kontrol eder")
    expect(other).to_contain_text("“Hızlı ve doğru” yöntemden daha iyi sonuç vermedi")


def test_the_ai_mode_is_disabled_with_a_plain_reason_when_it_is_not_configured(page, base_url):
    caps = caps_without_llm(page, base_url)
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    open_advanced(page)
    ai = page.get_by_role("radio", name="Yapay zekâ ile yazılmış cevap", exact=True)
    expect(ai).to_be_disabled()
    expect(page.locator(".method-option").filter(has=ai)).to_contain_text(
        "Bu özellik bu sistemde henüz açık değil."
    )
    expect(page.get_by_role("radio", name="Hızlı ve doğru", exact=True)).to_be_checked()
    expect(
        page.get_by_role("radio", name="Bölüm başlıklarına da bakar", exact=True)
    ).to_be_enabled()


def test_a_preset_the_page_does_not_know_is_never_shown(page, base_url):
    caps = page.request.get(base_url + "/api/capabilities").json()
    caps["presets"].append({"name": "L9+x", "available": True, "reason": None, "uses_llm": False})
    page.route("**/api/capabilities", lambda route: route.fulfill(json=caps))
    open_page(page, base_url)
    open_advanced(page)
    expect(page.locator("#method-list input[type=radio]")).to_have_count(
        5
    )  # L5+llm and L9+x hidden
    expect(page.locator("#method-list")).not_to_contain_text("L9")


def test_the_chosen_mode_is_not_remembered_after_a_reload(page, base_url):
    open_page(page, base_url)
    choose_method(page, "Bölüm başlıklarına da bakar")
    page.reload()
    expect(page.locator("#system-chip")).to_have_text("Sistem hazır")
    open_advanced(page)
    expect(page.get_by_role("radio", name="Hızlı ve doğru", exact=True)).to_be_checked()


def test_example_questions_fill_the_box_without_asking(page, base_url):
    collection_with_document(page, base_url)
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/ask") else None)
    expect(page.locator("#example-list button")).to_have_text(
        [
            "Garanti süresi kaç yıldır?",
            "Başvuru için hangi belgeler gerekir?",
            "Teslimat ne kadar sürer?",
        ]
    )
    expect(page.locator("#examples-title")).to_have_text(
        "Örnek sorular (kendi belgenize göre değiştirin):"
    )
    expect(page.locator("#ask-tip")).to_have_text(
        "İpucu: Belgede geçen kelimelerle, tek bir bilgiyi soran kısa bir soru yazın."
    )
    page.get_by_role("button", name="Garanti süresi kaç yıldır?").click()
    expect(page.get_by_label("Sorunuz", exact=True)).to_have_value("Garanti süresi kaç yıldır?")
    expect(page.get_by_label("Sorunuz", exact=True)).to_be_focused()
    assert requests == []


def test_asking_is_explained_while_the_first_document_is_prepared(page, base_url):
    new_library(page, base_url)
    open_page(page, base_url)
    page.route(
        "**/api/jobs/*",
        lambda route: route.fulfill(
            json={"state": "embedding", "error": None, "document_id": "pending"}
        ),
    )
    upload_text(page, "ocak.md")
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    expect(page.locator("#ask-reason")).to_have_text(
        "Belgeniz hazırlanıyor. Hazır olunca soru sorabilirsiniz."
    )
    expect(page.get_by_role("button", name=ASK)).to_be_disabled()
    page.unroute("**/api/jobs/*")
    expect(page.get_by_role("button", name=ASK)).to_be_enabled(timeout=20_000)
    expect(page.locator("#ask-reason")).to_be_hidden()
    expect(page.get_by_label("Sorunuz", exact=True)).to_have_value("Stok modülü")


def test_a_blank_question_is_explained_and_the_message_goes_away_when_typing(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#ask-message")).to_have_text("Lütfen bir soru yazın.")
    page.get_by_role("button", name="Teslimat ne kadar sürer?").click()
    expect(page.locator("#ask-message")).to_be_hidden()


def test_the_answer_shows_its_text_then_the_source_in_full(page, base_url):
    collection_with_document(page, base_url)
    expect(page.locator("#result-empty")).to_have_text("Cevabınız burada görünecek.")
    _ask(page)
    expect(page.locator("#result-empty")).to_be_hidden()
    expect(page.locator("#result-title")).to_contain_text("Stok modülü")
    expect(page.locator("#result-title")).to_be_focused()
    expect(page.locator(".answer-card .note")).to_have_text(
        "Bu cevap belgedeki bu cümleden alındı. Cevap kısa olabilir; tam bağlam için kaynak metnine bakın."
    )
    expect(page.locator(".answer-card .meta")).to_have_count(0)
    expect(page.get_by_role("heading", name="Cevabın kaynağı")).to_be_visible()
    card = page.locator("#cite-1")
    expect(card).to_contain_text("Belge: ocak.md")
    expect(card).to_contain_text("Bölüm: Stok")
    expect(card.get_by_role("heading", level=4)).to_have_count(0)
    expect(page.locator("#cite-1-text")).to_be_visible()
    expect(page.locator("#cite-1-text")).to_contain_text("Stok modülü performans")
    expect(page.get_by_role("button", name="Kaynağın metnini göster")).to_have_count(0)
    expect(page.locator("details.trace")).to_have_count(0)


def test_ai_answer_names_its_mode_and_markers_open_their_sources(page, base_url):
    collection_with_document(page, base_url)
    _ask(page, method="Yapay zekâ ile yazılmış cevap")
    expect(page.locator(".answer-card .note")).to_contain_text("Bu cevabı yapay zekâ yazdı.")
    expect(page.locator(".answer-card .meta")).to_have_text(
        "Kullanılan yöntem: Yapay zekâ ile yazılmış cevap"
    )
    page.get_by_role("button", name="1. kaynağa git").click()
    expect(page.locator("#cite-1")).to_be_focused()
    expect(page.locator("#cite-1")).to_have_attribute("data-active", "true")
    expect(page.locator("#cite-1-text")).to_be_visible()


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
    expect(page.get_by_role("button", name="1. kaynağa git")).to_have_count(1)
    expect(page.get_by_role("button", name="2. kaynağa git")).to_have_count(1)
    expect(page.locator(".answer-text")).to_contain_text("[7] ile arr[3].")
    expect(page.get_by_role("heading", name="Cevabın kaynakları")).to_be_visible()
    expect(page.locator("#cite-1")).to_contain_text("Belge: bilinmiyor")
    expect(page.locator("#cite-1")).to_contain_text("Bölüm: Bölüm")
    expect(page.locator("#cite-2")).to_contain_text("Bölüm: belirtilmemiş")
    expect(page.get_by_role("heading", name="Kaynak 1")).to_be_visible()
    expect(page.get_by_role("heading", name="Kaynak 2")).to_be_visible()


def test_answer_not_found_is_a_calm_state_with_one_hint(page, base_url):
    collection_with_document(page, base_url)
    _mock_ask(page, answer=None, citations=[], trace=[], preset="L2", latency_ms=12.0)
    _ask(page)
    expect(page.locator("#result-title")).to_have_text(
        "Bu sorunun cevabı yüklediğiniz belgelerde yok."
    )
    expect(page.locator(".notfound-card p")).to_have_text(
        "Sorunuzu belgede geçen kelimelere daha yakın yazmayı deneyin."
    )
    expect(page.locator(".notfound-card li")).to_have_count(0)
    expect(page.locator(".error-card")).to_have_count(0)


@pytest.mark.parametrize(
    ("status", "body", "text"),
    [
        (429, {"detail": "busy"}, "Sistem şu anda başka bir soruyu yanıtlıyor. Birkaç saniye sonra tekrar deneyin."),
        (503, {"detail": "not_ready"}, "Sistem hâlâ açılıyor. Birkaç dakika sonra tekrar deneyin."),
        (503, {"detail": "vector_store_unavailable"}, "Belgelerin saklandığı bölüme şu anda ulaşılamıyor. Birkaç saniye sonra tekrar deneyin."),
        (500, {"detail": "internal_error"}, None),
    ],
)  # fmt: skip
def test_errors_are_explained_in_turkish(page, base_url, status, body, text):
    collection_with_document(page, base_url)
    _mock_ask(page, status=status, **body)
    _ask(page)
    card = page.locator("#result .error-card")
    expect(card).to_contain_text("Bir sorun oluştu. Lütfen tekrar deneyin.")
    if text is None:
        expect(page.locator("#result .error-detail")).to_have_count(0)
    else:
        expect(card.locator(".error-detail")).to_have_text(text)
    expect(page.get_by_role("button", name=ASK)).to_be_enabled()


def test_unreachable_server_during_a_question_is_explained(page, base_url):
    collection_with_document(page, base_url)
    page.route("**/api/collections/*/ask", lambda route: route.abort())
    _ask(page)
    expect(page.locator(".error-card")).to_contain_text("Uygulamaya bağlanılamadı.")


def test_ai_failure_is_explained_and_shows_no_search_details(page, base_url):
    collection_with_document(page, base_url)
    trace = [{"stage": "pool", "chunk_id": "c1", "rank": 1, "score": 0.5, "score_type": "rrf"}]
    _mock_ask(page, status=503, detail="llm_unavailable", trace=trace)
    _ask(page, method="Yapay zekâ ile yazılmış cevap")
    expect(page.locator(".error-card .error-detail")).to_contain_text(
        "Yapay zekâ şu anda yanıt vermiyor."
    )
    expect(page.locator("details.trace")).to_have_count(0)


def test_blank_question_is_explained(page, base_url):
    collection_with_document(page, base_url)
    page.get_by_role("button", name=ASK).click()
    expect(page.locator("#ask-message")).to_have_text("Lütfen bir soru yazın.")


# Review Focus 4
def test_double_click_sends_one_request(page, base_url):
    collection_with_document(page, base_url)
    requests = []
    page.on("request", lambda r: requests.append(r.url) if r.url.endswith("/ask") else None)
    page.get_by_label("Sorunuz", exact=True).fill("Stok modülü")
    page.get_by_role("button", name=ASK).dblclick()
    expect(page.locator("#result-title")).to_be_visible()
    assert len(requests) == 1


# Review Focus 1
def test_passage_text_is_shown_as_text_never_as_html(page, base_url):
    collection_with_document(
        page, base_url, content="# Not\n\nBu paragraf <script>window.__pwned = 1</script> içerir.\n"
    )
    _ask(page, question="paragraf")
    expect(page.locator("#cite-1-text")).to_be_visible()
    expect(page.locator("#cite-1-text")).to_contain_text("<script>window.__pwned = 1</script>")
    expect(page.locator(".answer-text")).to_contain_text("<script>")
    assert page.evaluate("window.__pwned") is None
