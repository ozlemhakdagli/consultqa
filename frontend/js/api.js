// The API client. JSON calls use fetch; the upload uses XMLHttpRequest because only it reports
// upload progress. Every method resolves with the parsed body or rejects with an ApiError.
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

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

export function createApi({
  fetchImpl = (...args) => fetch(...args),
  createXhr = () => new XMLHttpRequest(),
} = {}) {
  async function call(path, { method = "GET", json } = {}) {
    let response;
    try {
      response = await fetchImpl(path, {
        method,
        headers: json === undefined ? undefined : JSON_HEADERS,
        body: json === undefined ? undefined : JSON.stringify(json),
      });
    } catch {
      throw new ApiError("network_error");
    }
    const body = await readJson(response);
    if (!response.ok) throw new ApiError(codeOf(body), response.status, body);
    return body;
  }

  function uploadDocument(cid, file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = createXhr();
      xhr.open("POST", `/api/collections/${encodeURIComponent(cid)}/documents`);
      xhr.upload.addEventListener("progress", (event) => {
        if (event.lengthComputable) onProgress(event.loaded, event.total);
      });
      xhr.addEventListener("load", () => {
        const body = parseJson(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(body);
        else reject(new ApiError(codeOf(body), xhr.status, body));
      });
      xhr.addEventListener("error", () => reject(new ApiError("network_error")));
      xhr.addEventListener("abort", () => reject(new ApiError("network_error")));
      const form = new FormData();
      form.append("file", file, file.name);
      xhr.send(form);
    });
  }

  const collection = (cid) => `/api/collections/${encodeURIComponent(cid)}`;

  return {
    capabilities: () => call("/api/capabilities"),
    listCollections: () => call("/api/collections"),
    createCollection: (name) => call("/api/collections", { method: "POST", json: { name } }),
    listDocuments: (cid) => call(`${collection(cid)}/documents`),
    deleteDocument: (cid, docId) =>
      call(`${collection(cid)}/documents/${encodeURIComponent(docId)}`, { method: "DELETE" }),
    getJob: (jobId) => call(`/api/jobs/${encodeURIComponent(jobId)}`),
    ask: (cid, question, preset) =>
      call(`${collection(cid)}/ask`, { method: "POST", json: { question, preset } }),
    uploadDocument,
  };
}
