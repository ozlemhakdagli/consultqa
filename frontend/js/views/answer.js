// The answer card and its sources. Each source shows its whole passage. For a single extractive
// answer the sentence that holds the answer is marked, and the answer itself is set in bold.
import { el } from "../dom.js";
import { splitPassage } from "../highlight.js";
import { t } from "../i18n.js";
import { methodKey } from "../methods.js";
import { splitMarkers } from "../markers.js";

// The passage as text, or as text with its answer sentence marked when `parts` is given.
function passageNode(id, text, parts) {
  const attrs = { id: `${id}-text` };
  if (parts === null) return el("blockquote", { class: "source-passage", attrs, text });
  return el(
    "blockquote",
    { class: "source-passage", attrs },
    parts.before,
    el(
      "mark",
      { class: "source-sentence" },
      parts.lead,
      el("strong", { class: "source-answer", text: parts.answer }),
      parts.tail,
    ),
    parts.after,
  );
}

// One source: where the passage came from, then the whole passage, visible at once.
function sourceCard(citation, names, several, parts) {
  const id = `cite-${citation.number}`;
  const heading = several
    ? [el("h4", { text: t("result.sourceHeading", { number: citation.number }) })]
    : [];
  return el(
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
    el("p", { class: "passage-label", text: t("result.passageLabel") }),
    passageNode(id, citation.text, parts),
  );
}

// Marks one source as the active one and moves focus to it.
function showSource(item, cards) {
  for (const other of cards.values()) other.removeAttribute("data-active");
  item.setAttribute("data-active", "true");
  item.focus();
  item.scrollIntoView({ block: "nearest" });
}

function sourcesSection(citations, names, cards, parts) {
  const several = citations.length > 1;
  const list = el("ol", { class: "citation-list" });
  for (const citation of citations) {
    const item = sourceCard(citation, names, several, parts);
    cards.set(citation.number, item);
    list.append(item);
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
    const item = cards.get(number);
    nodes.push(
      item
        ? el("button", {
            class: "marker",
            text: String(number),
            attrs: { type: "button", "aria-label": t("result.markerLabel", { number }) },
            on: { click: () => showSource(item, cards) },
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

// The note says what kind of answer this is. An extractive answer says that its sentence is marked
// only when the answer was found inside the passage.
function noteText(result, parts) {
  if (result.usesLlm) return t("result.llmNote");
  if (result.citations.length === 0) return null;
  return t(parts ? "result.extractiveNote" : "result.extractiveNoteNoMark");
}

// The method is named only when it is not the recommended one, and then only by its plain label.
function methodLine(result) {
  const key = methodKey(result.preset);
  if (result.isRecommended || key === null) return null;
  return t("result.method", { method: t(`method.${key}.label`) });
}

function answerCard(result, cards, parts) {
  const children = [
    el(
      "p",
      { class: "answer-text", attrs: { id: "result-title", tabindex: -1 } },
      ...answerNodes(result.answer, cards),
    ),
  ];
  const note = noteText(result, parts);
  if (note !== null) children.push(el("p", { class: "note", text: note }));
  const method = methodLine(result);
  if (method !== null) children.push(el("p", { class: "meta", text: method }));
  return el("article", { class: "answer-card" }, ...children);
}

// Only a single extractive answer has its sentence split for marking; the others have none.
function markedParts(result) {
  if (result.usesLlm || result.citations.length !== 1) return null;
  return splitPassage(result.citations[0].text, result.answer);
}

// Returns [answer card, sources section]; the sources section is null when there are no sources.
export function renderAnswer(result, names) {
  const cards = new Map();
  const parts = markedParts(result);
  const sources =
    result.citations.length > 0 ? sourcesSection(result.citations, names, cards, parts) : null;
  return [answerCard(result, cards, parts), sources];
}
