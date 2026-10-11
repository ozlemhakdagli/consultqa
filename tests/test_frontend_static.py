"""Static checks of frontend/: they need no browser and no Node."""

import re
from html.parser import HTMLParser
from pathlib import Path

from consultqa.config import PRESETS

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
JS_FILES = sorted(FRONTEND.rglob("*.js"))
STRINGS_JS = FRONTEND / "js" / "strings.js"
BACKEND_SOURCES = [
    "src/consultqa/api/routes.py",
    "src/consultqa/api/app.py",
    "src/consultqa/api/services.py",
    "src/consultqa/ingest/parse.py",
    "src/consultqa/ingest/pipeline.py",
]
# Every way the backend writes an error code; the test below fails if one stops matching.
CODE_PATTERNS = [
    r'detail="([a-z_]+)"',
    r'"detail": "([a-z_]+)"',
    r'_error\(\d+, "([a-z_]+)"\)',
    r'"failed", "([a-z_]+)"',
    r'ParseError\("([a-z_]+)"\)',
    r'_ERROR = "([a-z_]+)"',
]
CLIENT_CODES = {"network_error", "file_empty", "job_timeout"}
FORBIDDEN_APIS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
)
TURKISH_LETTERS = re.compile("[çğıöşüÇĞİÖŞÜ]")
IMPORT = re.compile(r"""(?:from\s+|import\s*\(\s*)["'](\.{1,2}/[^"']+)["']""")


def _string_keys() -> set[str]:
    text = STRINGS_JS.read_text(encoding="utf-8")
    return set(re.findall(r'^\s*"([A-Za-z0-9_.+-]+)":', text, re.MULTILINE))


def test_every_error_code_of_the_api_has_a_turkish_message():
    found: set[str] = set()
    for source in BACKEND_SOURCES:
        text = (ROOT / source).read_text(encoding="utf-8")
        for pattern in CODE_PATTERNS:
            found.update(re.findall(pattern, text))
    contract = {
        "validation_error",
        "busy",
        "not_ready",
        "llm_unavailable",
        "collection_not_found",
        "collection_exists",
        "document_not_found",
        "file_too_large",
        "unsupported_type",
        "preset_unavailable",
        "unknown_preset",
        "parse_failed",
        "no_text",
        "interrupted",
        "vector_store_unavailable",
        "too_many_pages",
        "internal_error",
        "job_not_found",
    }
    assert contract <= found  # the scan still sees the whole contract
    keys = _string_keys()
    missing = sorted(code for code in found | CLIENT_CODES if f"error.{code}" not in keys)
    assert missing == [] and "error.unknown" in keys


def test_every_preset_is_offered_with_plain_copy_or_deliberately_hidden():
    text = (FRONTEND / "js" / "methods.js").read_text(encoding="utf-8")
    catalog = set(re.findall(r'preset: "([^"]+)"', text))
    hidden_list = re.search(r"HIDDEN_PRESETS = Object\.freeze\(\[([^\]]*)\]\)", text)
    assert hidden_list is not None
    hidden = set(re.findall(r'"([^"]+)"', hidden_list.group(1)))
    assert set(PRESETS) | {"paper"} == catalog | hidden
    assert catalog & hidden == set()
    keys = _string_keys()
    for key in re.findall(r'key: "([^"]+)"', text):
        for part in ("label", "summary", "note"):
            assert f"method.{key}.{part}" in keys, f"method.{key}.{part}"


def test_scripts_never_build_html_from_text():
    for path in JS_FILES:
        text = path.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN_APIS:
            assert forbidden not in text, f"{path.name} uses {forbidden}"


def test_relative_imports_resolve():
    for path in JS_FILES:
        for target in IMPORT.findall(path.read_text(encoding="utf-8")):
            assert (path.parent / target).resolve().is_file(), f"{path.name} imports {target}"


def test_turkish_text_lives_only_in_strings_js():
    for path in JS_FILES:
        if path != STRINGS_JS:
            assert not TURKISH_LETTERS.search(path.read_text(encoding="utf-8")), path.name


SKIPPED_TAGS = {"script", "style", "title", "noscript"}
TEXT_PAIRS = [
    ("text", "bg"),
    ("text", "surface"),
    ("text", "field"),
    ("text", "code-bg"),
    ("muted", "surface"),
    ("muted", "bg"),
    ("muted", "code-bg"),
    ("accent-text", "accent"),
    ("accent", "surface"),
    ("accent", "code-bg"),
    ("error", "surface"),
    ("error", "error-bg"),
    ("ok", "surface"),
    ("ok", "ok-bg"),
    ("warn", "warn-bg"),
    ("info", "info-bg"),
    ("disabled-text", "surface"),
    ("mark-text", "mark-bg"),
]


