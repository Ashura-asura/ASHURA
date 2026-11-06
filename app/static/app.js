const $ = (selector) => document.querySelector(selector);
const chat = $("#chat");
const composer = $("#composer");
const input = $("#message");
const send = $("#send");
const showTrace = $("#show-trace");
const memoryQuery = $("#memory-query");
const memoryResults = $("#memory-results");
const ocrFile = $("#ocr-file");
let busy = false;

function elem(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function badge(text, tone = "") {
  return elem("span", `badge ${tone}`.trim(), text);
}

function clearEmptyState() {
  const empty = chat.querySelector(".empty-state");
  if (empty) empty.remove();
}

function renderTrace(trace) {
  if (!trace || !Array.isArray(trace.steps) || !trace.steps.length) return null;
  const details = elem("details", "trace");
  details.open = false;
  const steps = trace.steps;
  details.appendChild(elem("summary", "", `Trace · ${steps.length} steps · ${Math.round(trace.total_ms || 0)} ms`));
  const body = elem("div", "trace-body");
  const routing = (trace.routing && trace.routing.selected) ? trace.routing.selected.join(", ") : "none";
  body.appendChild(elem("div", "trace-row route", `route: ${routing}`));
  for (const step of steps) {
    const row = elem("div", "trace-row");
    row.appendChild(elem("strong", "", step.module));
    row.appendChild(elem("span", "", `${Math.round(step.ms || 0)} ms`));
    row.appendChild(elem("span", "note", step.ok === false ? `failed: ${step.note || step.output}` : (step.note || step.output || "")));
    body.appendChild(row);
  }
  details.appendChild(body);
  return details;
}

function addMessage(role, text, payload = null) {
  clearEmptyState();
  const wrap = elem("div", `msg ${role}`);
  wrap.appendChild(elem("div", "who", role === "user" ? "you" : role === "error" ? "error" : "ashura"));
  wrap.appendChild(elem("div", "bubble", text || "(empty response)"));
  if (payload && role === "assistant") {
    const meta = elem("div", "msg-meta");
    if (payload.verified === true) meta.appendChild(badge("verified", "ok"));
    else if (payload.verified === false) meta.appendChild(badge("unverified", "warn"));
    if (payload.admission) meta.appendChild(badge(payload.admission));
    if (payload.correction) meta.appendChild(badge("correction", "warn"));
    if (meta.childNodes.length) wrap.appendChild(meta);
    if (payload.attribution) wrap.appendChild(elem("div", "muted", payload.attribution));
    if (showTrace.checked) {
      const trace = renderTrace(payload.trace);
      if (trace) wrap.appendChild(trace);
    }
  }
  chat.appendChild(wrap);
  chat.scrollTop = chat.scrollHeight;
  return wrap;
}

async function request(path, options = {}) {
  const response = await fetch(path, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`server returned ${response.status}`);
  }
  if (!response.ok) throw new Error(data.error || `request failed (${response.status})`);
  return data;
}

async function refreshStatus() {
  const target = $("#status");
  try {
    const status = await request("/api/status");
    target.replaceChildren();
    const counts = status.counts || {};
    const add = (label, value, wide = false) => {
      const card = elem("div", `stat${wide ? " wide" : ""}`);
      card.appendChild(elem("span", "k", label));
      card.appendChild(elem("span", "v", value === null || value === undefined ? "n/a" : String(value)));
      target.appendChild(card);
    };
    add("model", status.model, true);
    add("experiences", counts.experiences);
    add("facts", counts.facts);
    add("open conflicts", counts.conflicts_open);
    add("FTS rows", counts.fts_rows);
    add("uptime", `${Math.round(status.uptime_s || 0)} s`);
    $("#model-label").textContent = `${status.model} · ${status.database || "in-memory"}`;
  } catch (error) {
    target.replaceChildren(elem("p", "muted", `status unavailable: ${error.message}`));
  }
}

function renderMemory(items) {
  memoryResults.replaceChildren();
  if (!items || !items.length) {
    memoryResults.appendChild(elem("p", "muted", "No matching memories."));
    return;
  }
  for (const item of items) {
    const card = elem("article", "memory-item");
    card.appendChild(elem("div", "q", item.input || "(no input)"));
    card.appendChild(elem("div", "a", item.output || "(no output)"));
    const meta = elem("div", "memory-meta");
    const status = String(item.status || "unknown");
    meta.appendChild(badge(status, status === "verified" ? "ok" : status === "user_provided" ? "warn" : ""));
    if (item.category) meta.appendChild(badge(item.category));
    if (item.conflict) meta.appendChild(badge("conflict", "bad"));
    card.appendChild(meta);
    card.addEventListener("click", () => {
      input.value = item.input || "";
      input.focus();
    });
    memoryResults.appendChild(card);
  }
}

async function searchMemory() {
  const query = memoryQuery.value.trim();
  try {
    const data = await request(`/api/memory?q=${encodeURIComponent(query)}&limit=20`);
    renderMemory(data.items);
  } catch (error) {
    memoryResults.replaceChildren(elem("p", "muted", `search failed: ${error.message}`));
  }
}

async function sendMessage(text) {
  if (!text || busy) return;
  busy = true;
  send.disabled = true;
  send.textContent = "Thinking…";
  addMessage("user", text);
  input.value = "";
  try {
    const data = await request("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    addMessage("assistant", data.text, data);
  } catch (error) {
    addMessage("error", error.message);
  } finally {
    busy = false;
    send.disabled = false;
    send.textContent = "Send";
    refreshStatus();
  }
}

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error("could not read file"));
    reader.readAsDataURL(file);
  });
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value.trim());
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

$("#memory-search").addEventListener("click", searchMemory);
memoryQuery.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    searchMemory();
  }
});

ocrFile.addEventListener("change", async () => {
  const file = ocrFile.files && ocrFile.files[0];
  if (!file || busy) {
    ocrFile.value = "";
    return;
  }
  busy = true;
  send.disabled = true;
  send.textContent = "Reading…";
  addMessage("user", `OCR: ${file.name}`);
  try {
    const dataUrl = await readAsDataURL(file);
    const encoded = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
    const data = await request("/api/ocr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename: file.name, data: encoded }),
    });
    addMessage("assistant", data.text || "(no text recognized)", data);
  } catch (error) {
    addMessage("error", error.message);
  } finally {
    ocrFile.value = "";
    busy = false;
    send.disabled = false;
    send.textContent = "Send";
    refreshStatus();
  }
});

refreshStatus();
searchMemory();
