// Documents pane drop area: the file button, drag and drop, the file types and why it may be locked.
import { byId, setVisible } from "../dom.js";
import { formatFileTypes, formatMegabytes } from "../format.js";
import { t } from "../i18n.js";
import { uploadBlockReason } from "../selectors.js";

export function mountDropzoneView(store, actions) {
  const dropzone = byId("dropzone");
  const input = byId("upload-files");
  const hint = byId("upload-hint");
  const reason = byId("upload-reason");
  let locked = false;

  store.subscribe(
    ({ capabilities }) => {
      if (!capabilities) return;
      input.accept = capabilities.extensions.join(",");
      hint.textContent = t("documents.hint", {
        types: formatFileTypes(capabilities.extensions),
        mb: formatMegabytes(capabilities.max_upload_mb),
      });
    },
    ["capabilities"],
  );

  store.subscribe(
    (state) => {
      const blocked = uploadBlockReason(state);
      locked = blocked !== null;
      input.disabled = locked;
      dropzone.dataset.disabled = String(locked);
      setVisible(reason, locked);
      reason.textContent = blocked ?? "";
    },
    ["status", "selectedCollectionId"],
  );

  input.addEventListener("change", () => {
    const files = Array.from(input.files);
    input.value = "";
    actions.uploads.uploadFiles(files);
  });

  const setDragging = (on) => dropzone.classList.toggle("is-dragging", on);
  for (const type of ["dragenter", "dragover"]) {
    dropzone.addEventListener(type, (event) => {
      event.preventDefault();
      setDragging(true);
    });
  }
  dropzone.addEventListener("dragleave", () => setDragging(false));
  dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    setDragging(false);
    if (!locked) actions.uploads.uploadFiles(Array.from(event.dataTransfer.files));
  });

  // A file dropped beside the drop area must not make the browser open it instead of the page.
  window.addEventListener("dragover", (event) => event.preventDefault());
  window.addEventListener("drop", (event) => event.preventDefault());
}
