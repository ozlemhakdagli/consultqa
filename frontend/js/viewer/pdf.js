// The pdf.js wrapper: the only module that touches the library, and the facade of the viewer. Pages are
// shown one under another. A page's text layer is built once it is near the view and then kept, so
// highlights and selections on a page stay valid for as long as the document is open. A page's canvas
// is drawn when the page comes within one viewport height of the view, and released when it is more
// than three viewport heights away, so a long document holds only a few canvases at a time.
// The page lifecycle is in pages.js and the text search and highlights are in search.js; both work on
// the `state` object made here.
import { el } from "../dom.js";
import { createHighlighter } from "./search.js";
import { createPageRenderer, newPage, READING_LINE } from "./pages.js";

const LIBRARY_URL = "/vendor/pdfjs/pdf.min.mjs";
const WORKER_URL = "/vendor/pdfjs/pdf.worker.min.mjs";
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4;

// Opens the library and returns a viewer that draws into `container`. Nothing loads before this.
export async function createPdfViewer(container, options = {}) {
  const pdfjs = await import(LIBRARY_URL);
  pdfjs.GlobalWorkerOptions.workerSrc = options.workerSrc ?? WORKER_URL;
  const onSelection = options.onSelection ?? (() => {});

  const root = el("div", { class: "viewer-pdf" });
  root.style.position = "relative";
  container.append(root);
  container.style.overflowY = "auto";

  // The fields that the helpers share. A helper reads and writes them where it uses them and never
  // keeps a copy: a copied generation, scale or page list would miss the changes made since.
  const state = {
    container,
    root,
    pdfjs,
    onPage: options.onPage ?? (() => {}),
    destroyed: false,
    doc: null,
    pages: [],
    ready: false, // true once the open document's pages are all in place
    docGeneration: 0, // bumped by open and destroy; work started for an older one stops
    highlightGeneration: 0, // bumped by each highlight; an older highlight stops
    zoomLevel: "fit",
    scale: 1,
    current: 1,
    marked: [], // the text-layer nodes that carry the highlight class
    lastHighlight: null, // { text, page } to mark again after a layout
    updateCurrent, // search.js calls it after it scrolls to a match
  };
  const { onPage } = state;
  let selectionReported = false;
  const renderer = createPageRenderer(state);
  const highlighter = createHighlighter(state, renderer);
  // The container width the pages were last laid out for, and the frame of a pending resize check.
  let laidOutWidth = 0;
  let resizeFrame = null;

  // Sizes the pages for the current zoom. The width is recorded after the layout: the layout can make
  // a scrollbar appear and narrow the container, and that change must not start another layout.
  function layoutPages() {
    renderer.layout();
    renderer.watchPages();
    laidOutWidth = container.clientWidth;
  }

  // Lays the pages out again at the current zoom, keeps the reader on the same page, and marks the
  // last highlight again without moving the reader to it. Used by a zoom and by a resize of a "fit".
  function relayout() {
    const keep = state.current;
    layoutPages();
    goToPage(keep);
    if (state.lastHighlight !== null) {
      highlighter
        .markText(state.lastHighlight.text, false, state.lastHighlight.page)
        .catch(() => {});
    }
  }

  // A "fit" view follows the width of the container. The observer checks at most once per frame,
  // and a check relays out only when the width differs by a pixel or more from the width recorded
  // after the last layout. A layout changes the height, and can change the width through a scrollbar,
  // but neither starts another layout. A hidden container has no width and is ignored.
  const resizeObserver = new ResizeObserver(() => {
    if (resizeFrame === null && !state.destroyed) resizeFrame = requestAnimationFrame(refit);
  });
  resizeObserver.observe(container);

  function refit() {
    resizeFrame = null;
    const width = container.clientWidth;
    if (state.destroyed || width <= 0 || Math.abs(width - laidOutWidth) < 1) return;
    if (state.zoomLevel !== "fit" || state.pages.length === 0) return;
    relayout();
  }

  // Releases the open document and everything drawn from it. Callers bump the generations.
  function closeDocument() {
    renderer.stopWatching();
    state.doc?.destroy().catch(() => {});
    state.doc = null;
    state.pages = [];
    state.ready = false;
    state.marked = [];
    state.lastHighlight = null;
    root.replaceChildren();
  }

  function setCurrent(number) {
    if (state.destroyed || number === state.current) return;
    state.current = number;
    onPage(number);
  }

  // The page under the reading line of the view. A hidden view has no height and reports nothing.
  function updateCurrent() {
    const box = renderer.viewBox();
    if (state.pages.length === 0 || box.height === 0) return;
    const line = box.top + box.height * READING_LINE;
    const found = state.pages.findIndex((info) => info.node.getBoundingClientRect().bottom > line);
    setCurrent(found === -1 ? state.pages.length : found + 1);
  }

  function reportSelection() {
    if (state.destroyed) return;
    const selection = window.getSelection();
    const range = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null;
    const text = range && !range.collapsed ? selection.toString().trim() : "";
    const inside = range !== null && container.contains(range.commonAncestorContainer);
    if (text && inside) {
      selectionReported = true;
      onSelection({ text, rect: range.getBoundingClientRect() });
    } else if (selectionReported) {
      selectionReported = false;
      onSelection(null);
    }
  }

  // Opens a document and shows its pages. A later open or destroy supersedes this one: its
  // document is released and it rejects with "superseded". An open after destroy rejects with
  // "destroyed" and touches nothing.
  async function open(url) {
    if (state.destroyed) throw new Error("destroyed");
    const generation = ++state.docGeneration;
    closeDocument();
    const stale = () => generation !== state.docGeneration;
    let opened = null;
    let adopted = false;
    try {
      opened = await pdfjs.getDocument({ url, isEvalSupported: false }).promise;
      if (stale()) throw new Error("superseded");
      const found = [];
      for (let number = 1; number <= opened.numPages; number += 1) {
        const page = await opened.getPage(number);
        if (stale()) throw new Error("superseded");
        found.push(newPage(page, number, page.getViewport({ scale: 1 })));
      }
      state.doc = opened;
      adopted = true;
      state.pages = found;
      for (const info of found) root.append(info.node);
    } catch (error) {
      if (!adopted) opened?.destroy().catch(() => {});
      if (stale()) throw new Error("superseded");
      throw new Error("load_failed", { cause: error });
    }
    layoutPages();
    state.ready = true;
    state.current = 0;
    goToPage(1);
    return { pageCount: state.pages.length };
  }

  // Moves to a page, clamped to the pages of the document. A value that is not a number is ignored.
  function goToPage(number) {
    const requested = Number(number);
    if (state.pages.length === 0 || !Number.isFinite(requested)) return;
    const target = Math.min(Math.max(Math.round(requested), 1), state.pages.length);
    renderer.scrollToNode(state.pages[target - 1].node);
    setCurrent(target);
  }

  // Sets the zoom: "fit" or a number, clamped to MIN_ZOOM..MAX_ZOOM. Any other value is ignored.
  // The page in view stays in view, and the last highlight is marked again without scrolling.
  function setZoom(value) {
    if (state.destroyed) return;
    const numeric = Number(value);
    if (value !== "fit" && !(Number.isFinite(numeric) && numeric > 0)) return;
    state.zoomLevel = value === "fit" ? "fit" : Math.min(Math.max(numeric, MIN_ZOOM), MAX_ZOOM);
    if (state.pages.length === 0) return;
    relayout();
  }

  function destroy() {
    state.destroyed = true;
    resizeObserver.disconnect();
    cancelAnimationFrame(resizeFrame);
    resizeFrame = null;
    window.removeEventListener("resize", renderer.refreshRoot);
    state.docGeneration += 1;
    state.highlightGeneration += 1;
    document.removeEventListener("selectionchange", reportSelection);
    container.removeEventListener("scroll", updateCurrent);
    window.removeEventListener("scroll", updateCurrent);
    closeDocument();
    root.remove();
  }

  document.addEventListener("selectionchange", reportSelection);
  container.addEventListener("scroll", updateCurrent);
  window.addEventListener("scroll", updateCurrent);
  window.addEventListener("resize", renderer.refreshRoot);

  return {
    open,
    goToPage,
    currentPage: () => state.current,
    setZoom,
    zoom: () => state.zoomLevel,
    // The numeric scale the pages are drawn at: the computed fit scale for "fit", and the zoom
    // number before a document is open.
    scale: () => (state.zoomLevel === "fit" ? state.scale : state.zoomLevel),
    highlight: highlighter.highlight,
    clearHighlight: highlighter.clearHighlight,
    destroy,
  };
}
