// Use cases of the document list: load it, and delete a document after a confirmation.
import { ApiError, errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { VIEWER_CLOSED } from "../state.js";

// The folder list shows how many documents each folder has. The list just loaded is the newer
// count, so the chosen folder takes it; the list is kept as it is when the count did not change.
function withCount(collections, collectionId, count) {
  const chosen = collections.find((collection) => collection.id === collectionId);
  if (!chosen || chosen.document_count === count) return collections;
  return collections.map((collection) =>
    collection.id === collectionId ? { ...collection, document_count: count } : collection,
  );
}

export function createDocumentActions({ api, store }) {
  // A response for a collection that is no longer selected is dropped, never shown.
  async function loadDocuments() {
    const collectionId = store.get().selectedCollectionId;
    try {
      const documents = await api.listDocuments(collectionId);
      if (store.get().selectedCollectionId !== collectionId) return;
      // A replaced or deleted document is no longer listed: the viewer then returns to empty.
      const openId = store.get().openDocId;
      const openGone = openId !== "" && !documents.some((document) => document.id === openId);
      store.set({
        documents,
        documentsLoaded: true,
        collections: withCount(store.get().collections, collectionId, documents.length),
        ...(openGone ? VIEWER_CLOSED : {}),
      });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      if (store.get().selectedCollectionId !== collectionId) return;
      store.set({
        documents: [],
        documentsLoaded: true,
        documentsMessage: { kind: "error", text: errorMessage(error.code) },
      });
    }
  }

  function requestDelete(id) {
    store.set({ confirmDeleteId: id });
  }

  function cancelDelete() {
    store.set({ confirmDeleteId: "" });
  }

  async function confirmDelete(id) {
    const collectionId = store.get().selectedCollectionId;
    const name = store.get().documents.find((document) => document.id === id)?.filename ?? "";
    try {
      await api.deleteDocument(collectionId, id);
      // The viewer is reset only when the open document is the one deleted.
      const viewerReset = store.get().openDocId === id ? VIEWER_CLOSED : {};
      store.set({
        confirmDeleteId: "",
        thread: [],
        ...viewerReset,
        documentsMessage: { kind: "info", text: t("documents.deleted", { name }) },
      });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({
        confirmDeleteId: "",
        documentsMessage: { kind: "error", text: errorMessage(error.code) },
      });
      if (error.code !== "document_not_found") return;
    }
    await loadDocuments();
  }

  return { loadDocuments, requestDelete, cancelDelete, confirmDelete };
}
