// The question thread in the answer area: one section per question with its scope, then the busy
// line while it is searched, or the answer card with its sources, the not-found card or the error
// card. The hint line shows while nothing has been asked yet.
//
// The sections are kept between renders: a turn is built again only when it changed, so the node
// that holds the focus is not removed by a later render (a focus moved to a new answer stays there).
import { el, byId, setVisible } from "../dom.js";
import { errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { revealIfHidden } from "../scroll.js";
import { documentNames } from "../selectors.js";
import { renderAnswer } from "./answer.js";

function notFoundCard() {
  return el(
    "article",
    { class: "notfound-card" },
    el("h3", { class: "result-title", attrs: { tabindex: -1 }, text: t("result.notFound.title") }),
    el("p", { text: t("result.notFound.hint") }),
  );
}

// The card always says the same title; the specific sentence follows only when it is different.
function errorCard(result) {
  const title = t("result.error.title");
  const detail = errorMessage(result.code);
  const children = [el("h3", { class: "result-title", attrs: { tabindex: -1 }, text: title })];
  if (detail !== title) children.push(el("p", { class: "error-detail", text: detail }));
  return el("article", { class: "error-card" }, ...children);
}

function renderResult(result, names, onOpenPage) {
  if (result.kind === "answer") return renderAnswer(result, names, onOpenPage);
  if (result.kind === "notFound") return [notFoundCard()];
  return [errorCard(result)];
}

function scopeLine(turn, names) {
  const text = turn.docId
    ? t("thread.scopeDocument", {
        document: names.get(turn.docId) ?? t("result.unknownDocument"),
      })
    : t("thread.scopeFolder");
  return el("p", { class: "turn-scope", text });
}

// The line that shows a question is being searched. It is created empty and its text is set in the
// next frame, once it is in the page, so the polite live region reports the change. The text makes
// the turn taller, so the line is brought into view again then, while it is still the newest turn.
function busyLine() {
  const node = el("p", { class: "turn-busy", attrs: { role: "status" } });
  requestAnimationFrame(() => {
    node.textContent = t("ask.loading");
    const section = node.closest(".turn");
    if (node.isConnected && section?.parentElement?.lastElementChild === section) {
      node.scrollIntoView({ block: "nearest" });
    }
  });
  return node;
}

// A question is shown as text only, whatever it contains.
function turnSection(turn, names, onOpenPage) {
  const children = [el("p", { class: "turn-question", text: turn.question }), scopeLine(turn, names)];
  if (turn.pending) children.push(busyLine());
  else children.push(...renderResult(turn.result, names, onOpenPage).filter(Boolean));
  return el("section", { class: "turn" }, ...children);
}

// The names a turn shows: its own document and the documents of its sources and related pages.
// A turn is built again when one of these names changes.
function nameKeyOf(turn, names) {
  const ids = [turn.docId];
  if (turn.result?.kind === "answer") {
    for (const citation of turn.result.citations) ids.push(citation.doc_id);
    for (const item of turn.result.related ?? []) ids.push(item.doc_id);
  }
  return ids.map((id) => (id ? (names.get(id) ?? "") : "")).join("\u0000");
}

// Says in the answer area that the AI answer mode is not configured, so answers are only passages.
function watchLlmNotice(store) {
  const notice = byId("llm-notice");
  store.subscribe(
    (state) => {
      const off = state.capabilities !== null && state.capabilities.llm_configured === false;
      setVisible(notice, off);
      notice.textContent = off ? t("answer.llmOff") : "";
    },
    ["capabilities"],
  );
}

// Puts the sections in order. Only a section that is not in its place is moved, so the others keep
// their nodes and their focus.
function placeSections(container, sections) {
  const wanted = new Set(sections);
  for (const child of [...container.children]) {
    if (!wanted.has(child)) child.remove();
  }
  sections.forEach((section, index) => {
    if (container.children[index] !== section) {
      container.insertBefore(section, container.children[index] ?? null);
    }
  });
}

// Only the newest turn's error card is an alert, so an old error is not announced again.
function markAlerts(sections) {
  sections.forEach((section, index) => {
    const card = section.querySelector(".error-card");
    if (!card) return;
    if (index === sections.length - 1) card.setAttribute("role", "alert");
    else card.removeAttribute("role");
  });
}

export function mountThreadView(store, actions) {
  const container = byId("result");
  const empty = byId("result-empty");
  const loading = byId("result-loading");
  // The built sections by turn id: { turn, nameKey, lang, node }.
  const built = new Map();
  // The turn whose answer had its focus moved already, and the newest turn that was scrolled to.
  let focusedTurn = null;
  let scrolledTo = null;
  watchLlmNotice(store);
  // The global loading line stays hidden and empty: the pending turn shows its own busy line.
  setVisible(loading, false);
  loading.textContent = "";
  // The container is never busy: a busy container hides its live region changes from screen readers.
  container.removeAttribute("aria-busy");

  // The page is opened through the viewer's action, looked up only when a button is clicked.
  const onOpenPage = (args) => actions.viewer.openPage(args);

  function sectionFor(turn, names, lang) {
    const nameKey = nameKeyOf(turn, names);
    const cached = built.get(turn.id);
    if (cached && cached.turn === turn && cached.nameKey === nameKey && cached.lang === lang) {
      return cached.node;
    }
    const node = turnSection(turn, names, onOpenPage);
    built.set(turn.id, { turn, nameKey, lang, node });
    return node;
  }

  // The hint only. The turns are not touched by this.
  store.subscribe(
    (state) => {
      setVisible(empty, !state.asking && state.thread.length === 0);
    },
    ["asking", "thread"],
  );

  store.subscribe(
    (state) => {
      const names = documentNames(state);
      const sections = state.thread.map((turn) => sectionFor(turn, names, state.lang));
      const live = new Set(state.thread.map((turn) => turn.id));
      for (const id of [...built.keys()]) {
        if (!live.has(id)) built.delete(id);
      }
      placeSections(container, sections);
      markAlerts(sections);

      const last = state.thread.at(-1);
      const lastSection = sections.at(-1);
      if (!last || !lastSection) return;
      // Focus moves to the heading of the newest answer, once, without scrolling.
      if (!last.pending && last.id !== focusedTurn) {
        focusedTurn = last.id;
        lastSection.querySelector(".result-title")?.focus({ preventScroll: true });
        revealIfHidden(byId("step-answer"));
      }
      // The newest turn is kept in view when it is added and when its answer arrives.
      const stage = `${last.id}:${last.pending ? "pending" : "done"}`;
      if (stage !== scrolledTo) {
        scrolledTo = stage;
        lastSection.scrollIntoView({ block: "nearest" });
      }
    },
    ["thread", "documents"],
  );
}
