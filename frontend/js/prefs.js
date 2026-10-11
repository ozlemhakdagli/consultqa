// Remembered choices in localStorage. Storage can be blocked, so every access is guarded.
const PREFIX = "docrag.";

export function getPref(name) {
  try {
    return localStorage.getItem(PREFIX + name) ?? "";
  } catch {
    return "";
  }
}

export function setPref(name, value) {
  try {
    localStorage.setItem(PREFIX + name, value);
  } catch {
    // Remembering is optional: the page works the same without it.
  }
}
