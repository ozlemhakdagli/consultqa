// The page state: one frozen object that is replaced on every change. Listeners name the keys
// they watch and are called only when one of those keys changed by reference, or when the
// language changed (every view shows text, so every view is rendered again).
export const INITIAL_STATE = Object.freeze({
  lang: "",
  status: "checking",
  capabilities: null,
  collections: [],
  collectionsLoaded: false,
  collectionMessage: null,
  selectedCollectionId: "",
  documents: [],
  documentsLoaded: false,
  documentsMessage: null,
  confirmDeleteId: "",
  uploads: [],
  documentsAnnouncement: "",
  selectedPreset: "",
  asking: false,
  askMessage: "",
  openDocId: "",
  openPage: 1,
  // { text, token } | null: the sentence to mark on the open page.
  highlight: null,
  // "idle" | "loading" | "ready" | "text" | "failed" | "old"
  viewerStatus: "idle",
  // "document" | "folder": where the next question looks.
  scope: "document",
  // Turns { id, question, docId, pending, result }; docId is "" for a folder question.
  thread: [],
  // { text, token } | null: the text the user selected to ask again.
  draft: null,
  // "documents" | "viewer" | "chat"
  activePane: "documents",
  // A new value on every open of a page or a document, so that opening the same place again
  // moves the reader.
  navToken: 0,
});

// The viewer keys of a page with no document open.
export const VIEWER_CLOSED = Object.freeze({
  openDocId: "",
  openPage: 1,
  highlight: null,
  viewerStatus: "idle",
});

export function createStore(initial) {
  let state = Object.freeze({ ...initial });
  const subscriptions = new Set();
  return {
    get: () => state,
    set(patch) {
      const previous = state;
      state = Object.freeze({ ...previous, ...patch });
      const languageChanged = !Object.is(previous.lang, state.lang);
      for (const subscription of subscriptions) {
        const changed =
          languageChanged || subscription.keys.some((key) => !Object.is(previous[key], state[key]));
        if (changed) subscription.listener(state);
      }
    },
    subscribe(listener, keys) {
      const subscription = { listener, keys };
      subscriptions.add(subscription);
      listener(state);
      return () => subscriptions.delete(subscription);
    },
  };
}
