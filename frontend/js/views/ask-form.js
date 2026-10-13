// The question form of the chat pane: the text box, three example questions that fill it, the
// submit button, and the reason the form is locked.
import { byId, el, setVisible, showMessage } from "../dom.js";
import { t } from "../i18n.js";
import { askBlockReason } from "../selectors.js";

const EXAMPLE_KEYS = ["ask.example.1", "ask.example.2", "ask.example.3"];

export function mountAskView(store, actions) {
  const form = byId("ask-form");
  const question = byId("question");
  const submit = byId("ask-submit");
  const reason = byId("ask-reason");
  const message = byId("ask-message");
  const examples = byId("example-list");

  // An example fills the box but never asks: the user decides when a question is sent. The buttons
  // are built again on every language change, so they always read in the current language.
  function renderExamples() {
    examples.replaceChildren(
      ...EXAMPLE_KEYS.map((key) =>
        el("button", {
          class: "example-button",
          text: t(key),
          attrs: { type: "button" },
          on: {
            click: () => {
              question.value = t(key);
              actions.ask.clearMessage();
              question.focus();
            },
          },
        }),
      ),
    );
  }
  store.subscribe(renderExamples, ["lang"]);
  question.addEventListener("input", () => actions.ask.clearMessage());

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
      "uploads",
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

  // A text from the page (the selected text) fills the box and is never sent by itself. The token
  // tells a new draft from the same one seen again on a language change.
  let draftToken = null;
  store.subscribe(
    (state) => {
      if (!state.draft || state.draft.token === draftToken) return;
      draftToken = state.draft.token;
      // The server takes at most the box's maxlength; a longer text is cut here, not sent and refused.
      const limit = question.maxLength > 0 ? question.maxLength : undefined;
      question.value = state.draft.text.slice(0, limit);
      // The focus waits a frame: the pane listener runs after this one, shows the chat pane and
      // moves the focus off the hidden viewer pane, so the box is focused after all of that.
      requestAnimationFrame(() => question.focus());
    },
    ["draft"],
  );

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.ask.askQuestion(question.value);
  });
}
