// Use cases of the readiness check: what the page may offer and when the models are ready.
import { READY_POLL_MS } from "../config.js";
import { ApiError } from "../errors.js";
import { isPresetAvailable, pickPreset } from "../selectors.js";
import { sleep as defaultSleep } from "../timing.js";

export function createSystemActions({ api, store, sleep = defaultSleep }) {
  async function refresh() {
    try {
      const capabilities = await api.capabilities();
      const patch = {
        capabilities,
        status: capabilities.ready ? "ready" : "loading",
      };
      if (!isPresetAvailable(capabilities, store.get().selectedPreset)) {
        patch.selectedPreset = pickPreset(capabilities, "");
      }
      store.set(patch);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      store.set({ status: "unreachable" });
    }
  }

  async function watchUntilReady() {
    await refresh();
    while (store.get().status !== "ready") {
      await sleep(READY_POLL_MS);
      await refresh();
    }
  }

  return { refresh, watchUntilReady };
}
