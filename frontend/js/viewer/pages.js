// The render lifecycle of the pdf.js viewer's pages: sizing for the zoom, which pages get or lose
// a canvas as the view moves, and building a text layer and a canvas. The helpers read and write
// the shared `state` from pdf.js and never keep a copy of its fields. The epoch and token rules
// are described beside the code that keeps them.
import { el } from "../dom.js";

const FIT_PADDING = 32;
const PAGE_GAP = 12;
// A page's canvas is drawn while the page is within one viewport height of the view.
const NEAR_VIEWPORT = "100% 0px";
// A page's canvas is released only once it is three viewport heights away from the view.
const FAR_VIEWPORT = "300% 0px";
// Where a scrolled-to page or match sits in the container, as a share of its height.
export const READING_LINE = 0.3;

// The latest entry of each observed node in a batch: one batch may hold several for one node.
function latestEntries(entries) {
  const latest = new Map();
  for (const entry of entries) latest.set(entry.target, entry);
  return latest.values();
}

// Everything the viewer keeps about one page. Fields that a layout or a release replaces are
// set to null or to a new epoch object, so work started for an older one can tell it is stale.
export function newPage(page, number, size) {
  const node = el("div", { class: "pdf-page", attrs: { "data-page": number } });
  node.style.margin = `0 auto ${PAGE_GAP}px`;
  return {
    number,
    page,
    node,
    width: size.width,
    height: size.height,
    content: null, // the page's text content, read once
    text: null, // the page's normalized text for matching, made once from the content
    layer: null, // the built text layer; kept while the canvas is released
    layerTask: null, // the build of the text layer while it runs
    canvas: null, // the drawn canvas, or null while it is released
    canvasTask: null, // the draw of the canvas while it runs
    epoch: null, // replaced by every layout; an older build or draw stops
    canvasEpoch: null, // replaced by every layout and release; an older canvas draw stops
  };
}

