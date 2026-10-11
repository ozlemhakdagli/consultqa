// The theme switch in the top bar: three choices, the saved one checked. A change applies at once.
import { byId } from "../dom.js";
import { applyTheme, chooseTheme, readTheme } from "../theme.js";

export function mountThemeView() {
  const switchNode = byId("theme-switch");
  const current = readTheme();
  applyTheme(current);
  for (const radio of switchNode.querySelectorAll("input[type=radio]")) {
    radio.checked = radio.value === current;
  }
  switchNode.addEventListener("change", (event) => chooseTheme(event.target.value));
}
