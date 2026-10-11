// Step 1 view: the collection list, the form that creates one, and the message line of the step.
import { el, byId, showMessage } from "../dom.js";
import { t } from "../i18n.js";

function renderOptions(select, { collections, collectionsLoaded }) {
  const empty = collectionsLoaded && collections.length === 0;
  const options = empty
    ? [el("option", { attrs: { value: "" }, text: t("collection.empty") })]
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

  store.subscribe((state) => renderOptions(select, state), ["collections", "collectionsLoaded"]);
  store.subscribe(
    (state) => {
      select.value = state.selectedCollectionId;
    },
    ["selectedCollectionId", "collections", "collectionsLoaded"],
  );
  store.subscribe((state) => showMessage(message, state.collectionMessage), ["collectionMessage"]);

  select.addEventListener("change", () => actions.collections.selectCollection(select.value));
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const created = await actions.collections.createCollection(input.value);
    if (created) input.value = "";
  });
}
