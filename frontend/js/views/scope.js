// The scope choice of the chat pane: where the next question looks. The document choice needs an
// open document; without one only the whole folder can be chosen.
import { byId, setVisible } from "../dom.js";
import { t } from "../i18n.js";

export function mountScopeView(store, actions) {
  const documentRadio = byId("scope-document");
  const folderRadio = byId("scope-folder");
  const note = byId("scope-note");

  for (const radio of [documentRadio, folderRadio]) {
    radio.addEventListener("change", () => actions.ask.setScope(radio.value));
  }

  store.subscribe(
    (state) => {
      const open = Boolean(state.openDocId);
      const inDocument = open && state.scope === "document";
      documentRadio.disabled = !open;
      documentRadio.checked = inDocument;
      folderRadio.checked = !inDocument;
      setVisible(note, !open);
      note.textContent = open ? "" : t("scope.noDocument");
    },
    ["scope", "openDocId"],
  );
}
