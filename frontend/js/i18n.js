// Turkish text lookup. t() fills {name} placeholders; static text comes from data attributes.
import { STRINGS } from "./strings.js";

export function has(key) {
  return Object.hasOwn(STRINGS, key);
}

// An unknown key is returned as is, so a missing string shows its key instead of breaking the page.
export function t(key, params = {}) {
  const text = has(key) ? STRINGS[key] : key;
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
