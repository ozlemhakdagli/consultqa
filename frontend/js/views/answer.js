// The answer card and the source cards. Citation markers are buttons that move focus to a source.
import { el } from "../dom.js";
import { formatSeconds } from "../format.js";
import { has, t } from "../i18n.js";
import { splitMarkers } from "../markers.js";

function methodLabel(preset) {
  return has(`method.${preset}.label`) ? `${t(`method.${preset}.label`)} (${preset})` : preset;
}

function focusSource(target, cards) {
  for (const card of cards.values()) card.removeAttribute("data-active");
  target.setAttribute("data-active", "true");
  target.focus();
  target.scrollIntoView({ block: "nearest" });
}

function sourceCard(citation, names) {
  return el(
    "li",
    { class: "citation-card", attrs: { id: `cite-${citation.number}`, tabindex: -1 } },
    el("h4", { text: t("result.sourceHeading", { number: citation.number }) }),
    el("p", {
      class: "citation-meta",
      text: t("result.sourceMeta", {
        document: names.get(citation.doc_id) ?? t("result.unknownDocument"),
        section: citation.heading_path.join(" › ") || t("result.noSection"),
      }),
    }),
    el("blockquote", { text: citation.text }),
  );
}

function sourcesSection(citations, names, cards) {
  const list = el("ol", { class: "citation-list" });
  for (const citation of citations) {
    const card = sourceCard(citation, names);
    cards.set(citation.number, card);
    list.append(card);
  }
  return el(
    "section",
    { class: "sources" },
    el("h3", { text: t("result.sourcesTitle") }),
    el("p", { class: "help", text: t("result.sourcesHelp") }),
    list,
  );
}

// A marker keeps only the numbers that have a source as buttons; anything else stays text.
function markerNodes(numbers, cards) {
  if (!numbers.some((number) => cards.has(number))) return [`[${numbers.join(", ")}]`];
  const nodes = ["["];
  numbers.forEach((number, index) => {
    if (index > 0) nodes.push(", ");
    const card = cards.get(number);
    nodes.push(
      card
        ? el("button", {
            class: "marker",
            text: String(number),
            attrs: { type: "button", "aria-label": t("result.markerLabel", { number }) },
            on: { click: () => focusSource(card, cards) },
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

function noteText(result, citationCount) {
  if (result.usesLlm) return t("result.llmNote");
  return citationCount > 0 ? t("result.extractiveNote") : null;
}

function answerCard(result, cards) {
  const children = [
    el("h3", { attrs: { id: "result-title", tabindex: -1 }, text: t("result.answerTitle") }),
    el("p", { class: "answer-text" }, ...answerNodes(result.answer, cards)),
  ];
  const note = noteText(result, result.citations.length);
  if (note !== null) children.push(el("p", { class: "note", text: note }));
  children.push(
    el("p", {
      class: "meta",
      text: t("result.meta", {
        method: methodLabel(result.preset),
        seconds: formatSeconds(result.latencyMs),
      }),
    }),
  );
  return el("article", { class: "answer-card" }, ...children);
}

// Returns [answer card, sources section]; the sources section is null when there are no sources.
export function renderAnswer(result, names) {
  const cards = new Map();
  const sources = result.citations.length > 0 ? sourcesSection(result.citations, names, cards) : null;
  return [answerCard(result, cards), sources];
}
