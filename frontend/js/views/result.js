// Step 3 result area: a loading line, then the answer card with its sources, the not-found card or
// the error card. The hint line shows while nothing has been asked yet.
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
    el("h3", { attrs: { id: "result-title", tabindex: -1 }, text: t("result.notFound.title") }),
    el("p", { text: t("result.notFound.hint") }),
  );
}

// The card always says the same title; the specific sentence follows only when it is different.
function errorCard(result) {
  const title = t("result.error.title");
  const detail = errorMessage(result.code);
  const children = [el("h3", { attrs: { id: "result-title", tabindex: -1 }, text: title })];
  if (detail !== title) children.push(el("p", { class: "error-detail", text: detail }));
  return el("article", { class: "error-card", attrs: { role: "alert" } }, ...children);
}

function renderResult(result, names) {
  if (result.kind === "answer") return renderAnswer(result, names);
  if (result.kind === "notFound") return [notFoundCard()];
  return [errorCard(result)];
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

export function mountResultView(store) {
  const container = byId("result");
  const empty = byId("result-empty");
  const loading = byId("result-loading");
  let shown = null;
  watchLlmNotice(store);

  store.subscribe(
    (state) => {
      setVisible(empty, !state.asking && !state.result);
      setVisible(loading, state.asking);
      loading.textContent = state.asking ? t("ask.loading") : "";
      container.setAttribute("aria-busy", String(state.asking));
      // While a question is searched the previous answer stays in place, dimmed.
      if (state.asking) return;
      const fresh = state.result !== shown;
      shown = state.result;
      const nodes = state.result ? renderResult(state.result, documentNames(state)) : [];
      container.replaceChildren(...nodes.filter(Boolean));
      // Focus moves to the heading only for a new result, and without scrolling; then the panel is
      // brought into view once, if it is not in view already.
      if (fresh && state.result) {
        container.querySelector("#result-title")?.focus({ preventScroll: true });
        revealIfHidden(byId("step-answer"));
      }
    },
    ["asking", "result", "documents"],
  );
}
