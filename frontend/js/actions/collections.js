// Use cases of step 1: list, create and select collections.
import { ApiError, errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { getPref, setPref } from "../prefs.js";

export function createCollectionActions({ api, store, documents }) {
  function pickId(collections, preferredId) {
    const ids = new Set(collections.map((collection) => collection.id));
    const current = store.get().selectedCollectionId;
    const remembered = getPref("collection");
    const candidate = [preferredId, current, remembered].find((id) => id && ids.has(id));
    return candidate ?? collections[0]?.id ?? "";
  }

  async function loadCollections(preferredId = "") {
    try {
      const collections = await api.listCollections();
      const id = pickId(collections, preferredId);
      store.set({ collections, collectionsLoaded: true });
      if (id !== store.get().selectedCollectionId) await selectCollection(id);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ collectionMessage: { kind: "error", text: errorMessage(error.code) } });
    }
  }

  async function createCollection(name) {
    const trimmed = name.trim();
    if (!trimmed) {
      store.set({ collectionMessage: { kind: "error", text: t("collection.nameRequired") } });
      return false;
    }
    try {
      const created = await api.createCollection(trimmed);
      await loadCollections(created.id);
      store.set({
        collectionMessage: { kind: "info", text: t("collection.created", { name: trimmed }) },
      });
      return true;
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ collectionMessage: { kind: "error", text: errorMessage(error.code) } });
      return false;
    }
  }

  // Switching collection clears everything that belonged to the previous one.
  async function selectCollection(id) {
    if (!id) return;
    store.set({
      selectedCollectionId: id,
      documents: [],
      documentsLoaded: false,
      documentsMessage: null,
      confirmDeleteId: "",
      result: null,
      askMessage: "",
    });
    setPref("collection", id);
    await documents.loadDocuments();
  }

  return { loadCollections, createCollection, selectCollection };
}
