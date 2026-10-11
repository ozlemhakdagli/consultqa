// Use cases of step 3: choose a method and ask a question; the answer is kept as a result.
import { ApiError } from "../errors.js";
import { t } from "../i18n.js";
import { setPref } from "../prefs.js";
import { askBlockReason } from "../selectors.js";

export function createAskActions({ api, store }) {
  function selectPreset(name) {
    store.set({ selectedPreset: name });
    setPref("preset", name);
  }

  function answerResult(question, state, body) {
    const preset = body.preset;
    const trace = body.trace;
    const latencyMs = body.latency_ms;
    if (body.answer === null) return { kind: "notFound", question, preset, trace, latencyMs };
    const usesLlm = state.capabilities.presets.find((p) => p.name === preset)?.uses_llm ?? false;
    return {
      kind: "answer",
      question,
      preset,
      usesLlm,
      answer: body.answer,
      citations: body.citations,
      trace,
      latencyMs,
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
    store.set({ asking: true, result: null, askMessage: "" });
    try {
      const body = await api.ask(state.selectedCollectionId, text, state.selectedPreset);
      store.set({ result: answerResult(text, state, body) });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ result: { kind: "error", code: error.code, trace: error.body.trace ?? [] } });
    } finally {
      store.set({ asking: false });
    }
  }

  return { selectPreset, askQuestion };
}
