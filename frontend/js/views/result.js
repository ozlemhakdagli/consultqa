// Step 3 result area: a loading line, then the answer card with its sources, the not-found card or
// the error card. The hint line shows while nothing has been asked yet.
import { el, byId, setVisible } from "../dom.js";
import { errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { documentNames } from "../selectors.js";
import { renderAnswer } from "./answer.js";

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
    ),
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

export function mountResultView(store) {
  const container = byId("result");
  const empty = byId("result-empty");
  let shown = null;

  store.subscribe(
    (state) => {
      setVisible(empty, !state.asking && !state.result);
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