// The page renderer over `state`. It owns the two intersection observers that draw and release
// the canvases, so they are made and dropped here.
export function createPageRenderer(state) {
  let drawWatch = null;
  let releaseWatch = null;
  let watchedScrollsItself = null; // the mode the observers were made for; see refreshRoot

  // The scale that makes the first page as wide as the container, less its padding.
  function fitScale() {
    const width = state.container.clientWidth - 2 * FIT_PADDING;
    return Math.max(0.1, width / state.pages[0].width);
  }

  // Sizes every page for the current scale and forgets everything drawn at another one.
  function layout() {
    state.scale = state.zoomLevel === "fit" ? fitScale() : state.zoomLevel;
    state.marked = [];
    for (const info of state.pages) {
      info.epoch = {};
      info.canvasEpoch = {};
      info.layer = null;
      info.layerTask = null;
      info.canvas = null;
      info.canvasTask = null;
      info.node.replaceChildren();
      // The text layer is positioned against its page and sized by --scale-factor, which pdf.js
      // reads from an ancestor; the module sets both, since the scale changes with zoom.
      info.node.style.position = "relative";
      info.node.style.setProperty("--scale-factor", String(state.scale));
      info.node.style.width = `${info.width * state.scale}px`;
      info.node.style.height = `${info.height * state.scale}px`;
    }
  }

  function pageOf(node) {
    return state.pages[Number(node.dataset.page) - 1];
  }

  // Whether the container scrolls itself. A container that grows with its pages does not, and then
  // the window scrolls the pages.
  function scrollsItself() {
    return state.container.scrollHeight > state.container.clientHeight;
  }

  // The part of the view that is on screen: the container when it scrolls itself, otherwise the part
  // of the container that the window shows. A hidden container has no height.
  function viewBox() {
    const rect = state.container.getBoundingClientRect();
    if (scrollsItself()) return { top: rect.top, height: rect.height };
    const top = Math.max(rect.top, 0);
    const bottom = Math.min(rect.bottom, window.innerHeight);
    return { top, height: Math.max(0, bottom - top) };
  }

  // Shows a page that came near the view: its text layer and its canvas.
  function showPage(info) {
    return Promise.all([ensureLayer(info), drawCanvas(info)]);
  }

  // Watches the pages: draws the ones that come near the view and releases the canvases of the
  // ones that go far away. The observers' root is the container only while it scrolls itself.
  function watchPages() {
    drawWatch?.disconnect();
    releaseWatch?.disconnect();
    watchedScrollsItself = scrollsItself();
    const root = watchedScrollsItself ? state.container : null;
    drawWatch = new IntersectionObserver(
      (entries) => {
        for (const entry of latestEntries(entries)) {
          const info = entry.isIntersecting ? pageOf(entry.target) : null;
          if (info) showPage(info).catch(() => {});
        }
      },
      { root, rootMargin: NEAR_VIEWPORT },
    );
    releaseWatch = new IntersectionObserver(
      (entries) => {
        for (const entry of latestEntries(entries)) {
          const info = entry.isIntersecting ? null : pageOf(entry.target);
          if (info) releaseCanvas(info);
        }
      },
      { root, rootMargin: FAR_VIEWPORT },
    );
    for (const info of state.pages) {
      drawWatch.observe(info.node);
      releaseWatch.observe(info.node);
    }
  }

  // Stops both observers. Called when the document is closed.
  function stopWatching() {
    drawWatch?.disconnect();
    releaseWatch?.disconnect();
    drawWatch = null;
    releaseWatch = null;
  }

  // A resize can move the view across the point where it starts or stops scrolling itself; the
  // observers are then made again for the other root.
  function refreshRoot() {
    if (state.pages.length > 0 && scrollsItself() !== watchedScrollsItself) watchPages();
  }

  // Drops a page's canvas and frees its memory. The text layer stays. A canvas draw still running
  // for the page stops before it adds its canvas.
  function releaseCanvas(info) {
    info.canvasEpoch = {};
    info.canvasTask = null;
    if (info.canvas) {
      info.canvas.width = 0;
      info.canvas.height = 0;
      info.canvas.remove();
      info.canvas = null;
    }
  }

  // The text content of a page, read once.
  // A failed read is forgotten, so that a later one retries it.
  function contentOf(info) {
    info.content ??= info.page.getTextContent().catch((error) => {
      info.content = null;
      throw error;
    });
    return info.content;
  }

  // The text layer of a page, built once and shared while it is built. A failed build is
  // forgotten, so a later one retries.
  function ensureLayer(info) {
    if (!info.layerTask) {
      // The build starts in a microtask, so that its task is recorded before any of its code runs.
      const task = Promise.resolve().then(() => buildLayer(info)).catch((error) => {
        if (info.layerTask === task) info.layerTask = null;
        throw error;
      });
      info.layerTask = task;
    }
    return info.layerTask;
  }

  async function buildLayer(info) {
    const epoch = info.epoch;
    const content = await contentOf(info);
    if (info.epoch !== epoch) throw new Error("superseded");
    const viewport = info.page.getViewport({ scale: state.scale });
    const textLayerNode = el("div", { class: "textLayer" });
    info.node.append(textLayerNode);
    const layer = new state.pdfjs.TextLayer({ textContentSource: content, container: textLayerNode, viewport });
    await layer.render();
    if (info.epoch !== epoch) {
      textLayerNode.remove();
      throw new Error("superseded");
    }
    info.layer = layer;
  }

  // The canvas of a page, drawn once and shared while it is drawn. A failed draw is forgotten,
  // so a later one retries.
  // The draw starts in a microtask, so that its task is recorded before any of its code runs; code
  // that runs during a draw (a zoom, say) may clear the task, and must not be overwritten by it.
  function drawCanvas(info) {
    if (!info.canvasTask) {
      const task = Promise.resolve().then(() => renderCanvas(info)).catch((error) => {
        if (info.canvasTask === task) info.canvasTask = null;
        throw error;
      });
      info.canvasTask = task;
    }
    return info.canvasTask;
  }

  async function renderCanvas(info) {
    const epoch = info.epoch;
    const canvasEpoch = info.canvasEpoch;
    const viewport = info.page.getViewport({ scale: state.scale });
    const ratio = window.devicePixelRatio || 1;
    const canvas = el("canvas");
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    await info.page.render({
      canvasContext: canvas.getContext("2d"),
      viewport,
      transform: [ratio, 0, 0, ratio, 0, 0],
    }).promise;
    if (info.epoch !== epoch || info.canvasEpoch !== canvasEpoch) {
      canvas.width = 0;
      canvas.height = 0;
      return;
    }
    info.canvas = canvas;
    info.node.prepend(canvas);
  }

  // Brings the node to the reading line of the view, by scrolling the container or the window.
  function scrollToNode(node) {
    const box = viewBox();
    const delta = node.getBoundingClientRect().top - (box.top + box.height * READING_LINE);
    if (scrollsItself()) state.container.scrollTop += delta;
    else window.scrollBy(0, delta);
  }

  return {
    layout,
    watchPages,
    stopWatching,
    refreshRoot,
    viewBox,
    scrollsItself,
    scrollToNode,
    contentOf,
    ensureLayer,
  };
}
