// Step 3 method list: one radio card per method, with its description and, when unavailable, why.
import { byId, el } from "../dom.js";
import { has, t } from "../i18n.js";

function textOr(key, fallback) {
  return has(key) ? t(key) : fallback;
}

function methodOption(preset, index, capabilities, actions) {
  const { name } = preset;
  const radioId = `method-radio-${index}`;
  const titleId = `method-title-${index}`;
  const summaryId = `method-summary-${index}`;
  const reasonId = `method-reason-${index}`;
  const describedBy = preset.available ? summaryId : `${summaryId} ${reasonId}`;

  const radio = el("input", {
    attrs: {
      type: "radio",
      name: "preset",
      id: radioId,
      value: name,
      "aria-labelledby": titleId,
      "aria-describedby": describedBy,
    },
    on: { change: () => actions.ask.selectPreset(name) },
  });
  radio.disabled = !preset.available;

  const badges = el("div", { class: "method-badges" }, el("span", { class: "badge", text: name }));
  if (capabilities.default_preset === name) {
    badges.append(el("span", { class: "badge badge-recommended", text: t("method.recommended") }));
  }
  if (preset.uses_llm) {
    badges.append(el("span", { class: "badge", text: t("method.needsLlm") }));
  }

  const body = [
    el("label", {
      class: "method-title",
      attrs: { id: titleId, for: radioId },
      text: textOr(`method.${name}.label`, name),
    }),
    badges,
    el("p", {
      class: "method-summary",
      attrs: { id: summaryId },
      text: textOr(`method.${name}.summary`, t("method.unknown.summary")),
    }),
  ];
  if (has(`method.${name}.note`)) {
    body.push(el("p", { class: "method-note", text: t(`method.${name}.note`) }));
  }
  if (!preset.available) {
    body.push(
      el("p", {
        class: "reason",
        attrs: { id: reasonId },
        text: textOr(`method.reason.${preset.reason}`, t("method.reason.unknown")),
      }),
    );
  }
  return el(
    "div",
    { class: "method-option", attrs: { "data-available": String(preset.available) } },
    radio,
    el("div", { class: "method-body" }, ...body),
  );
}

export function mountMethodsView(store, actions) {
  const list = byId("method-list");

  store.subscribe((state) => {
    const { capabilities } = state;
    if (!capabilities) return;
    list.replaceChildren(
      ...capabilities.presets.map((preset, index) =>
        methodOption(preset, index, capabilities, actions),
      ),
    );
  }, ["capabilities"]);

  // Only the checked state changes here: re-rendering the radios would drop keyboard focus.
  store.subscribe(
    (state) => {
      for (const radio of list.querySelectorAll("input[type=radio]")) {
        radio.checked = radio.value === state.selectedPreset;
      }
    },
    ["selectedPreset", "capabilities"],
  );
}
