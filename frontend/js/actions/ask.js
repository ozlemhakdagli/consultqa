// Use cases of the chat pane: choose a method, choose the scope and ask a question. Each question
// is kept as a turn of the thread, first pending, then with its result.
import { ApiError } from "../errors.js";
import { t } from "../i18n.js";
import { askBlockReason, effectiveScopeDocId } from "../selectors.js";
import { VIEWER_CLOSED } from "../state.js";

const SCOPES = Object.freeze(["document", "folder"]);

let nextTurnId = 1;

export function createAskActions({ api, store, documents = { loadDocuments: async () => {} } }) {
  function selectPreset(name) {
    store.set({ selectedPreset: name });
  }

  function setScope(scope) {
    if (!SCOPES.includes(scope)) return;
    store.set({ scope });
  }

  // The text fills the question box of the chat pane. Only the draft is set here: the form decides
  // whether the chat pane must be shown, which is needed only where the panes are tabs.
  function setDraft(text) {
    store.set({ draft: { text, token: Date.now() } });
  }

  // A document deleted elsewhere: when it is the open one, the viewer is closed, so that later
  // questions do not ask about it again, and the list is loaded again without it.
  async function forgetDocument(docId) {
    if (store.get().openDocId === docId) store.set(VIEWER_CLOSED);
    await documents.loadDocuments();
  }

  function answerResult(state, body) {
    if (body.answer === null) return { kind: "notFound" };
    const { preset } = body;
    return {
      kind: "answer",
      preset,
      isRecommended: preset === state.capabilities.default_preset,
      usesLlm: state.capabilities.presets.find((p) => p.name === preset)?.uses_llm ?? false,
      answer: body.answer,
      citations: body.citations,
      related: body.related ?? [],
    };
  }

  // Replaces one turn of the thread by its id; the other turns are kept as they are.
  function updateTurn(id, patch) {
    store.set({
      thread: store.get().thread.map((turn) => (turn.id === id ? { ...turn, ...patch } : turn)),
    });
  }

  async function askQuestion(question) {
    const state = store.get();
    if (askBlockReason(state) || state.asking) return;
    const text = question.trim();
    if (!text) {
      store.set({ askMessage: t("ask.questionRequired") });
      return;
    }
    const docId = effectiveScopeDocId(state);
    const id = nextTurnId;
    nextTurnId += 1;
    // Set before the first await, so a second click returns at once (no double request).
    // The earlier turns stay on screen while the question is searched.
    store.set({
      asking: true,
      askMessage: "",
      thread: [...state.thread, { id, question: text, docId, pending: true, result: null }],
    });
    try {
      const body = await api.ask(state.selectedCollectionId, text, state.selectedPreset, docId);
      updateTurn(id, { pending: false, result: answerResult(state, body) });
    } catch (error) {
      if (!(error instanceof ApiError)) {
        updateTurn(id, { pending: false, result: { kind: "error", code: "internal_error" } });
        throw error;
      }
      updateTurn(id, { pending: false, result: { kind: "error", code: error.code } });
      if (error.code === "document_not_found") await forgetDocument(docId);
    } finally {
      store.set({ asking: false });
    }
  }

  function clearMessage() {
    store.set({ askMessage: "" });
  }

  return { selectPreset, askQuestion, clearMessage, setScope, setDraft };
}
