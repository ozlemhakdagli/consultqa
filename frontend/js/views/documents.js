// Step 2 document list: the documents of the selected collection, with a two-step delete.
import { el, byId, setVisible, showMessage } from "../dom.js";
import { formatDateTime } from "../format.js";
import { t } from "../i18n.js";

function deleteControl(doc, state, actions) {
  if (state.confirmDeleteId !== doc.id) {
    return el("button", {
      class: "button button-danger",
      text: t("documents.delete"),
      attrs: { type: "button", "aria-label": t("documents.deleteLabel", { name: doc.filename }) },
      on: { click: () => actions.documents.requestDelete(doc.id) },
    });
  }
  const confirm = el("button", {
    class: "button button-danger",
    text: t("documents.confirmYes"),
    attrs: { type: "button" },
    on: { click: () => actions.documents.confirmDelete(doc.id) },
  });
  const cancel = el("button", {
    class: "button button-secondary",
    text: t("documents.confirmNo"),
    attrs: { type: "button" },
    on: { click: () => actions.documents.cancelDelete() },
  });
  return el(
    "p",
    { class: "doc-confirm", attrs: { role: "alert" } },
    t("documents.confirmQuestion", { name: doc.filename }),
    " ",
    confirm,
    " ",
    cancel,
  );
}

function documentRow(doc, state, actions) {
  return el(
    "li",
    { class: "doc-row" },
    el("span", { class: "doc-name", text: doc.filename }),
    el("span", { class: "doc-date", text: t("documents.added", { date: formatDateTime(doc.created_at) }) }),
    deleteControl(doc, state, actions),
  );
}

export function mountDocumentsView(store, actions) {
  const title = byId("documents-title");
  const empty = byId("documents-empty");
  const list = byId("document-list");
  const message = byId("documents-message");
  let openedConfirmId = "";

  store.subscribe(
    (state) => {
      const hasCollection = state.selectedCollectionId !== "";
      title.textContent = t("documents.listTitle", { count: state.documents.length });
      setVisible(title, hasCollection && state.documentsLoaded);
      setVisible(list, hasCollection);
      let emptyText = null;
      if (!state.documentsLoaded) emptyText = t("documents.loading");
      else if (state.documents.length === 0) emptyText = t("documents.empty");
      setVisible(empty, hasCollection && emptyText !== null);
      empty.textContent = emptyText ?? "";
      list.replaceChildren(...state.documents.map((doc) => documentRow(doc, state, actions)));
      // Focus moves to the cancel button only when a confirmation opens, not on later re-renders.
      if (state.confirmDeleteId && state.confirmDeleteId !== openedConfirmId) {
        list.querySelector(".doc-confirm .button-secondary")?.focus();
      }
      openedConfirmId = state.confirmDeleteId;
    },
    ["documents", "documentsLoaded", "selectedCollectionId", "confirmDeleteId"],
  );

  store.subscribe((state) => showMessage(message, state.documentsMessage), ["documentsMessage"]);
}
