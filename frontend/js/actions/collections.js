// Use cases of the library: choose the one the page works in, list, create and select folders.
import { DEFAULT_LIBRARY_NAME } from "../config.js";
import { ApiError, errorMessage } from "../errors.js";
import { t } from "../i18n.js";
import { isReservedLibraryName, libraryLabel } from "../libraries.js";
import { removePref } from "../prefs.js";

export function createCollectionActions({ api, store, documents }) {
  // An older page remembered a folder here. The page always opens on the default library now.
  removePref("collection");

  // The first of the asked and current folders that still exists wins.
  function keptId(collections, preferredId) {
    const ids = new Set(collections.map((collection) => collection.id));
    const current = store.get().selectedCollectionId;
    return [preferredId, current].find((id) => id && ids.has(id)) ?? "";
  }

  // Without a kept folder the page uses the default library, creating it when missing. Its stored
  // name is the same in every language. A 409 means another tab created it first: that is not an
  // error, the existing one is used.
  async function defaultLibrary(collections) {
    const name = DEFAULT_LIBRARY_NAME;
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
    if (isReservedLibraryName(trimmed)) {
      store.set({ collectionMessage: { kind: "error", text: t("collection.nameReserved") } });
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

  // Deletes a folder with its documents. The folder list is refreshed afterwards. When the folder
  // in use was the one deleted, the page moves to the default library, creating it when missing.
  async function deleteCollection(collection) {
    const wasSelected = collection.id === store.get().selectedCollectionId;
    try {
      await api.deleteCollection(collection.id);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ collectionMessage: { kind: "error", text: errorMessage(error.code) } });
      return false;
    }
    await loadCollections();
    if (!wasSelected) await documents.loadDocuments();
    store.set({
      collectionMessage: {
        kind: "info",
        text: t("collection.deleted", { name: libraryLabel(collection) }),
      },
    });
    return true;
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
    await documents.loadDocuments();
  }

  return { loadCollections, createCollection, selectCollection, deleteCollection };
}
