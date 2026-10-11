"""Tests for turning update-report text into structured records."""

from hybrid_qa.pdf_extraction import parse_document

SAMPLE_TEXT = """VERSİYON GÜNCELLEME
Ürün Versiyon: V4.23.07.26
Güncel Versiyon İle Gelen Yenilikler
Ürün Web Geliştirmeleri
1.
Envanter Aracı Envanter form sayfasındaki harita için arama alanı eklendi
2.
Proje Aracı Proje sayfası İlgili İşlemlere "Dışa aktar" işlem seçeneği
eklendi
Ürün Mobil Geliştirmeleri
1. Mobil uygulamada bildirim ekranı iyileştirildi
"""


def test_parse_document_reads_version_and_updates():
    document = parse_document(SAMPLE_TEXT, doc_id="document_1")

    assert document["id"] == "document_1"
    assert document["version_info"]["version"] == "V4.23.07.26"
    assert [u["id"] for u in document["updates"]] == ["update_1", "update_2", "update_3"]
    assert (
        document["updates"][0]["description"]
        == "Envanter Aracı Envanter form sayfasındaki harita için arama alanı eklendi"
    )


def test_wrapped_lines_are_joined_into_one_update():
    document = parse_document(SAMPLE_TEXT, doc_id="document_1")

    assert document["updates"][1]["description"].endswith("işlem seçeneği eklendi")


def test_text_without_version_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_document("Gelen Yenilikler\n1. Bir şey eklendi", doc_id="document_1")
