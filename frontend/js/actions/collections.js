// Use cases of the library: choose the one the page works in, list, create and select folders.
import { ApiError, errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { getPref, setPref } from "../prefs.js";

export function createCollectionActions({ api, store, documents }) {
  // The first of the asked, current and remembered folders that still exists wins.
  function keptId(collections, preferredId) {
    const ids = new Set(collections.map((collection) => collection.id));
    const current = store.get().selectedCollectionId;
    const remembered = getPref("collection");
    return [preferredId, current, remembered].find((id) => id && ids.has(id)) ?? "";
  }

  // Without a kept folder the page uses the folder named "Belgelerim", creating it when missing.
  // A 409 means another tab created it first: that is not an error, the existing one is used.
  async function defaultLibrary(collections) {
    const name = t("library.defaultName");
    const existing = collections.find((collection) => collection.name === name);
    if (existing) return { collections, id: existing.id };
    try {
      const created = await api.createCollection(name);
      return { collections: await api.listCollections(), id: created.id };
    } catch (error) {
      if (!(error instanceof ApiError) || error.code !== "collection_exists") throw error;
      const listed = await api.listCollections();
      const match = listed.find((collection) => collection.name === name);
      return { collections: listed, id: match?.id ?? "" };
    }
  }

  async function loadCollections(preferredId = "") {
    try {
      const listed = await api.listCollections();
      const kept = keptId(listed, preferredId);
      const { collections, id } = kept
        ? { collections: listed, id: kept }
        : await defaultLibrary(listed);
      const patch = { collections, collectionsLoaded: true };
      if (!store.get().collectionsLoaded) patch.documentsMessage = null;
      store.set(patch);
      if (id !== store.get().selectedCollectionId) await selectCollection(id);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ documentsMessage: { kind: "error", text: errorMessage(error.code) } });
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
