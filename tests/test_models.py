# tests/test_models.py
from consultqa.models import Chunk


def test_section_id_uses_the_heading_path():
    assert Chunk("d1#0", "d1", 0, ("Giriş", "Kurulum"), "x").section_id == "d1/Giriş > Kurulum"
    assert Chunk("d1#0", "d1", 0, (), "x").section_id == "d1/"


def test_chunk_page_defaults_to_none():
    assert Chunk("d1#0", "d1", 0, (), "x").page is None
    assert Chunk("d1#0", "d1", 0, (), "x", page=3).page == 3
