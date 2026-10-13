// Pane tabs: below 1000 px one pane shows at a time and the tab row picks it; from 1000 px the CSS
// shows all three panes and hides the tabs. The chosen pane is kept in the state either way.
import { byId } from "../dom.js";

const PANES = Object.freeze([
  { key: "documents", tab: "tab-documents", pane: "pane-documents" },
  { key: "viewer", tab: "tab-viewer", pane: "pane-viewer" },
  { key: "chat", tab: "tab-chat", pane: "pane-chat" },
]);

// Arrow keys, Home and End move between the tabs, as the tab pattern asks.
function nextIndex(key, current) {
  if (key === "ArrowRight") return (current + 1) % PANES.length;
  if (key === "ArrowLeft") return (current + PANES.length - 1) % PANES.length;
  if (key === "Home") return 0;
  if (key === "End") return PANES.length - 1;
  return null;
}

// The pane that holds the focus, if any. Keyboard shortcuts of the browser (Alt+Left is back) are
// never taken over, so an event with Alt, Ctrl or Meta is left alone.
function paneWithFocus() {
  const focused = document.activeElement;
  return PANES.find(({ pane }) => byId(pane).contains(focused)) ?? null;
}

export function mountPanesView(store) {
  const tabRow = byId("pane-tabs");

  // Only the chosen tab is in the tab order; the panes say which one is active. A programmatic
  // switch can hide the pane that holds the focus: the focus then moves to the chosen tab, so it
  // never falls back to the page body. Focus is never moved when it was outside the hidden pane.
  function render(state) {
    const focusedPane = paneWithFocus();
    for (const { key, tab, pane } of PANES) {
      const active = state.activePane === key;
      const tabNode = byId(tab);
      tabNode.setAttribute("aria-selected", String(active));
      tabNode.tabIndex = active ? 0 : -1;
      byId(pane).setAttribute("data-pane-active", String(active));
    }
    if (focusedPane !== null && focusedPane.key !== state.activePane) {
      const chosen = PANES.find(({ key }) => key === state.activePane);
      if (chosen) byId(chosen.tab).focus();
    }
  }
  store.subscribe(render, ["activePane"]);

  for (const { key, tab } of PANES) {
    byId(tab).addEventListener("click", () => store.set({ activePane: key }));
  }

  tabRow.addEventListener("keydown", (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const current = PANES.findIndex(({ key }) => key === store.get().activePane);
    const next = nextIndex(event.key, Math.max(current, 0));
    if (next === null) return;
    event.preventDefault();
    store.set({ activePane: PANES[next].key });
    byId(PANES[next].tab).focus();
  });
}
