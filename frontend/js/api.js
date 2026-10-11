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

  return {
    capabilities: () => call("/api/capabilities"),
    listCollections: () => call("/api/collections"),
    createCollection: (name) => call("/api/collections", { method: "POST", json: { name } }),
    deleteCollection: (cid) => call(collection(cid), { method: "DELETE" }),
    listDocuments: (cid) => call(`${collection(cid)}/documents`),
    deleteDocument: (cid, docId) =>
      call(`${collection(cid)}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" }),
    getJob: (jobId) => call(`/api/jobs/${encodeURIComponent(jobId)}`),
    ask: (cid, question, preset) =>
      call(`${collection(cid)}/ask`, { method: "POST", json: { question, preset } }),
    uploadDocument,
  };
}
