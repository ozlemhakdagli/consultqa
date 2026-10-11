// Pure functions over the state: what is selected, what can be used, and the reason when it cannot.
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

// The first unmet prerequisite of step 2, or null when files can be uploaded.
export function uploadBlockReason(state) {
  if (!state.selectedCollectionId) return t("documents.reason.noCollection");
  if (state.status !== "ready") return t("documents.reason.notReady");
  return null;
}

// The first unmet prerequisite of step 3, or null when a question can be asked.
export function askBlockReason(state) {
  if (!state.selectedCollectionId) return t("ask.reason.noCollection");
  if (state.status !== "ready") return t("ask.reason.notReady");
  if (state.documentsLoaded && state.documents.length === 0) {
    return t("ask.reason.noDocuments");
  }
  if (!isPresetAvailable(state.capabilities, state.selectedPreset)) {
    return t("ask.reason.methodUnavailable");
  }
  return null;
}
