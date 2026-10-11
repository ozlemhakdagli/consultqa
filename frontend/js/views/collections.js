// Folder view: the folder list, the form that creates one, and the message line of that form.
import { el, byId, setVisible, showMessage } from "../dom.js";
import { t } from "../i18n.js";
import { libraryLabel } from "../libraries.js";
import { selectedCollection, usesDefaultLibrary } from "../selectors.js";

// The confirmation names the folder and says that its documents go too. Only a yes deletes.
function askAndDelete(collection, actions) {
  if (!window.confirm(t("collection.deleteConfirm", { name: libraryLabel(collection) }))) return;
  actions.collections.deleteCollection(collection);
}

// One row per folder: its name, its number of documents and the button that deletes it.
function folderRow(collection, actions) {
  const label = libraryLabel(collection);
  return el(
    "li",
    { class: "doc-row" },
    el(
      "div",
      { class: "doc-main" },
      el("p", { class: "doc-name", text: label }),
      el("p", {
        class: "doc-status",
        text: t("collection.documentCount", { count: collection.document_count }),
      }),
    ),
    el("button", {
      class: "button button-danger",
      text: t("collection.delete"),
      attrs: { type: "button", "aria-label": t("collection.deleteLabel", { name: label }) },
      on: { click: () => askAndDelete(collection, actions) },
    }),
  );
}

function renderFolderList(list, title, { collections }, actions) {
  const any = collections.length > 0;
  setVisible(title, any);
  setVisible(list, any);
  list.replaceChildren(...collections.map((collection) => folderRow(collection, actions)));
}

function renderOptions(select, { collections }) {
  const empty = collections.length === 0;
  const options = empty
    ? [el("option", { attrs: { value: "" }, text: t("collection.loading") })]
    : collections.map((collection) =>
        el("option", { attrs: { value: collection.id }, text: libraryLabel(collection) }),
      );
  select.replaceChildren(...options);
  select.disabled = collections.length === 0;
}

export function mountCollectionsView(store, actions) {
  const select = byId("collection-select");
  const form = byId("collection-form");
  const input = byId("collection-name");
  const message = byId("collection-message");
  const notice = byId("library-notice");
  const folderTitle = byId("folder-list-title");
  const folderList = byId("folder-list");

  store.subscribe(
    (state) => renderFolderList(folderList, folderTitle, state, actions),
    ["collections"],
  );
  store.subscribe((state) => renderOptions(select, state), ["collections"]);
  store.subscribe(
    (state) => {
      select.value = state.selectedCollectionId;
    },
    ["selectedCollectionId", "collections", "collectionsLoaded"],
  );
  // Says in step 1 which folder is in use when it is not the default one.
  store.subscribe(
    (state) => {
      const other = !usesDefaultLibrary(state);
      setVisible(notice, other);
      if (other) {
        notice.textContent = t("library.notDefault", {
          name: libraryLabel(selectedCollection(state)),
          default: t("library.defaultName"),
        });
      }
    },
    ["collections", "selectedCollectionId"],
  );
  store.subscribe((state) => showMessage(message, state.collectionMessage), ["collectionMessage"]);

  select.addEventListener("change", () => actions.collections.selectCollection(select.value));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const created = await actions.collections.createCollection(input.value);
    if (created) input.value = "";
  });
}
