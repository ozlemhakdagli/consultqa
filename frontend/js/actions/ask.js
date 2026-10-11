// Use cases of step 3: choose a method and ask a question; the answer is kept as a result.
import { ApiError } from "../errors.js";
import { t } from "../i18n.js";
import { askBlockReason } from "../selectors.js";

export function createAskActions({ api, store }) {
  function selectPreset(name) {
    store.set({ selectedPreset: name });
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
    };
  }

  async function askQuestion(question) {
    const state = store.get();
    if (askBlockReason(state) || state.asking) return;
    const text = question.trim();
    if (!text) {
      store.set({ askMessage: t("ask.questionRequired") });
      return;
    }
    // Set before the first await, so a second click returns at once (no double request).
    // The previous result stays on screen while the question is searched (the page keeps its height).
    store.set({ asking: true, askMessage: "" });
    try {
      const body = await api.ask(state.selectedCollectionId, text, state.selectedPreset);
      store.set({ result: answerResult(state, body) });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ result: { kind: "error", code: error.code } });
    } finally {
      store.set({ asking: false });
    }
  }

  function clearMessage() {
    store.set({ askMessage: "" });
  }

  return { selectPreset, askQuestion, clearMessage };
}
