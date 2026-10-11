// Advanced section: one radio card per offered method, with its plain name, its description and,
// when the method cannot be used, the plain reason.
import { byId, el } from "../dom.js";
import { has, t } from "../i18n.js";
import { offeredMethods } from "../methods.js";

function reasonText(reason) {
  const key = `method.reason.${reason}`;
  return t(has(key) ? key : "method.reason.unknown");
}

function methodOption(method, index, actions) {
  const radioId = `method-radio-${index}`;
  const titleId = `method-title-${index}`;
  const summaryId = `method-summary-${index}`;
  const reasonId = `method-reason-${index}`;
  const describedBy = method.available ? summaryId : `${summaryId} ${reasonId}`;

  const radio = el("input", {
    attrs: {
      type: "radio",
      name: "preset",
      id: radioId,
      value: method.preset,
      "aria-labelledby": titleId,
      "aria-describedby": describedBy,
    },
    on: { change: () => actions.ask.selectPreset(method.preset) },
  });
  radio.disabled = !method.available;

  const body = [
    el("label", {
      class: "method-title",
      attrs: { id: titleId, for: radioId },
      text: t(`method.${method.key}.label`),
    }),
  ];
  if (method.recommended) {
    body.push(el("span", { class: "badge badge-recommended", text: t("method.recommended") }));
  }
  body.push(
    el("p", {
      class: "method-summary",
      attrs: { id: summaryId },
      text: t(`method.${method.key}.summary`),
    }),
    el("p", { class: "method-note", text: t(`method.${method.key}.note`) }),
  );
  if (!method.available) {
    body.push(
      el("p", {
        class: "reason",
        attrs: { id: reasonId },
        text: reasonText(method.reason),
      }),
    );
  }
  return el(
    "div",
    { class: "method-option", attrs: { "data-available": String(method.available) } },
    radio,
    el("div", { class: "method-body" }, ...body),
  );
}

export function mountMethodsView(store, actions) {
  const list = byId("method-list");

  store.subscribe(
    (state) => {
      list.replaceChildren(
        ...offeredMethods(state.capabilities).map((method, index) =>
          methodOption(method, index, actions),
        ),
      );
    },
    ["capabilities"],
  );

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
