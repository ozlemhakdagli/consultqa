# tests/test_models.py
from consultqa.models import Chunk


def test_section_id_uses_the_heading_path():
    assert Chunk("d1#0", "d1", 0, ("Giriş", "Kurulum"), "x").section_id == "d1/Giriş > Kurulum"
    assert Chunk("d1#0", "d1", 0, (), "x").section_id == "d1/"
