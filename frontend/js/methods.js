// The catalog of answer methods: the API presets the page offers, each with the key of its plain
// copy. A preset that is in neither list is never shown, so a new preset cannot leak its raw name.
export const METHODS = Object.freeze([
  Object.freeze({ preset: "L2", key: "fast" }),
  Object.freeze({ preset: "L3", key: "recheck" }),
  Object.freeze({ preset: "L4", key: "headings" }),
  Object.freeze({ preset: "L5", key: "related" }),
  Object.freeze({ preset: "L4+llm", key: "ai" }),
  Object.freeze({ preset: "paper", key: "paper" }),
]);

// Presets the page never offers: the graph variant that uses an LLM showed no gain.
export const HIDDEN_PRESETS = Object.freeze(["L5+llm"]);

export function methodKey(preset) {
  return METHODS.find((method) => method.preset === preset)?.key ?? null;
}

// The offered methods that the server lists, in catalog order.
export function offeredMethods(capabilities) {
  if (!capabilities) return [];
  return METHODS.flatMap(({ preset, key }) => {
    const listed = capabilities.presets.find((item) => item.name === preset);
    if (!listed) return [];
    return [
      {
        preset,
        key,
        available: listed.available,
        reason: listed.reason,
        recommended: preset === capabilities.default_preset,
      },
    ];
  });
}
