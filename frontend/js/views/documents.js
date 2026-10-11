// Step 1 document list: the unfinished, failed and ready documents of the selected library in one
// list. Each row has its plain status and one button: "Sil" for a ready document, "Kapat" for a
// failed or duplicate upload.
import { el, byId, setVisible, showMessage } from "../dom.js";
import { t } from "../i18n.js";
import { libraryLabel } from "../libraries.js";
import { documentRows, rowStatusText, selectedCollection } from "../selectors.js";

// A ready document is deleted in two steps: the first click asks, the second one deletes.
function deleteControl(row, state, actions) {
  if (state.confirmDeleteId !== row.docId) {
    return el("button", {
      class: "button button-danger",
      text: t("documents.delete"),
      attrs: { type: "button", "aria-label": t("documents.deleteLabel", { name: row.name }) },
      on: { click: () => actions.documents.requestDelete(row.docId) },
    });
  }
  const confirm = el("button", {
    class: "button button-danger",
    text: t("documents.confirmYes"),
    attrs: { type: "button" },
    on: { click: () => actions.documents.confirmDelete(row.docId) },
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
    t("documents.confirmQuestion", { name: row.name }),
    " ",
    confirm,
    " ",
    cancel,
  );
}

function dismissButton(row, actions) {
  return el("button", {
    class: "button button-secondary",
    text: t("documents.dismiss"),
    attrs: { type: "button", "aria-label": t("documents.dismissLabel", { name: row.name }) },
    on: { click: () => actions.uploads.dismiss(row.uploadId) },
  });
}

function documentRow(row, state, actions) {
  const main = [
    el("p", { class: "doc-name", text: row.name }),
    el("p", { class: "doc-status", text: rowStatusText(row.status, row.errorCode) }),
  ];
  if (row.status === "sending" || row.status === "preparing") {
    // No value attribute: an indeterminate bar, since the page has no honest measure of progress.
    const label = t("documents.progressLabel", { name: row.name });
    main.push(el("progress", { attrs: { "aria-label": label } }));
  }
  if (row.status === "preparing") {
    main.push(el("p", { class: "doc-note", text: t("documents.preparingNote") }));
  }
  const children = [el("div", { class: "doc-main" }, ...main)];
  if (row.status === "ready") children.push(deleteControl(row, state, actions));
  if (row.status === "duplicate" || row.status === "failed") {
    children.push(dismissButton(row, actions));
  }
  return el("li", { class: "doc-row", attrs: { "data-status": row.status } }, ...children);
}

export function mountDocumentsView(store, actions) {
  const title = byId("documents-title");
  const empty = byId("documents-empty");
  const list = byId("document-list");
  const message = byId("documents-message");
  const live = byId("documents-live");
  let openedConfirmId = "";

  store.subscribe(
    (state) => {
      const hasLibrary = state.selectedCollectionId !== "";
      const rows = documentRows(state);
      title.textContent = t("documents.listTitle", {
        name: libraryLabel(selectedCollection(state)),
        count: state.documents.length,
      });
      setVisible(title, state.documents.length > 0);
      let emptyText = null;
      if (!state.documentsLoaded) emptyText = t("documents.loading");
      else if (rows.length === 0) emptyText = t("documents.empty");
      setVisible(empty, hasLibrary && emptyText !== null);
      empty.textContent = emptyText ?? "";
      setVisible(list, hasLibrary);
      list.replaceChildren(...rows.map((row) => documentRow(row, state, actions)));
      // Focus moves to the cancel button only when a confirmation opens, not on later re-renders.
      if (state.confirmDeleteId && state.confirmDeleteId !== openedConfirmId) {
        list.querySelector(".doc-confirm .button-secondary")?.focus();
      }
      openedConfirmId = state.confirmDeleteId;
    },
    [
      "uploads",
      "documents",
      "documentsLoaded",
      "selectedCollectionId",
      "collections",
      "confirmDeleteId",
    ],
  );

  store.subscribe(
    (state) => {
      live.textContent = state.documentsAnnouncement;
    },
    ["documentsAnnouncement"],
  );
  store.subscribe((state) => showMessage(message, state.documentsMessage), ["documentsMessage"]);
}
