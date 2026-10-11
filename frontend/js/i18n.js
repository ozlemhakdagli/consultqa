// Text lookup for the page's current language. t() fills {name} placeholders; static text comes
// from data attributes.
import { getPref, setPref } from "./prefs.js";
import { DICTIONARIES } from "./strings.js";

export const LANGUAGES = Object.freeze(["tr", "en"]);
const TURKISH_BROWSER = /^tr(?:[-_]|$)/i;

// A saved choice wins. Otherwise a Turkish browser language gives Turkish, any other gives English.
export function detectLanguage(
  browserLanguage = globalThis.navigator?.language,
  saved = getPref("language"),
) {
  if (LANGUAGES.includes(saved)) return saved;
  return TURKISH_BROWSER.test(String(browserLanguage ?? "")) ? "tr" : "en";
}

let language = detectLanguage();

export function currentLanguage() {
  return language;
}

// An unknown code is ignored. Returns the language in use after the call.
export function setLanguage(code) {
  if (!LANGUAGES.includes(code)) return language;
  language = code;
  document.documentElement.lang = code;
  document.title = t("app.title");
  applyStaticText(document);
  return language;
}

// Chooses a language for the page and remembers the choice in the browser.
export function chooseLanguage(code) {
  const applied = setLanguage(code);
  setPref("language", applied);
  return applied;
}

export function has(key) {
  return Object.hasOwn(DICTIONARIES[language], key);
}

// An unknown key is returned as is, so a missing string shows its key instead of breaking the page.
export function t(key, params = {}) {
  const dictionary = DICTIONARIES[language];
  const text = Object.hasOwn(dictionary, key) ? dictionary[key] : key;
  return text.replace(/\{(\w+)\}/g, (placeholder, name) =>
    Object.hasOwn(params, name) ? String(params[name]) : placeholder,
  );
}

export function applyStaticText(root = document) {
  for (const node of root.querySelectorAll("[data-text]")) {
    node.textContent = t(node.dataset.text);
  }
  for (const node of root.querySelectorAll("[data-placeholder]")) {
    node.placeholder = t(node.dataset.placeholder);
  }
}
