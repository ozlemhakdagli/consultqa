"""Static checks of the three-pane workspace: the DOM contract in frontend/index.html, the tabs,
the viewer toolbar and the class contract that the stylesheets must cover."""

import re
from html.parser import HTMLParser
from pathlib import Path

from frontend_strings import EN_JS, TR_JS, keys

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
CSS_FILES = sorted((FRONTEND / "css").glob("*.css"))

KEPT_IDS = [
    "system-chip",
    "language-switch",
    "theme-switch",
    "system-banner",
    "library-notice",
    "dropzone",
    "upload-files",
    "upload-hint",
    "upload-reason",
    "documents-title",
    "documents-empty",
    "document-list",
    "documents-live",
    "documents-message",
    "question",
    "ask-form",
    "ask-submit",
    "ask-message",
    "ask-reason",
    "ask-tip",
    "example-list",
    "examples-title",
    "result",
    "result-empty",
    "result-loading",
    "llm-notice",
    "advanced",
    "method-fieldset",
    "method-list",
    "collection-select",
    "collection-form",
    "collection-name",
    "collection-name-help",
    "collection-create",
    "collection-message",
    "folder-list",
    "folder-list-title",
    "folder-title",
]
NEW_IDS = [
    "pane-tabs",
    "tab-documents",
    "tab-viewer",
    "tab-chat",
    "pane-documents",
    "pane-viewer",
    "pane-chat",
    "step-documents",
    "step-answer",
    "step-ask",
    "scope-switch",
    "scope-document",
    "scope-folder",
    "scope-note",
    "viewer-title",
    "viewer-toolbar",
    "viewer-page",
    "viewer-page-count",
    "viewer-zoom-out",
    "viewer-zoom-in",
    "viewer-fit",
    "viewer-canvas",
    "viewer-text",
    "viewer-empty",
    "viewer-message",
    "selection-ask",
]
# Classes that Tasks 11 and 12 create; the stylesheets must style every one of them.
CLASS_CONTRACT = [
    "turn",
    "turn-question",
    "turn-scope",
    "page-button",
    "related-pages",
    "related-list",
    "viewer-pdf",
    "viewer-text",
    "viewer-message",
    "pdf-highlight",
    "doc-open",
    "doc-row-open",
    "selection-ask-button",
]
PANE_IDS = ["pane-documents", "pane-viewer", "pane-chat"]
SKIPPED_TAGS = {"script", "style", "title", "noscript"}


