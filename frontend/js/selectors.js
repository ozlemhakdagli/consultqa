// Pure functions over the state: what is selected, what can be used, and the reason when it cannot.
import { errorMessage } from "./errors.js";
import { t } from "./i18n.js";

export function selectedCollection(state) {
  return state.collections.find((collection) => collection.id === state.selectedCollectionId) ?? null;
}

export function documentNames(state) {
  return new Map(state.documents.map((document) => [document.id, document.filename]));
}

export function isPresetAvailable(capabilities, name) {
  if (!capabilities) return false;
  return capabilities.presets.some((preset) => preset.name === name && preset.available);
}

// The preferred method when it can be used; otherwise the default, otherwise the first available.
export function pickPreset(capabilities, preferred) {
  if (!capabilities) return "";
  const available = capabilities.presets.filter((preset) => preset.available).map((p) => p.name);
  if (available.includes(preferred)) return preferred;
  if (available.includes(capabilities.default_preset)) return capabilities.default_preset;
  return available[0] ?? "";
}

// True while a file of the selected library is still being sent or prepared.
export function hasUnfinishedUpload(state) {
  return state.uploads.some(
    (row) =>
      row.collectionId === state.selectedCollectionId &&
      (row.phase === "sending" || row.phase === "preparing"),
  );
}

// The rows of step 1: the unfinished or failed uploads of the selected library, then its documents.
// A finished upload is not listed, because its document is.
export function documentRows(state) {
  const uploads = state.uploads
    .filter((row) => row.collectionId === state.selectedCollectionId && row.phase !== "done")
    .map((row) => ({
      key: `upload-${row.id}`,
      name: row.name,
      status: row.phase,
      errorCode: row.errorCode,
      uploadId: row.id,
      docId: null,
    }));
  const documents = state.documents.map((doc) => ({
    key: `doc-${doc.id}`,
    name: doc.filename,
    status: "ready",
    errorCode: null,
    uploadId: null,
    docId: doc.id,
  }));
  return [...uploads, ...documents];
}

// The plain status of a row. The finished upload ("done") reads like a ready document.
export function rowStatusText(status, errorCode = null) {
  if (status === "failed") {
    return t("documents.status.failed", { reason: errorMessage(errorCode ?? "unknown") });
  }
  return t(`documents.status.${status === "done" ? "ready" : status}`);
}

// The first unmet prerequisite of step 1, or null when files can be added.
export function uploadBlockReason(state) {
  if (!state.selectedCollectionId) return t("documents.reason.noLibrary");
  if (state.status !== "ready") return t("documents.reason.notReady");
  return null;
}

// The first unmet prerequisite of step 3, or null when a question can be asked.
export function askBlockReason(state) {
  if (!state.selectedCollectionId) return t("ask.reason.noLibrary");
  if (state.status !== "ready") return t("ask.reason.notReady");
  if (state.documentsLoaded && state.documents.length === 0) {
    return t(hasUnfinishedUpload(state) ? "ask.reason.preparing" : "ask.reason.noDocuments");
  }
  if (!isPresetAvailable(state.capabilities, state.selectedPreset)) {
    return t("ask.reason.methodUnavailable");
  }
  return null;
}
