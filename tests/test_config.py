# tests/test_config.py
import re
from pathlib import Path

from docrag.config import MODEL_PINS, PRESETS, load_settings


def test_presets_follow_the_ladder():
    assert PRESETS["L2"].use_reranker is False and PRESETS["L2"].use_context is False
    assert PRESETS["L3"].use_reranker is True and PRESETS["L3"].use_context is False
    assert PRESETS["L4"].use_context is True and PRESETS["L4"].neighbours == 1
    assert PRESETS["L4"].use_graph is False
    assert PRESETS["L5"].use_graph is True and PRESETS["L5"].neighbours == 1
    assert PRESETS["L4+llm"].reader == "llm" and PRESETS["L5+llm"].reader == "llm"


def test_model_pins_are_full_commit_hashes():
    for model_id, revision in MODEL_PINS.values():
        assert re.fullmatch(r"[0-9a-f]{40}", revision), model_id


def test_settings_defaults_are_safe():
    settings = load_settings({})
    assert settings.backend == "real"
    assert settings.enable_paper_baseline is False
    assert settings.max_upload_mb == 20
    assert settings.qdrant_url is None


def test_frontend_dir_is_read_from_the_environment():
    assert load_settings({}).frontend_dir is None
    settings = load_settings({"DOCRAG_FRONTEND_DIR": "/app/frontend"})
    assert settings.frontend_dir == Path("/app/frontend")