class _Tags(HTMLParser):
    """Records every start tag, in document order, with its attributes."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _tags() -> list[tuple[str, dict[str, str | None]]]:
    parser = _Tags()
    parser.feed((FRONTEND / "index.html").read_text(encoding="utf-8"))
    return parser.tags


def _by_id(tags, element_id):
    found = [(tag, attrs) for tag, attrs in tags if attrs.get("id") == element_id]
    assert len(found) == 1, f"#{element_id} appears {len(found)} times"
    return found[0]


def _css() -> str:
    return "".join(path.read_text(encoding="utf-8") for path in CSS_FILES)


def test_every_contract_id_exists_exactly_once():
    tags = _tags()
    ids = [attrs["id"] for _, attrs in tags if "id" in attrs]
    for element_id in KEPT_IDS + NEW_IDS:
        assert ids.count(element_id) == 1, element_id


def test_every_text_key_exists_in_both_languages():
    used = {
        attrs[name]
        for _, attrs in _tags()
        for name in ("data-text", "data-placeholder")
        if name in attrs
    }
    assert used
    assert used <= keys(TR_JS), sorted(used - keys(TR_JS))
    assert used <= keys(EN_JS), sorted(used - keys(EN_JS))


def test_the_tabs_are_aria_tabs_that_control_a_pane():
    tags = _tags()
    tab_row = _by_id(tags, "pane-tabs")
    assert tab_row[0] == "nav" and tab_row[1]["role"] == "tablist"
    for tab_id, pane_id in (
        ("tab-documents", "pane-documents"),
        ("tab-viewer", "pane-viewer"),
        ("tab-chat", "pane-chat"),
    ):
        tag, attrs = _by_id(tags, tab_id)
        assert tag == "button", tab_id
        assert attrs["role"] == "tab", tab_id
        assert attrs["aria-controls"] == pane_id, tab_id
        assert _by_id(tags, pane_id)[1]["role"] == "tabpanel", pane_id
        assert attrs.get("data-text", "").startswith("panes."), tab_id


def test_the_panes_are_in_order_and_the_chat_pane_holds_the_answer_then_the_question():
    tags = _tags()
    order = [attrs.get("id") for _, attrs in tags]
    positions = [order.index(pane) for pane in PANE_IDS]
    assert positions == sorted(positions)
    chat = order.index("pane-chat")
    assert order.index("step-answer") > chat
    assert order.index("scope-switch") > order.index("step-answer")
    assert order.index("step-ask") > order.index("scope-switch")
    assert order.index("ask-form") > order.index("step-ask")
    assert order.index("step-documents") < order.index("pane-viewer")
    assert order.index("advanced") > order.index("step-documents")


def test_the_viewer_toolbar_controls_are_real_controls():
    tags = _tags()
    assert _by_id(tags, "viewer-toolbar")[0] == "div"
    tag, attrs = _by_id(tags, "viewer-page")
    assert tag == "input" and attrs["type"] == "number"
    for control in ("viewer-zoom-out", "viewer-zoom-in", "viewer-fit"):
        tag, attrs = _by_id(tags, control)
        assert tag == "button" and attrs["type"] == "button", control
        assert attrs.get("data-text", "").startswith("viewer."), control
    assert _by_id(tags, "viewer-text")[0] == "pre"
    assert _by_id(tags, "viewer-canvas")[0] == "div"


def test_the_floating_ask_button_and_the_empty_viewer_parts_start_hidden():
    tags = _tags()
    tag, attrs = _by_id(tags, "selection-ask")
    assert tag == "button" and attrs["type"] == "button" and "hidden" in attrs
    assert "hidden" in _by_id(tags, "viewer-text")[1]
    assert "hidden" in _by_id(tags, "viewer-message")[1]


def test_the_scope_switch_is_a_fieldset_of_two_radios_named_scope():
    tags = _tags()
    assert _by_id(tags, "scope-switch")[0] == "fieldset"
    for radio_id, value in (("scope-document", "document"), ("scope-folder", "folder")):
        tag, attrs = _by_id(tags, radio_id)
        assert tag == "input" and attrs["type"] == "radio", radio_id
        assert attrs["name"] == "scope" and attrs["value"] == value, radio_id


def test_the_chat_pane_heading_and_the_independent_line_use_their_keys():
    tags = _tags()
    pane_chat = [attrs.get("id") for _, attrs in tags].index("pane-chat")
    within = [attrs.get("data-text") for _, attrs in tags[pane_chat:]]
    assert "panes.chat" in within
    assert "thread.independent" in within


def test_step_numbers_are_gone():
    html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    assert "step-number" not in html
    assert "step-number" not in _css()


def test_no_inline_style_script_or_event_attribute():
    for tag, attrs in _tags():
        assert "style" not in attrs, tag
        assert not [name for name in attrs if name.startswith("on")], tag
        if tag == "script":
            assert "src" in attrs, "inline script"


def test_the_pdfjs_stylesheet_is_linked_from_the_vendored_copy():
    hrefs = [attrs["href"] for tag, attrs in _tags() if tag == "link"]
    assert "/vendor/pdfjs/pdf_viewer.css" in hrefs
    assert (FRONTEND / "vendor" / "pdfjs" / "pdf_viewer.css").is_file()


def test_every_class_of_the_contract_is_styled():
    css = _css()
    for name in CLASS_CONTRACT:
        assert re.search(rf"\.{re.escape(name)}(?![\w-])", css), name


def test_the_styles_use_tokens_only_and_no_hard_coded_colours():
    for path in CSS_FILES:
        if path.name == "tokens.css":
            continue
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", text), path.name
        assert not re.search(r"\b(rgba?|hsla?)\(", text), path.name


def test_the_tabs_are_hidden_and_all_panes_show_from_1000_px():
    css = _css()
    wide = re.search(r"@media \(min-width: 1000px\)\s*{(.*?)\n}", css, re.S)
    assert wide is not None
    assert ".pane-tabs" in wide.group(1) and "display: none" in wide.group(1)
    narrow = re.search(r"@media \(max-width: 999\.98px\)\s*{(.*?)\n}", css, re.S)
    assert narrow is not None
    assert 'data-pane-active="false"' in narrow.group(1)


def test_the_floating_button_is_fixed_to_the_viewport():
    # Task 12 places it with viewport coordinates, so it must not scroll inside its pane.
    rule = re.search(r"\.selection-ask-button\s*{(.*?)}", _css(), re.S)
    assert rule is not None
    assert "position: fixed;" in rule.group(1)


def test_each_pane_is_a_focus_target_for_a_programmatic_switch():
    tags = _tags()
    for pane_id in PANE_IDS:
        assert _by_id(tags, pane_id)[1].get("tabindex") == "-1", pane_id


def test_the_answer_area_is_a_named_region():
    tags = _tags()
    tag, attrs = _by_id(tags, "step-answer")
    assert tag == "section"  # a section with a name is a region landmark
    assert attrs["aria-labelledby"] == "step-answer-title"
    assert _by_id(tags, "step-answer-title")[0] == "h3"


def test_heading_levels_never_skip_a_level():
    levels = [int(tag[1]) for tag, _ in _tags() if re.fullmatch(r"h[1-6]", tag)]
    assert levels[0] == 1
    assert all(later <= earlier + 1 for earlier, later in zip(levels[:-1], levels[1:], strict=True))


def test_the_answer_area_keeps_a_floor_of_8rem_on_the_desktop_chat_pane():
    css = _css()
    wide = re.search(r"@media \(min-width: 1000px\)\s*{(.*?)\n}", css, re.S)
    assert wide is not None
    rule = re.search(r"\.pane-chat \.answer-area\s*{(.*?)}", wide.group(1), re.S)
    assert rule is not None and "min-height: 8rem" in rule.group(1)
    assert "overflow-y: auto" in rule.group(1)


def test_the_question_box_is_three_rows_and_the_hints_sit_in_the_answer_area():
    tags = _tags()
    assert _by_id(tags, "question")[1]["rows"] == "3"
    order = [attrs.get("id") for _, attrs in tags]
    answer = order.index("step-answer")
    ask = order.index("step-ask")
    for hint in ("ask-tip", "example-list"):
        assert answer < order.index(hint) < ask, hint
    assert order.index("ask-submit") > ask


def test_the_answer_area_is_not_a_tab_stop():
    assert _by_id(_tags(), "step-answer")[1]["tabindex"] == "-1"


def test_dead_and_duplicate_rules_are_gone():
    css = _css()
    assert "aria-busy" not in css
    assert not re.search(r"(?<![\w-])\.card h2\b", css)
    assert len(re.findall(r"\.viewer-toolbar label\s*{", css)) == 1


def test_the_highlight_is_a_translucent_wash_with_no_text_colour():
    rule = re.search(
        r"(?<![\w-])\.pdf-highlight\s*,?\s*\.textLayer \.pdf-highlight\s*{(.*?)}", _css(), re.S
    )
    assert rule is not None
    body = rule.group(1)
    assert "color-mix(in srgb, var(--mark-bg)" in body and "transparent)" in body
    assert not re.search(r"(?<![\w-])color:", body)


def test_the_tab_keys_leave_browser_shortcuts_alone():
    text = (FRONTEND / "js" / "views" / "panes.js").read_text(encoding="utf-8")
    assert "event.altKey || event.ctrlKey || event.metaKey" in text
