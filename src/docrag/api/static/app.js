// docrag page logic. Every string from the server is written with textContent.

const POLL_MS = 1000;
const DEFAULT_PRESET = "L5";

const MESSAGES = {
  validation_error: "Check the input. Questions and names must not be blank.",
  busy: "The service is answering another question. Try again in a moment.",
  not_ready: "The models are still loading. Try again in a moment.",
  llm_unavailable: "The language model did not answer. The retrieval trace is shown below.",
  collection_not_found: "That collection no longer exists. Choose another one.",
  collection_exists: "A collection with that name already exists.",
  document_not_found: "That document no longer exists.",
  file_too_large: "The file is larger than the upload limit.",
  unsupported_type: "This file type is not supported. Use .pdf, .txt or .md.",
  preset_unavailable: "That method is not available on this server.",
  unknown_preset: "Unknown method.",
  parse_failed: "The file could not be read. It may be corrupt or not text.",
  too_many_pages: "The file has more pages than the server accepts.",
  internal_error: "Something went wrong on the server.",
  network_error: "The service could not be reached.",
};

const JOB_LABELS = {
  queued: "Queued",
  parsing: "Reading the file",
  embedding: "Indexing the passages",
  graph: "Building the evidence graph",
};

const $ = (id) => document.getElementById(id);
const collectionSelect = $("collection-select");
const presetSelect = $("preset-select");

function messageFor(code) {
  return Object.prototype.hasOwnProperty.call(MESSAGES, code) ? MESSAGES[code] : code;
}

function show(element, text) {
  element.textContent = text;
  element.hidden = !text;
}

// Call the API and never throw: network failures become a result with the code network_error.
async function request(url, options = {}) {
  try {
    const response = await fetch(url, options);
    let body = {};
    try {
      body = await response.json();
    } catch (_error) {
      body = {};
    }
    return { ok: response.ok, status: response.status, body };
  } catch (_error) {
    return { ok: false, status: 0, body: { detail: "network_error" } };
  }
}

function errorCode(result) {
  const detail = result.body ? result.body.detail : undefined;
  return typeof detail === "string" ? detail : "internal_error";
}

function optionElement(value, text) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = text;
  return option;
}

async function loadPresets() {
  const result = await request("/api/presets");
  if (!result.ok) {
    show($("error"), messageFor(errorCode(result)));
    return;
  }
  const names = result.body;
  presetSelect.replaceChildren(...names.map((name) => optionElement(name, name)));
  presetSelect.value = names.includes(DEFAULT_PRESET) ? DEFAULT_PRESET : names[0] || "";
}

async function loadCollections(selectedId) {
  const result = await request("/api/collections");
  if (!result.ok) {
    show($("collection-status"), messageFor(errorCode(result)));
    return;
  }
  const collections = result.body;
  const previous = selectedId || collectionSelect.value;
  const options = collections.map((item) => optionElement(item.id, item.name));
  if (collections.length === 0) {
    options.push(optionElement("", "No collections yet. Create one below."));
  }
  collectionSelect.replaceChildren(...options);
  if (collections.some((item) => item.id === previous)) {
    collectionSelect.value = previous;
  }
}

$("collection-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = $("collection-status");
  const nameInput = $("collection-name");
  const name = nameInput.value.trim();
  if (!name) {
    show(status, messageFor("validation_error"));
    return;
  }
  const result = await request("/api/collections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!result.ok) {
    show(status, messageFor(errorCode(result)));
    return;
  }
  nameInput.value = "";
  show(status, `Created collection ${result.body.name}.`);
  await loadCollections(result.body.id);
});

