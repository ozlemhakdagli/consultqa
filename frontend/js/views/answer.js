// The answer card and its sources. A citation marker is a button that shows its source passage.
import { el } from "../dom.js";
import { t } from "../i18n.js";
import { methodKey } from "../methods.js";
import { splitMarkers } from "../markers.js";

// One source: where the passage came from, and a button that shows or hides the passage text.
function sourceCard(citation, names, several) {
  const id = `cite-${citation.number}`;
  const passage = el("blockquote", {
    class: "source-passage",
    attrs: { id: `${id}-text` },
    text: citation.text,
  });
  passage.hidden = true;
  const toggle = el("button", {
    class: "button button-secondary",
    text: t("result.showPassage"),
    attrs: { type: "button", "aria-controls": `${id}-text`, "aria-expanded": "false" },
  });
  const setOpen = (open) => {
    passage.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = t(open ? "result.hidePassage" : "result.showPassage");
  };
  toggle.addEventListener("click", () => setOpen(passage.hidden));
  const heading = several
    ? [el("h4", { text: t("result.sourceHeading", { number: citation.number }) })]
    : [];
  const item = el(
    "li",
    { class: "citation-card", attrs: { id, tabindex: -1 } },
    ...heading,
    el("p", {
      class: "citation-meta",
      text: t("result.sourceDocument", {
        document: names.get(citation.doc_id) ?? t("result.unknownDocument"),
      }),
    }),
    el("p", {
      class: "citation-meta",
      text: t("result.sourceSection", {
        section: citation.heading_path.join(" › ") || t("result.noSection"),
      }),
    }),
    toggle,
    passage,
  );
  return { item, open: setOpen };
}

// Marks one source as the active one, shows its passage and moves focus to it.
function showSource(source, cards) {
  for (const other of cards.values()) other.item.removeAttribute("data-active");
  source.item.setAttribute("data-active", "true");
  source.open(true);
  source.item.focus();
  source.item.scrollIntoView({ block: "nearest" });
}

function sourcesSection(citations, names, cards) {
  const several = citations.length > 1;
  const list = el("ol", { class: "citation-list" });
  for (const citation of citations) {
    const source = sourceCard(citation, names, several);
    cards.set(citation.number, source);
    list.append(source.item);
  }
  const title = t(several ? "result.sourceTitleMany" : "result.sourceTitleOne");
  return el("section", { class: "sources" }, el("h3", { text: title }), list);
}

// A marker keeps only the numbers that have a source as buttons; anything else stays text.
function markerNodes(numbers, cards) {
  if (!numbers.some((number) => cards.has(number))) return [`[${numbers.join(", ")}]`];
  const nodes = ["["];
  numbers.forEach((number, index) => {
    if (index > 0) nodes.push(", ");
    const source = cards.get(number);
    nodes.push(
      source
        ? el("button", {
            class: "marker",
            text: String(number),
            attrs: { type: "button", "aria-label": t("result.markerLabel", { number }) },
            on: { click: () => showSource(source, cards) },
          })
        : String(number),
    );
  });
  nodes.push("]");
  return nodes;
}

function answerNodes(answer, cards) {
  return splitMarkers(answer).flatMap((part) =>
    part.type === "text" ? [part.value] : markerNodes(part.numbers, cards),
  );
}

function noteText(result) {
  if (result.usesLlm) return t("result.llmNote");
  return result.citations.length > 0 ? t("result.extractiveNote") : null;
}

// The method is named only when it is not the recommended one, and then only by its plain label.
function methodLine(result) {
  const key = methodKey(result.preset);
  if (result.isRecommended || key === null) return null;
  return t("result.method", { method: t(`method.${key}.label`) });
}

function answerCard(result, cards) {
  const children = [
    el(
      "p",
      { class: "answer-text", attrs: { id: "result-title", tabindex: -1 } },
      ...answerNodes(result.answer, cards),
    ),
  ];
  const note = noteText(result);
  if (note !== null) children.push(el("p", { class: "note", text: note }));
  const method = methodLine(result);
  if (method !== null) children.push(el("p", { class: "meta", text: method }));
  return el("article", { class: "answer-card" }, ...children);
}

// Returns [answer card, sources section]; the sources section is null when there are no sources.
export function renderAnswer(result, names) {
  const cards = new Map();
  const sources =
    result.citations.length > 0 ? sourcesSection(result.citations, names, cards) : null;
  return [answerCard(result, cards), sources];
}
