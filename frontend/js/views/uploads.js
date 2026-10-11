// Step 2 upload view: the file input and its lock reason, and one progress row per file.
import { el, byId, setVisible } from "../dom.js";
import { errorMessage } from "../errors.js";
import { formatMegabytes } from "../format.js";
import { t } from "../i18n.js";
import { uploadBlockReason } from "../selectors.js";

const FINISHED = new Set(["done", "duplicate", "failed"]);

function statusText(row) {
  if (row.phase === "failed") {
    return t("upload.phase.failed", { reason: errorMessage(row.errorCode) });
  }
  return t(`upload.phase.${row.phase}`);
}

// Rows are created once and then updated in place, so a live region is not re-announced on
// every progress event.
function createRow(row, actions) {
  const progress = el("progress", {
    attrs: { max: 100, "aria-label": t("upload.progressLabel", { name: row.name }) },
  });
  const percent = el("span", { class: "upload-percent", attrs: { "aria-hidden": "true" } });
  const dismiss = el("button", {
    class: "button button-secondary",
    text: t("upload.dismiss"),
    attrs: { type: "button", "aria-label": t("upload.dismissLabel", { name: row.name }) },
    on: { click: () => actions.uploads.dismiss(row.id) },
  });
  const status = el("p", { class: "upload-status" });
  const item = el(
    "li",
    { class: "upload-row" },
    el("p", { class: "upload-name", text: row.name }),
    status,
    progress,
    percent,
    dismiss,
  );
  return { item, status, progress, percent, dismiss };
}

function updateRow(view, row) {
  view.item.dataset.phase = row.phase;
  const status = statusText(row);
  if (view.status.textContent !== status) view.status.textContent = status;
  const finished = FINISHED.has(row.phase);
  setVisible(view.progress, !finished);
  setVisible(view.percent, row.phase === "sending");
  setVisible(view.dismiss, finished);
  if (row.phase === "sending") {
    view.progress.value = row.percent;
    const text = t("upload.percent", { percent: row.percent });
    if (view.percent.textContent !== text) view.percent.textContent = text;
  } else {
    view.progress.removeAttribute("value"); // no value means an indeterminate bar
  }
}

function renderRows(list, rowViews, uploads, actions) {
  const live = new Set(uploads.map((row) => row.id));
  for (const [id, view] of rowViews) {
    if (!live.has(id)) {
      view.item.remove();
      rowViews.delete(id);
    }
  }
  for (const row of uploads) {
    if (!rowViews.has(row.id)) {
      const view = createRow(row, actions);
      rowViews.set(row.id, view);
      list.append(view.item);
    }
    updateRow(rowViews.get(row.id), row);
  }
}

export function mountUploadsView(store, actions) {
  const input = byId("upload-files");
  const submit = byId("upload-submit");
  const form = byId("upload-form");
  const hint = byId("upload-hint");
  const reason = byId("upload-reason");
  const list = byId("upload-list");
  const rowViews = new Map();

  store.subscribe(
    ({ capabilities }) => {
      if (!capabilities) return;
      input.accept = capabilities.extensions.join(",");
      hint.textContent = t("documents.hint", {
        types: capabilities.extensions.join(", "),
        mb: formatMegabytes(capabilities.max_upload_mb),
      });
    },
    ["capabilities"],
  );

  store.subscribe(
    (state) => {
      const blocked = uploadBlockReason(state);
      input.disabled = blocked !== null;
      submit.disabled = blocked !== null;
      setVisible(reason, blocked !== null);
      reason.textContent = blocked ?? "";
    },
    ["status", "selectedCollectionId"],
  );

  store.subscribe((state) => renderRows(list, rowViews, state.uploads, actions), ["uploads"]);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.uploads.uploadFiles(Array.from(input.files));
    input.value = "";
  });
}