function pause(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Poll the ingestion job once a second until it reaches done or failed.
async function pollJob(jobId, status) {
  for (;;) {
    const result = await request(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (!result.ok) {
      show(status, messageFor(errorCode(result)));
      return;
    }
    const { state, error } = result.body;
    if (state === "done") {
      show(status, "Document added. You can ask questions about it now.");
      return;
    }
    if (state === "failed") {
      show(status, `Upload failed: ${messageFor(error || "internal_error")}`);
      return;
    }
    show(status, JOB_LABELS[state] || state);
    await pause(POLL_MS);
  }
}

$("upload-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const status = $("upload-status");
  const cid = collectionSelect.value;
  const file = $("upload-file").files[0];
  if (!cid || !file) {
    show(status, "Choose a collection and a file first.");
    return;
  }
  const submit = $("upload-submit");
  submit.disabled = true;
  try {
    show(status, "Uploading...");
    const data = new FormData();
    data.append("file", file, file.name);
    const result = await request(`/api/collections/${encodeURIComponent(cid)}/documents`, {
      method: "POST",
      body: data,
    });
    if (!result.ok) {
      show(status, messageFor(errorCode(result)));
      return;
    }
    await pollJob(result.body.job_id, status);
  } finally {
    submit.disabled = false;
  }
});

function citationItem(citation) {
  const item = document.createElement("li");
  item.id = `cite-${citation.number}`;
  const heading = document.createElement("p");
  heading.className = "citation-heading";
  const label = document.createElement("strong");
  label.textContent = `[${citation.number}] `;
  const path = document.createElement("span");
  path.textContent = citation.heading_path.join(" > ") || "Untitled section";
  heading.append(label, path);
  const passage = document.createElement("blockquote");
  passage.textContent = citation.text;
  item.append(heading, passage);
  return item;
}

// Append answer text, turning each [n] marker into a link to citation n.
function appendWithMarkers(container, text) {
  const pattern = /\[(\d+)\]/g;
  let last = 0;
  let match = pattern.exec(text);
  while (match !== null) {
    container.append(text.slice(last, match.index));
    const link = document.createElement("a");
    link.href = `#cite-${match[1]}`;
    link.textContent = match[0];
    container.append(link);
    last = match.index + match[0].length;
    match = pattern.exec(text);
  }
  container.append(text.slice(last));
}

function renderAnswer(body) {
  const answer = $("answer");
  answer.replaceChildren();
  if (body.answer) {
    appendWithMarkers(answer, body.answer);
  } else {
    answer.textContent = "No answer was found in the uploaded documents.";
  }
  $("citations").replaceChildren(...body.citations.map(citationItem));
  $("answer-block").hidden = false;
}

function traceRow(item) {
  const row = document.createElement("tr");
  const cells = [
    item.stage,
    item.rank,
    item.chunk_id,
    Number(item.score).toFixed(4),
    item.score_type,
    item.channel,
  ];
  for (const value of cells) {
    const cell = document.createElement("td");
    cell.textContent = String(value);
    row.append(cell);
  }
  return row;
}

function renderTrace(trace) {
  $("trace-body").replaceChildren(...trace.map(traceRow));
  $("trace-details").hidden = trace.length === 0;
}

function clearAnswer() {
  show($("error"), "");
  $("answer").replaceChildren();
  $("citations").replaceChildren();
  $("answer-block").hidden = true;
  renderTrace([]);
}

$("ask-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  clearAnswer();
  const cid = collectionSelect.value;
  const question = $("question").value.trim();
  if (!cid) {
    show($("error"), "Choose a collection first.");
    return;
  }
  if (!question) {
    show($("error"), messageFor("validation_error"));
    return;
  }
  const submit = $("ask-submit");
  submit.disabled = true;
  try {
    const result = await request(`/api/collections/${encodeURIComponent(cid)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, preset: presetSelect.value }),
    });
    // A 503 from the LLM reader still carries the retrieval trace.
    renderTrace(Array.isArray(result.body.trace) ? result.body.trace : []);
    if (!result.ok) {
      show($("error"), messageFor(errorCode(result)));
      return;
    }
    renderAnswer(result.body);
  } finally {
    submit.disabled = false;
  }
});

loadPresets();
loadCollections();
