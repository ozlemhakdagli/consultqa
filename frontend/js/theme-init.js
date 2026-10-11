// A classic script in <head>, so it runs before the first paint: a saved light or dark choice is
// applied at once and the page never flashes the other theme. Remembering is optional, so a blocked
// storage simply leaves the page on the system setting.
(function applySavedTheme() {
  try {
    var saved = localStorage.getItem("docrag.theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.setAttribute("data-theme", saved);
    }
  } catch {
    // Storage is blocked: the system setting applies.
  }
})();
