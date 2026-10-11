"""Readers of the two page dictionaries (frontend/js/strings-tr.js and strings-en.js)."""

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
TR_JS = FRONTEND / "js" / "strings-tr.js"
EN_JS = FRONTEND / "js" / "strings-en.js"
LANGUAGE_FILES = {"tr": TR_JS, "en": EN_JS}
_KEY = re.compile(r'^\s*"([A-Za-z0-9_.+-]+)":', re.MULTILINE)
_LINE = re.compile(r'^\s*"([^"]+)":\s*"(.*)",\s*$')


def keys(path: Path) -> set[str]:
    return set(_KEY.findall(path.read_text(encoding="utf-8")))


def values(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {m.group(1): m.group(2) for line in lines if (m := _LINE.match(line))}


def placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", text))
