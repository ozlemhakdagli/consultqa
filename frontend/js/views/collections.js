// Folder view: the folder list, the form that creates one, and the message line of that form.
import { el, byId, setVisible, showMessage } from "../dom.js";
import { t } from "../i18n.js";
import { selectedCollection, usesDefaultLibrary } from "../selectors.js";

function renderOptions(select, { collections }) {
  const empty = collections.length === 0;
  const options = empty
    ? [el("option", { attrs: { value: "" }, text: t("collection.loading") })]
    : collections.map((collection) =>
        el("option", { attrs: { value: collection.id }, text: collection.name }),
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
          name: selectedCollection(state).name,
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
