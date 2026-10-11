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
  result: null,
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
