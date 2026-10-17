// Use cases of the documents pane: check files, send them one after another and follow each ingestion job.
import { JOB_MAX_POLL_FAILURES, JOB_MAX_WAIT_MS, JOB_POLL_MS } from "../config.js";
import { ApiError } from "../errors.js";
import { t } from "../i18n.js";
import { rowStatusText } from "../selectors.js";
import { sleep as defaultSleep } from "../timing.js";

const MEGABYTE = 1024 * 1024;

function extensionOf(name) {
  const dot = name.lastIndexOf(".");
  return dot < 0 ? "" : name.slice(dot).toLowerCase();
}

// The error code that refuses a file before it is sent, or null when it may be sent.
export function validateFile(file, capabilities) {
  if (!capabilities.extensions.includes(extensionOf(file.name))) return "unsupported_type";
  if (file.size === 0) return "file_empty";
  if (file.size > capabilities.max_upload_mb * MEGABYTE) return "file_too_large";
  return null;
}

export function createUploadActions({
  api,
  store,
  documents,
  sleep = defaultSleep,
  now = Date.now,
}) {
  let nextId = 1;

  // Every change of a row is announced to screen readers through the live line of the documents pane.
  function publish(uploads, row) {
    store.set({
      uploads,
      documentsAnnouncement: t("documents.announce", {
        name: row.name,
        status: rowStatusText(row.phase, row.errorCode),
      }),
    });
  }

  function addRow(row) {
    publish([...store.get().uploads, row], row);
  }

  function setRow(id, patch) {
    const row = { ...store.get().uploads.find((item) => item.id === id), ...patch };
    const uploads = store.get().uploads.map((item) => (item.id === id ? row : item));
    publish(uploads, row);
  }

  // Polls the job until it is done or failed. Gives up after too many failed polls in a row, or
  // when the job has run for longer than JOB_MAX_WAIT_MS, so the page never waits forever. The row
  // does not change while the job runs: the server's stages are not shown one by one.
  async function followJob(jobId) {
    const started = now();
    let failures = 0;
    while (now() - started <= JOB_MAX_WAIT_MS) {
      try {
        const job = await api.getJob(jobId);
        failures = 0;
        if (job.state === "done" || job.state === "failed") return job;
      } catch (error) {
        if (!(error instanceof ApiError)) throw error;
        failures += 1;
        if (failures >= JOB_MAX_POLL_FAILURES) return { state: "failed", error: error.code };
      }
      await sleep(JOB_POLL_MS);
    }
    return { state: "failed", error: "job_timeout" };
  }

  async function uploadOne(file, collectionId, capabilities) {
    const invalid = validateFile(file, capabilities);
    const id = nextId;
    nextId += 1;
    addRow({
      id,
      collectionId,
      name: file.name,
      phase: invalid ? "failed" : "sending",
      errorCode: invalid,
    });
    if (invalid) return;
    try {
      const { job_id: jobId, document_id: documentId } = await api.uploadDocument(
        collectionId,
        file,
      );
      setRow(id, { phase: "preparing" });
      const job = await followJob(jobId);
      if (job.state === "failed") {
        setRow(id, { phase: "failed", errorCode: job.error || "internal_error" });
        return;
      }
      // The server points a duplicate job at the document that already holds this content.
      const phase = job.document_id !== documentId ? "duplicate" : "done";
      // The list is reloaded while the row still reads "preparing": the file is never in neither.
      if (store.get().selectedCollectionId === collectionId) await documents.loadDocuments();
      setRow(id, { phase });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      setRow(id, { phase: "failed", errorCode: error.code });
    }
  }

  async function uploadFiles(files) {
    if (files.length === 0) return;
    store.set({ documentsMessage: null });
    // The whole batch goes to the collection that was selected when the files were chosen.
    const { selectedCollectionId: collectionId, capabilities } = store.get();
    for (const file of files) {
      await uploadOne(file, collectionId, capabilities);
    }
  }

  function dismiss(rowId) {
    store.set({ uploads: store.get().uploads.filter((row) => row.id !== rowId) });
  }

  return { uploadFiles, dismiss };
}
