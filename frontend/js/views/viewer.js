// The viewer pane: shows the open document as a PDF or as text, moves to the page and marks the
// sentence of an answer, and offers a selected text as a question. One pdf.js viewer is made for
// the pane and reused; opening another PDF replaces its document.
import { byId, setVisible } from "../dom.js";
import { createApi } from "../api.js";
import { currentLanguage, t } from "../i18n.js";
import { documentInfo } from "../selectors.js";
import { createPdfViewer } from "../viewer/pdf.js";

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4;
const ZOOM_STEP = 0.25;

export function mountViewerView(store, actions, { createViewer = createPdfViewer, api = createApi() } = {}) {
  const title = byId("viewer-title");
  const toolbar = byId("viewer-toolbar");
  const pageInput = byId("viewer-page");
  const pageCount = byId("viewer-page-count");
  const zoomOut = byId("viewer-zoom-out");
  const zoomIn = byId("viewer-zoom-in");
  const fit = byId("viewer-fit");
  const canvas = byId("viewer-canvas");
  const textNode = byId("viewer-text");
  const empty = byId("viewer-empty");
  const message = byId("viewer-message");
  const selectionButton = byId("selection-ask");

  // Translation keys of the note and of the page count, kept so that a language change redraws them.
  let noteKey = null;
  let total = 0;
  // null until the first call of the store listener, so that the empty state is shown at mount.
  let shownDocId = null;
  let loadSeq = 0;
  let navigationSeq = 0;
  let pdfPromise = null;
  let pdf = null;
  let selectedText = "";
  // The passages of the open document as fetched, and the language their dividers were drawn in;
  // a language change draws them again from these, without a new request.
  let passagePages = null;
  let passageLang = null;
  let titleFilename = "";
  // The page, sentence and navigation token the open PDF was last moved to; a language change
  // leaves them alone.
  let applied = null;

  setVisible(selectionButton, false);
  selectionButton.classList.add("selection-ask-button");

  // The heading is the open document's name, or the pane's name when nothing is open.
  function renderTitle() {
    title.textContent = titleFilename || t("panes.viewer");
  }

  function renderNote() {
    message.textContent = noteKey === null ? "" : t(noteKey);
    setVisible(message, noteKey !== null);
  }

  function renderCount() {
    pageCount.textContent = total > 0 ? t("viewer.pageOf", { count: total }) : "";
  }

  // Shows one kind of content and the status it is in; a note is a translation key or null.
  function present({ status, pdfShown = false, textShown = false, note = null }) {
    setVisible(canvas, pdfShown);
    setVisible(textNode, textShown);
    setVisible(toolbar, pdfShown && status === "ready");
    setVisible(empty, status === "idle");
    noteKey = note;
    renderNote();
    store.set({ viewerStatus: status });
  }

  function setZoom(value) {
    if (!pdf || store.get().viewerStatus !== "ready") return;
    const rounded = Math.round(value / ZOOM_STEP) * ZOOM_STEP;
    pdf.setZoom(Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, rounded)));
  }

  // The scale the page is shown at, also when the zoom is "fit"; 1 when the viewer cannot tell.
  function currentScale() {
    const scale = typeof pdf?.scale === "function" ? pdf.scale() : 1;
    return typeof scale === "number" && Number.isFinite(scale) ? scale : 1;
  }

  function onSelection(selection) {
    if (selection === null) {
      selectedText = "";
      setVisible(selectionButton, false);
      return;
    }
    selectedText = selection.text;
    selectionButton.style.left = `${selection.rect.left}px`;
    selectionButton.style.top = `${selection.rect.bottom + 4}px`;
    setVisible(selectionButton, true);
  }

  function onPage(number) {
    pageInput.value = String(number);
  }

  // Creates the pdf.js viewer on first use only; a failure to create it is a failure to show.
  function pdfViewer() {
    pdfPromise ??= Promise.resolve(createViewer(canvas, { onSelection, onPage })).then(
      (created) => {
        pdf = created;
        return created;
      },
      (error) => {
        // A failed creation is not kept: the next PDF open tries again.
        pdfPromise = null;
        throw error;
      },
    );
    return pdfPromise;
  }

  // Moves the open PDF to the requested page and marks the sentence, or clears the mark.
  async function applyNavigation(state) {
    if (state.viewerStatus !== "ready" || !pdf) return;
    const seq = ++navigationSeq;
    const loads = loadSeq;
    applied = { page: state.openPage, highlight: state.highlight, navToken: state.navToken };
    pdf.goToPage(state.openPage);
    pageInput.value = String(pdf.currentPage());
    if (state.highlight === null) {
      pdf.clearHighlight();
      noteKey = null;
      renderNote();
      return;
    }
    let found = false;
    try {
      found = await pdf.highlight(state.highlight.text, { page: state.openPage });
    } catch {
      found = false;
    }
    // A mark that arrives after the pane moved on, to another document or another navigation, is dropped.
    if (seq !== navigationSeq || loads !== loadSeq) return;
    noteKey = found ? null : "viewer.noHighlight";
    renderNote();
  }

  // The passages as one text: a divider line before each page that has a number, the passages of a
  // page and the pages separated by a blank line. Drawn in the language in use now.
  function renderPassages() {
    textNode.textContent = passagePages
      .map((entry) => {
        const passage = String(entry?.text ?? "");
        return typeof entry?.page === "number"
          ? `${t("viewer.pageDivider", { page: entry.page })}\n${passage}`
          : passage;
      })
      .join("\n\n");
    passageLang = currentLanguage();
  }

  // Fetches the passages of a document once and shows them with the note and status of its case.
  // When they cannot be had, the same note and status show without text: an old document keeps its
  // note, a PDF that failed to load keeps its "can't be shown" note. A document deleted elsewhere
  // closes the viewer and the document list is loaded again.
  async function showPassages(collectionId, docId, seq, { status, note }) {
    let body = null;
    let gone = false;
    try {
      body = await api.documentPassages(collectionId, docId);
    } catch (error) {
      gone = error?.code === "document_not_found";
      body = null;
    }
    if (gone) {
      actions.viewer.forgetDocument(docId);
      await actions.documents.loadDocuments();
      return;
    }
    if (seq !== loadSeq) return;
    const pages = Array.isArray(body?.pages) ? body.pages : [];
    if (pages.length === 0) {
      passagePages = null;
      textNode.textContent = "";
      present({ status, note });
      return;
    }
    passagePages = pages;
    renderPassages();
    present({ status, textShown: true, note });
  }

  async function showDocument(state) {
    const docId = state.openDocId;
    const seq = ++loadSeq;
    navigationSeq += 1;
    applied = null;
    passagePages = null;
    const info = documentInfo(state).get(docId) ?? null;
    titleFilename = info?.filename ?? "";
    renderTitle();
    pdf?.clearHighlight();
    if (docId === "") {
      // Nothing is open: the PDF viewer is destroyed so that no earlier document stays in the pane.
      pdf?.destroy();
      pdf = null;
      pdfPromise = null;
      onSelection(null);
      present({ status: "idle" });
      return;
    }
    const collectionId = state.selectedCollectionId;
    if (info !== null && !info.hasOriginal) {
      present({ status: "loading", note: "viewer.loading" });
      await showPassages(collectionId, docId, seq, { status: "old", note: "viewer.oldDocument" });
      return;
    }
    if (info?.kind === "text") {
      present({ status: "loading", note: "viewer.loading" });
      try {
        const body = await api.documentText(collectionId, docId);
        if (seq !== loadSeq) return;
        textNode.textContent = body;
        present({ status: "text", textShown: true });
      } catch {
        await showPassages(collectionId, docId, seq, { status: "failed", note: "viewer.cantShow" });
      }
      return;
    }
    present({ status: "loading", pdfShown: true, note: "viewer.loading" });
    try {
      const viewer = await pdfViewer();
      if (seq !== loadSeq) return;
      const { pageCount: pages } = await viewer.open(api.documentFileUrl(collectionId, docId));
      if (seq !== loadSeq) return;
      total = pages;
      pageInput.max = String(pages);
      pageInput.value = "1";
      renderCount();
      present({ status: "ready", pdfShown: true });
      applyNavigation(store.get());
    } catch {
      if (seq !== loadSeq) return;
      await showPassages(collectionId, docId, seq, { status: "failed", note: "viewer.cantShow" });
    }
  }

  store.subscribe(
    (state) => {
      renderTitle();
      empty.textContent = t("viewer.empty");
      selectionButton.textContent = t("viewer.selectionAsk");
      renderNote();
      renderCount();
      // A language change draws the dividers again; the passages are not requested a second time.
      if (passagePages !== null && passageLang !== currentLanguage()) renderPassages();
      if (state.openDocId !== shownDocId) {
        shownDocId = state.openDocId;
        showDocument(state);
        return;
      }
      // Only a new page, sentence or open moves the reader; a language change redraws the text.
      if (
        state.openPage !== applied?.page ||
        state.highlight !== applied?.highlight ||
        state.navToken !== applied?.navToken
      ) {
        applyNavigation(state);
      }
    },
    ["openDocId", "openPage", "highlight", "navToken"],
  );

  // The entered page is kept within the pages of the document. An entry that is not a number
  // puts the current page back in the box.
  // A PDF opened while its pane is hidden is laid out against a container of no width, so the fit
  // scale is wrong. When the pane is shown, the zoom is applied again and the navigation with it.
  let lastPane = null;
  store.subscribe(
    (state) => {
      const shown = state.activePane === "viewer" && lastPane !== "viewer";
      lastPane = state.activePane;
      if (!shown || state.viewerStatus !== "ready" || !pdf) return;
      pdf.setZoom(pdf.zoom());
      applied = null;
      applyNavigation(state);
    },
    ["activePane"],
  );

  pageInput.addEventListener("change", () => {
    if (!pdf || store.get().viewerStatus !== "ready") return;
    const number = Number(pageInput.value);
    if (pageInput.value.trim() === "" || !Number.isFinite(number)) {
      pageInput.value = String(pdf.currentPage());
      return;
    }
    const target = Math.min(Math.max(Math.round(number), 1), total);
    pdf.goToPage(target);
    pageInput.value = String(target);
  });
  zoomOut.addEventListener("click", () => setZoom(currentScale() - ZOOM_STEP));
  zoomIn.addEventListener("click", () => setZoom(currentScale() + ZOOM_STEP));
  fit.addEventListener("click", () => {
    if (pdf && store.get().viewerStatus === "ready") pdf.setZoom("fit");
  });

  // A press keeps the text selection, so the click still has the text to offer.
  selectionButton.addEventListener("mousedown", (event) => event.preventDefault());
  selectionButton.addEventListener("click", () => {
    const text = selectedText;
    if (!text) return;
    actions.ask.setDraft(text);
    selectedText = "";
    setVisible(selectionButton, false);
  });
}
