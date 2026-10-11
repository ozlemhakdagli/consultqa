// Use case of the language switch: choose a language, then render the page again in it.
import { chooseLanguage } from "../i18n.js";

export function createLanguageActions({ store, collections }) {
  function choose(code) {
    const applied = chooseLanguage(code);
    // Notices are cleared rather than translated, and a pending delete is cancelled: its question
    // would otherwise stay in the old language under the user's eyes.
    store.set({
      lang: applied,
      askMessage: "",
      collectionMessage: null,
      documentsMessage: null,
      documentsAnnouncement: "",
      confirmDeleteId: "",
    });
    // A library list that failed to load is requested again, so its error comes back translated.
    if (!store.get().collectionsLoaded) collections.loadCollections();
  }

  return { choose };
}
