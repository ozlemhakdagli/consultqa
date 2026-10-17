// The API client. Every call goes through fetch and resolves with the parsed body or rejects with
// an ApiError.
import { ApiError } from "./errors.js";

const JSON_HEADERS = { "Content-Type": "application/json" };

function codeOf(body) {
  return typeof body?.detail === "string" ? body.detail : "internal_error";
}

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

export function createApi({ fetchImpl = (...args) => fetch(...args) } = {}) {
  async function call(path, { method = "GET", json, body } = {}) {
    let response;
    try {
      response = await fetchImpl(path, {
        method,
        headers: json === undefined ? undefined : JSON_HEADERS,
        body: json === undefined ? body : JSON.stringify(json),
      });
    } catch {
      throw new ApiError("network_error");
    }
    const parsed = await readJson(response);
    if (!response.ok) throw new ApiError(codeOf(parsed), response.status, parsed);
    return parsed;
  }

  const collection = (cid) => `/api/collections/${encodeURIComponent(cid)}`;

  function uploadDocument(cid, file) {
    const form = new FormData();
    form.append("file", file, file.name);
    return call(`${collection(cid)}/documents`, { method: "POST", body: form });
  }

  const documentFileUrl = (cid, docId) =>
    `${collection(cid)}/documents/${encodeURIComponent(docId)}/file`;

  // The text of a document's text copy. Not parsed as JSON: a failure body still carries the code.
  async function documentText(cid, docId) {
    let response;
    try {
      response = await fetchImpl(documentFileUrl(cid, docId));
    } catch {
      throw new ApiError("network_error");
    }
    if (!response.ok) {
      throw new ApiError(codeOf(await readJson(response)), response.status);
    }
    return response.text();
  }

  // The passages of a document grouped by page. Parsed as JSON; a failure body carries the code.
  async function documentPassages(cid, docId) {
    return call(`${collection(cid)}/documents/${encodeURIComponent(docId)}/text`);
  }

  return {
    capabilities: () => call("/api/capabilities"),
    listCollections: () => call("/api/collections"),
    createCollection: (name) => call("/api/collections", { method: "POST", json: { name } }),
    deleteCollection: (cid) => call(collection(cid), { method: "DELETE" }),
    listDocuments: (cid) => call(`${collection(cid)}/documents`),
    deleteDocument: (cid, docId) =>
      call(`${collection(cid)}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" }),
    getJob: (jobId) => call(`/api/jobs/${encodeURIComponent(jobId)}`),
    ask: (cid, question, preset, docId = "") =>
      call(`${collection(cid)}/ask`, {
        method: "POST",
        json: docId ? { question, preset, doc_id: docId } : { question, preset },
      }),
    uploadDocument,
    documentFileUrl,
    documentText,
    documentPassages,
  };
}
