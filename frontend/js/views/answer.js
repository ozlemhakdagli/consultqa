// The answer card and its sources. Each source shows its whole passage. For a single extractive
// answer the sentence that holds the answer is marked, and the answer itself is set in bold.
import { el } from "../dom.js";
import { splitPassage } from "../highlight.js";
import { t } from "../i18n.js";
import { methodKey } from "../methods.js";
import { splitMarkers } from "../markers.js";

// The passage as text, or as text with its answer sentence marked when `parts` is given.
function passageNode(text, parts) {
  if (parts === null) return el("blockquote", { class: "source-passage", text });
  return el(
    "blockquote",
    { class: "source-passage" },
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

// The button that opens a page of a document. Its text is the sentence the answer came from, when
// there is one; otherwise the whole answer.
function pageButton(docId, page, names, text, onOpenPage) {
  const documentName = names.get(docId) ?? t("result.unknownDocument");
  return el("button", {
    class: "page-button",
    text: t("result.pageButton", { page }),
    attrs: {
      type: "button",
      "aria-label": t("result.pageButtonLabel", { document: documentName, page }),
    },
    on: { click: () => onOpenPage({ docId, page, text }) },
  });
}

// The marked sentence as plain text: the words before the answer, the answer and the words after it.
function markedSentence(parts) {
  return `${parts.lead}${parts.answer}${parts.tail}`;
}

// One source: where the passage came from, then the whole passage, visible at once.
function sourceCard(citation, names, several, parts, context) {
  const heading = several
    ? [el("h4", { text: t("result.sourceHeading", { number: citation.number }) })]
    : [];
  const hasPage = citation.page != null;
  const pageLines = hasPage
    ? [
        el("p", { class: "citation-meta", text: t("result.sourcePage", { page: citation.page }) }),
        pageButton(
          citation.doc_id,
          citation.page,
          names,
          parts ? markedSentence(parts) : context.answer,
          context.onOpenPage,
        ),
      ]
    : [];
  return el(
    "li",
    { class: "citation-card", attrs: { tabindex: -1 } },
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
    ...pageLines,
    el("p", { class: "passage-label", text: t("result.passageLabel") }),
    passageNode(citation.text, parts),
  );
}

// Marks one source as the active one and moves focus to it.
function showSource(item, cards) {
  for (const other of cards.values()) other.removeAttribute("data-active");
  item.setAttribute("data-active", "true");
  item.focus();
  item.scrollIntoView({ block: "nearest" });
}

function sourcesSection(citations, names, cards, parts, context) {
  const several = citations.length > 1;
  const list = el("ol", { class: "citation-list" });
  for (const citation of citations) {
    const item = sourceCard(citation, names, several, parts, context);
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
      { class: "answer-text result-title", attrs: { tabindex: -1 } },
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

// The pages related to the question, each page once. Pages that are not known are left out.
// The document name is shown only when the list spans more than one document.
function relatedSection(related, names, onOpenPage) {
  const seen = new Set();
  const pages = [];
  for (const item of related) {
    if (item.page == null) continue;
    const key = `${item.doc_id}:${item.page}`;
    if (seen.has(key)) continue;
    seen.add(key);
    pages.push(item);
  }
  if (pages.length === 0) return null;
  const several = new Set(pages.map((item) => item.doc_id)).size > 1;
  const items = pages.map((item) => {
    const documentName = names.get(item.doc_id) ?? t("result.unknownDocument");
    const label = several
      ? t("result.relatedLabel", { document: documentName, page: item.page })
      : t("result.pageButton", { page: item.page });
    return el(
      "li",
      {},
      el("button", {
        class: "page-button",
        text: label,
        attrs: {
          type: "button",
          // The name starts with the visible text: the visible label, or for one document the
          // "Page n" text followed by the document.
          "aria-label": several
            ? label
            : t("result.pageButtonLabel", { document: documentName, page: item.page }),
        },
        on: { click: () => onOpenPage({ docId: item.doc_id, page: item.page, text: null }) },
      }),
    );
  });
  return el(
    "section",
    { class: "related-pages" },
    el("h3", { text: t("result.relatedTitle") }),
    el("ul", { class: "related-list" }, ...items),
  );
}

// Returns [answer card, sources section, related section]. A section is null when it is empty.
// onOpenPage({ docId, page, text }) is called by a page button.
export function renderAnswer(result, names, onOpenPage = () => {}) {
  const cards = new Map();
  const parts = markedParts(result);
  const context = { answer: result.answer, onOpenPage };
  const sources =
    result.citations.length > 0
      ? sourcesSection(result.citations, names, cards, parts, context)
      : null;
  const related = relatedSection(result.related ?? [], names, onOpenPage);
  return [answerCard(result, cards, parts), sources, related];
}
