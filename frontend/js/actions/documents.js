// Use cases of the document list: load it, and delete a document after a confirmation.
import { ApiError, errorMessage } from "../errors.js";
import { t } from "../i18n.js";

export function createDocumentActions({ api, store }) {
  // A response for a collection that is no longer selected is dropped, never shown.
  async function loadDocuments() {
    const collectionId = store.get().selectedCollectionId;
    try {
      const documents = await api.listDocuments(collectionId);
      if (store.get().selectedCollectionId !== collectionId) return;
      store.set({ documents, documentsLoaded: true });
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
      store.set({
        confirmDeleteId: "",
        result: null,
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
