// Composition root: builds the API client, the store and the actions, then mounts the views.
import { createApi } from "./api.js";
import { applyStaticText } from "./i18n.js";
import { createSystemActions } from "./actions/system.js";
import { createCollectionActions } from "./actions/collections.js";
import { createDocumentActions } from "./actions/documents.js";
import { createUploadActions } from "./actions/uploads.js";
import { createAskActions } from "./actions/ask.js";
import { mountSystemView } from "./views/system.js";
import { mountCollectionsView } from "./views/collections.js";
import { mountDropzoneView } from "./views/dropzone.js";
import { mountDocumentsView } from "./views/documents.js";
import { mountMethodsView } from "./views/methods.js";
import { mountAskView } from "./views/ask-form.js";
import { mountResultView } from "./views/result.js";
import { mountThemeView } from "./views/theme.js";
import { createStore, INITIAL_STATE } from "./state.js";

const api = createApi();
const store = createStore(INITIAL_STATE);
const system = createSystemActions({ api, store });
const documents = createDocumentActions({ api, store });
const collections = createCollectionActions({ api, store, documents });
const uploads = createUploadActions({ api, store, documents });
const ask = createAskActions({ api, store });
const actions = { system, collections, documents, uploads, ask };

try {
  applyStaticText(document);
  mountSystemView(store);
  mountCollectionsView(store, actions);
  mountDropzoneView(store, actions);
  mountDocumentsView(store, actions);
  mountMethodsView(store, actions);
  mountAskView(store, actions);
  mountResultView(store);
  mountThemeView();
} finally {
  // The page shell was hidden until its text was in place; it can show now.
  document.body.classList.remove("booting");
}

collections.loadCollections();
system.watchUntilReady().then(() => {
  // The first load may have run while the app was unreachable; then the library is loaded now.
  if (!store.get().collectionsLoaded) collections.loadCollections();
});
