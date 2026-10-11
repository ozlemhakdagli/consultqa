// Step 3 result area: a loading line, then the answer cards, the not-found card or the error card.
import { el, byId } from "../dom.js";
import { errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { documentNames } from "../selectors.js";
import { renderAnswer } from "./answer.js";
import { renderTrace } from "./trace.js";

function notFoundCard() {
  return el(
    "article",
    { class: "notfound-card" },
    el("h3", { attrs: { id: "result-title", tabindex: -1 }, text: t("result.notFound.title") }),
    el("p", { text: t("result.notFound.body") }),
    el(
      "ul",
      {},
      el("li", { text: t("result.notFound.tip1") }),
      el("li", { text: t("result.notFound.tip2") }),
      el("li", { text: t("result.notFound.tip3") }),
    ),
  );
}

function errorCard(result) {
  return el(
    "article",
    { class: "error-card", attrs: { role: "alert" } },
    el("h3", { attrs: { id: "result-title", tabindex: -1 }, text: t("result.error.title") }),
    el("p", { text: errorMessage(result.code) }),
  );
}

function renderResult(result, names) {
  if (result.kind === "answer") return [...renderAnswer(result, names), renderTrace(result.trace)];
  if (result.kind === "notFound") return [notFoundCard(), renderTrace(result.trace)];
  return [errorCard(result), renderTrace(result.trace)];
}

export function mountResultView(store) {
  const container = byId("result");
  let shown = null;

  store.subscribe(
    (state) => {
      container.setAttribute("aria-busy", String(state.asking));
      if (state.asking) {
        container.replaceChildren(
          el("p", { class: "loading", attrs: { role: "status" }, text: t("ask.loading") }),
        );
        return;
      }
      const fresh = state.result !== shown;
      shown = state.result;
      const nodes = state.result ? renderResult(state.result, documentNames(state)) : [];
      container.replaceChildren(...nodes.filter(Boolean));
      // Focus moves to the heading only for a new result, not when the documents list changes.
      if (fresh && state.result) container.querySelector("#result-title")?.focus();
    },
    ["asking", "result", "documents"],
  );
}
