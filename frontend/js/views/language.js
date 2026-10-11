// The language switch in the top bar: two choices, the current one checked. A change applies at once.
import { byId } from "../dom.js";

export function mountLanguageView(store, actions) {
  const switchNode = byId("language-switch");
  store.subscribe(
    (state) => {
      for (const radio of switchNode.querySelectorAll("input[type=radio]")) {
        radio.checked = radio.value === state.lang;
      }
    },
    ["lang"],
  );
  switchNode.addEventListener("change", (event) => actions.language.choose(event.target.value));
}