class _Page(HTMLParser):
    """Collects the visible text, the tags and the attributes of index.html."""

    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self._skipped = 0

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag in SKIPPED_TAGS:
            self._skipped += 1

    def handle_endtag(self, tag):
        if tag in SKIPPED_TAGS:
            self._skipped -= 1

    def handle_data(self, data):
        if self._skipped == 0 and data.strip():
            self.text.append(data.strip())


def _page() -> _Page:
    page = _Page()
    page.feed((FRONTEND / "index.html").read_text(encoding="utf-8"))
    return page


def _luminance(colour: str) -> float:
    channels = [int(colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def _light_and_dark() -> tuple[dict[str, str], dict[str, str]]:
    css = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
    pairs = re.findall(
        r"--([a-z-]+):\s*light-dark\((#[0-9a-fA-F]{6}),\s*(#[0-9a-fA-F]{6})\)\s*;", css
    )
    return {n: light for n, light, _ in pairs}, {n: dark for n, _, dark in pairs}


def test_index_html_is_a_shell_without_visible_text():
    page = _page()
    # Step numbers are digits, not language; every word comes from strings.js at run time.
    assert [text for text in page.text if not text.isdigit()] == []
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert '<html lang="tr">' in html
    scripts = [attrs for tag, attrs in page.tags if tag == "script"]
    assert [s.get("src") for s in scripts] == ["/js/theme-init.js", "/js/main.js"]
    assert scripts[1]["type"] == "module"
    assert not {"type", "defer", "async"} & set(scripts[0])
    for tag, attrs in page.tags:
        assert "style" not in attrs, tag
        assert not [name for name in attrs if name.startswith("on")], tag


def test_every_static_text_key_exists_in_strings():
    used = {
        attrs[name]
        for _, attrs in _page().tags
        for name in ("data-text", "data-placeholder")
        if name in attrs
    }
    assert used and used <= _string_keys()


def test_the_four_stylesheets_are_linked_in_order():
    hrefs = [a["href"] for tag, a in _page().tags if tag == "link" and a.get("rel") == "stylesheet"]
    assert hrefs == ["/css/tokens.css", "/css/base.css", "/css/layout.css", "/css/components.css"]
    assert all((FRONTEND / href.lstrip("/")).is_file() for href in hrefs)


def test_text_contrast_of_the_tokens_meets_wcag_aa():
    for scheme, tokens in zip(("light", "dark"), _light_and_dark(), strict=True):
        for foreground, background in TEXT_PAIRS:
            ratio = _contrast(tokens[foreground], tokens[background])
            assert ratio >= 4.5, (scheme, foreground, background, round(ratio, 2))


def test_every_colour_token_has_a_light_and_a_dark_value():
    css = (FRONTEND / "css" / "tokens.css").read_text(encoding="utf-8")
    assert not re.search(r"--[a-z-]+:\s*#[0-9a-fA-F]{6}\s*;", css)
    assert re.search(r':root\[data-theme="light"\]\s*{\s*color-scheme: light;', css)
    assert re.search(r':root\[data-theme="dark"\]\s*{\s*color-scheme: dark;', css)
    light, dark = _light_and_dark()
    assert light and set(light) == set(dark)


def test_the_early_theme_script_runs_before_the_stylesheets_and_shares_the_key():
    names = [a.get("src") or a.get("href") for tag, a in _page().tags if tag in ("script", "link")]
    assert names.index("/js/theme-init.js") < names.index("/css/tokens.css")
    assert "consultqa.theme" in (FRONTEND / "js" / "theme-init.js").read_text(encoding="utf-8")
    assert 'getPref("theme")' in (FRONTEND / "js" / "theme.js").read_text(encoding="utf-8")
    assert 'PREFIX = "consultqa."' in (FRONTEND / "js" / "prefs.js").read_text(encoding="utf-8")


def test_reduced_motion_is_respected():
    css = "".join(p.read_text(encoding="utf-8") for p in (FRONTEND / "css").glob("*.css"))
    assert "prefers-reduced-motion" in css


def test_the_page_flow_is_in_reading_order():
    page = _page()
    ids = [a["id"] for tag, a in page.tags if tag in ("section", "details") and "id" in a]
    assert ids[:4] == ["step-documents", "step-ask", "step-answer", "advanced"]
    advanced = next(a for tag, a in page.tags if tag == "details" and a.get("id") == "advanced")
    assert "open" not in advanced  # closed by default


DYNAMIC_PREFIXES = (
    "error.",
    "method.",
    "documents.status.",
    "system.chip.",
    "system.banner.",
)


def test_no_string_is_unused():
    """Keys built at run time are matched by prefix; every other key must be referenced."""
    sources = "".join(
        path.read_text(encoding="utf-8")
        for path in [*JS_FILES, FRONTEND / "index.html"]
        if path != STRINGS_JS
    )
    unused = [
        key
        for key in sorted(_string_keys())
        if not key.startswith(DYNAMIC_PREFIXES) and f'"{key}"' not in sources
    ]
    assert unused == [], unused
