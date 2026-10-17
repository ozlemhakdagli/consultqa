// Use cases of the viewer: open a document, open a page with the sentence to mark, change the page,
// and clear the mark. Each one only sets state; the viewer view does the rest.
import { VIEWER_CLOSED } from "../state.js";

export function createViewerActions({ store }) {
  // Each open gets a new navigation token, so the viewer moves to the page again even when the
  // page and the sentence are the ones it was last moved to.
  let navigations = 0;

  // A page and the sentence of an answer on it. Without a sentence nothing is marked.
  function openPage({ docId, page, text }) {
    navigations += 1;
    store.set({
      openDocId: docId,
      openPage: page,
      highlight: text ? { text, token: Date.now() } : null,
      navToken: navigations,
      activePane: "viewer",
    });
  }

  function openDocument(docId) {
    navigations += 1;
    store.set({
      openDocId: docId,
      openPage: 1,
      highlight: null,
      navToken: navigations,
      scope: "document",
      activePane: "viewer",
    });
  }

  function setPage(page) {
    store.set({ openPage: page });
  }

  function clearHighlight() {
    store.set({ highlight: null });
  }

  // A document deleted elsewhere: when it is the open one, the viewer is closed.
  function forgetDocument(docId) {
    if (store.get().openDocId === docId) store.set(VIEWER_CLOSED);
  }

  return { openDocument, openPage, setPage, clearHighlight, forgetDocument };
}
