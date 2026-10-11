// The colour theme: "system" (the default, which follows the device), "light" or "dark". The choice
// is kept in the browser. When storage is blocked the choice still applies for this visit.
import { getPref, setPref } from "./prefs.js";

export const THEMES = Object.freeze(["system", "light", "dark"]);

export function readTheme() {
  const saved = getPref("theme");
  return THEMES.includes(saved) ? saved : "system";
}

// "light" and "dark" are forced on the root element; "system" removes the attribute, so the
// stylesheet follows the device again.
export function applyTheme(choice, root = document.documentElement) {
  if (choice === "light" || choice === "dark") {
    root.setAttribute("data-theme", choice);
  } else {
    root.removeAttribute("data-theme");
  }
}

// An unknown choice means "system". The choice is applied and then remembered.
export function chooseTheme(choice, root = document.documentElement) {
  const valid = THEMES.includes(choice) ? choice : "system";
  applyTheme(valid, root);
  setPref("theme", valid);
}
