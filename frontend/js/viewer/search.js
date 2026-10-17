// Text search and highlights in the pdf.js viewer: the first match of a text is found on the pages,
// marked in its page's text layer, and remembered so that a zoom can mark it again. The helpers
// work on the shared `state` that pdf.js makes, and on the page renderer from pages.js.
import { findMatch, itemsInRange, normalizeItems, pageOrder } from "./match.js";

const HIGHLIGHT_CLASS = "pdf-highlight";

export function createHighlighter(state, renderer) {
  // The normalized text of one page, read once from the library and kept until the next open.
  // Null when the document was closed or replaced while the text was being read.
  async function searchText(index) {
    const generation = state.docGeneration;
    const info = state.pages[index];
    if (info.text === null) {
      const content = await renderer.contentOf(info);
      if (generation !== state.docGeneration) return null;
      const items = content.items.map((item) => ({ str: item.str, eol: item.hasEOL }));
      info.text = normalizeItems(items);
    }
    return info.text;
  }

  // Marks the first match of the text in its page's text layer. The requested page (1-based, if
  // any) is searched first. `scroll` brings the mark to the reading line. False when nothing
  // matches, when no document is open yet, or when another highlight or document replaced this
  // one meanwhile.
  async function markText(text, scroll, page) {
    const generation = state.docGeneration;
    const attempt = ++state.highlightGeneration;
    unmark();
    if (!state.ready) return false;
    const isCurrent = () => attempt === state.highlightGeneration && generation === state.docGeneration;
    const match = await findMatch(searchText, text, pageOrder(state.pages.length, page));
    if (match === null || !isCurrent()) return false;
    const source = await searchText(match.page);
    if (source === null || !isCurrent()) return false;
    const info = state.pages[match.page];
    try {
      await renderer.ensureLayer(info);
    } catch {
      return false;
    }
    if (!isCurrent() || !info.layer) return false;
    const divs = info.layer.textDivs;
    const nodes = [];
    for (const index of itemsInRange(source.origins, match.start, match.end)) {
      const div = divs[index];
      if (!div) continue;
      div.classList.add(HIGHLIGHT_CLASS);
      nodes.push(div);
    }
    state.marked = nodes;
    if (nodes.length === 0) return false;
    if (scroll) {
      renderer.scrollToNode(nodes[0]);
      state.updateCurrent();
    }
    return true;
  }

  // Marks the first match of the text, from the requested page on, and scrolls to it. The text and
  // page are remembered for a zoom.
  function highlight(text, { page } = {}) {
    state.lastHighlight = { text, page };
    return markText(text, true, page);
  }

  // Removes the marks, forgets the highlight and cancels one that is still in flight.
  function clearHighlight() {
    state.lastHighlight = null;
    state.highlightGeneration += 1;
    unmark();
  }

  function unmark() {
    for (const div of state.marked) div.classList.remove(HIGHLIGHT_CLASS);
    state.marked = [];
  }

  return { highlight, markText, clearHighlight, unmark };
}
