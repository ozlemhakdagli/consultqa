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

export function removePref(name) {
  try {
    localStorage.removeItem(PREFIX + name);
  } catch {
    // Nothing was remembered, or storage is blocked: either way there is nothing to forget.
  }
}
