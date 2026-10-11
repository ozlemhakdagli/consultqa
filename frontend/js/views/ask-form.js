// Step 3 question form: the text box, the submit button, and the reason the form is locked.
import { byId, setVisible, showMessage } from "../dom.js";
import { t } from "../i18n.js";
import { askBlockReason } from "../selectors.js";

export function mountAskView(store, actions) {
  const form = byId("ask-form");
  const question = byId("question");
  const submit = byId("ask-submit");
  const reason = byId("ask-reason");
  const message = byId("ask-message");

  store.subscribe(
    (state) => {
      const blocked = askBlockReason(state);
      submit.disabled = blocked !== null || state.asking;
      submit.textContent = state.asking ? t("ask.submitting") : t("ask.submit");
      setVisible(reason, blocked !== null);
      reason.textContent = blocked ?? "";
    },
    [
      "status",
      "selectedCollectionId",
      "documents",
      "documentsLoaded",
      "selectedPreset",
      "capabilities",
      "asking",
    ],
  );

  store.subscribe(
    (state) =>
      showMessage(message, state.askMessage ? { kind: "error", text: state.askMessage } : null),
    ["askMessage"],
  );

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.ask.askQuestion(question.value);
  });
}
