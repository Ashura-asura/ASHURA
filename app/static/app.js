"use strict";

/* ASHURA local UI. No framework, no external requests, no inline handlers. */

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const state = {
  csrf: null,
  status: null,
  sessions: [],
  currentSessionId: null,
  messages: [],
  streaming: null,
  busy: false,
  inspectPayload: null,
  inspectorTab: "trace",
  sessionFilter: "",
  memoryQuery: "",
  memoryLoaded: false,
  memoryLoading: false,
  sessionsLoading: false,
  booted: false,
};

class ApiError extends Error {
  constructor(message, status, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

const dom = {};
let emptyTemplate = null;
let toastTimer = null;
let streamRenderScheduled = false;

/* --------------------------------------------------------------------------------------
   Small helpers
   -------------------------------------------------------------------------------------- */

function el(tag, className = "", text = undefined) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatMs(ms) {
  const value = Number(ms) || 0;
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 2 : 1)} s`;
}

function formatDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`;
}

function relativeTime(timestamp) {
  const value = Number(timestamp);
  if (!value) return "unknown";
  const seconds = Math.max(0, Date.now() / 1000 - value);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(value * 1000).toLocaleDateString();
}

function formatCount(value) {
  return value === null || value === undefined ? "—" : Number(value).toLocaleString();
}

function badge(text, tone = "") {
  return el("span", `badge${tone ? ` ${tone}` : ""}`, text);
}

function toast(message, tone = "") {
  if (!dom.toast) return;
  dom.toast.textContent = message;
  dom.toast.className = `toast${tone ? ` ${tone}` : ""}`;
  dom.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.hidden = true;
  }, 3600);
}

function closeDialog(dialog) {
  if (dialog && dialog.open) dialog.close();
}

function isNarrow() {
  return window.matchMedia("(max-width: 1180px)").matches;
}

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

function setConnection(mode, text) {
  const dot = dom.connectionDot;
  if (!dot) return;
  dot.classList.remove("dot-on", "dot-warn", "dot-off");
  dot.classList.add(mode === "on" ? "dot-on" : mode === "warn" ? "dot-warn" : "dot-off");
  if (dom.connectionText) dom.connectionText.textContent = text;
}

function syncScrim() {
  if (!dom.scrim) return;
  const open = document.body.classList.contains("sidebar-open") ||
    (isNarrow() && document.body.classList.contains("inspector-open"));
  dom.scrim.hidden = !open;
}

function closePanels() {
  document.body.classList.remove("sidebar-open", "inspector-open");
  syncScrim();
}

/* --------------------------------------------------------------------------------------
   HTTP / auth
   -------------------------------------------------------------------------------------- */

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (state.csrf && method !== "GET" && method !== "HEAD") {
    headers.set("X-CSRF-Token", state.csrf);
  }
  const response = await fetch(path, {
    ...options,
    method,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401) {
    showUnlock();
    throw new ApiError("Authentication required", 401);
  }
  return response;
}

async function apiJson(path, options = {}) {
  let response;
  try {
    response = await api(path, options);
  } catch (error) {
    if (error instanceof TypeError) {
      setConnection("off", "offline");
    }
    throw error;
  }
  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = null;
    }
  }
  if (!response.ok) {
    const message = data && data.error ? data.error : `request failed (${response.status})`;
    throw new ApiError(message, response.status, data && data.request_id);
  }
  return data;
}

function showUnlock() {
  if (!dom.unlockDialog || dom.unlockDialog.open) return;
  dom.unlockError.hidden = true;
  dom.unlockToken.value = "";
  dom.unlockDialog.showModal();
  dom.unlockToken.focus();
}

async function login(event) {
  event.preventDefault();
  const token = dom.unlockToken.value.trim();
  if (!token) return;
  dom.unlockSubmit.disabled = true;
  dom.unlockError.hidden = true;
  try {
    const data = await apiJson("/api/login", {
      method: "POST",
      body: JSON.stringify({ token }),
    });
    state.csrf = data.csrf || null;
    closeDialog(dom.unlockDialog);
    await bootstrap();
    toast("Unlocked");
  } catch (error) {
    dom.unlockError.textContent = error.message || "Could not unlock";
    dom.unlockError.hidden = false;
  } finally {
    dom.unlockSubmit.disabled = false;
  }
}

/* --------------------------------------------------------------------------------------
   Bootstrap / status
   -------------------------------------------------------------------------------------- */

async function bootstrap() {
  try {
    const status = await apiJson("/api/status");
    state.csrf = status.csrf || state.csrf;
    applyStatus(status);
    await loadSessions();
    if (state.sessions.length) {
      await selectSession(state.sessions[0].id, { quiet: true });
    } else {
      await newChat();
    }
    state.booted = true;
    setConnection("on", "local · online");
  } catch (error) {
    if (error.status === 401) {
      showUnlock();
    } else {
      setConnection("off", "offline");
      toast(error.message || "Could not reach the local server", "bad");
    }
  }
}

function applyStatus(status) {
  state.status = status;
  if (dom.modelName) dom.modelName.textContent = status.model || "unknown model";
  if (dom.modelDetail) {
    const db = status.database || "in-memory";
    dom.modelDetail.textContent = `${db} · v${status.version || "?"}`;
  }
  if (dom.workerPill) {
    const worker = status.worker || {};
    const depth = Number(worker.queue_depth) || 0;
    const active = worker.active;
    dom.workerPill.textContent = active
      ? `${active} running`
      : depth
        ? `${depth} queued`
        : "worker idle";
    dom.workerPill.classList.toggle("busy", Boolean(active || depth));
  }
  renderStatusPanel(status);
  updateChatHeading();
}

async function refreshStatus() {
  if (!state.csrf || document.visibilityState !== "visible") return;
  try {
    const status = await apiJson("/api/status");
    applyStatus(status);
    setConnection("on", "local · online");
  } catch (error) {
    if (error.status !== 401) setConnection("warn", "status unavailable");
  }
}

function addStat(grid, key, value, options = {}) {
  const card = el("div", `stat${options.wide ? " wide" : ""}`);
  card.appendChild(el("span", "k", key));
  card.appendChild(el("span", `v${options.mono ? " mono" : ""}`,
    value === null || value === undefined ? "—" : String(value)));
  grid.appendChild(card);
}

function renderStatusPanel(status) {
  if (!dom.statusGrid) return;
  const worker = status.worker || {};
  const counts = status.counts || {};
  dom.statusGrid.replaceChildren();
  addStat(dom.statusGrid, "model", status.model, { wide: true });
  addStat(dom.statusGrid, "database", status.database || "in-memory", { wide: true, mono: true });
  addStat(dom.statusGrid, "sessions", formatCount(status.sessions));
  addStat(dom.statusGrid, "experiences", formatCount(counts.experiences));
  addStat(dom.statusGrid, "facts", formatCount(counts.facts));
  addStat(dom.statusGrid, "open conflicts", formatCount(counts.conflicts_open));
  addStat(dom.statusGrid, "queue", `${formatCount(worker.queue_depth)} / ${formatCount(worker.max_queue)}`);
  addStat(dom.statusGrid, "worker", worker.active || "idle");
  addStat(dom.statusGrid, "avg wait", worker.avg_wait_ms === undefined ? "—" : formatMs(worker.avg_wait_ms));
  addStat(dom.statusGrid, "avg run", worker.avg_run_ms === undefined ? "—" : formatMs(worker.avg_run_ms));
  addStat(dom.statusGrid, "uptime", formatDuration(status.uptime_s), { wide: true });
  if (worker.last) {
    addStat(dom.statusGrid, "last job",
      `${worker.last.kind || "task"} · ${worker.last.status || "?"}`, { wide: true, mono: true });
  }
  if (dom.statusUpdated) {
    dom.statusUpdated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }
}

/* --------------------------------------------------------------------------------------
   Sessions
   -------------------------------------------------------------------------------------- */

async function loadSessions() {
  if (state.sessionsLoading) return;
  state.sessionsLoading = true;
  try {
    const data = await apiJson("/api/sessions?limit=100");
    state.sessions = Array.isArray(data.sessions) ? data.sessions : [];
    renderSessions();
    updateChatHeading();
  } catch (error) {
    if (error.status !== 401) toast(error.message || "Could not load sessions", "bad");
  } finally {
    state.sessionsLoading = false;
  }
}

function renderSessions() {
  if (!dom.sessionList) return;
  dom.sessionList.replaceChildren();
  const filter = state.sessionFilter.trim().toLowerCase();
  const sessions = state.sessions.filter((session) =>
    !filter || String(session.title || "").toLowerCase().includes(filter));
  if (dom.sessionCount) dom.sessionCount.textContent = String(state.sessions.length);
  if (!sessions.length) {
    dom.sessionList.appendChild(el("p", "session-empty",
      filter ? "No sessions match that filter." : "No sessions yet. Start a new chat."));
    return;
  }
  for (const session of sessions) {
    const item = el("div", "session-item");
    if (session.id === state.currentSessionId) item.classList.add("is-active");
    item.setAttribute("role", "listitem");

    const main = el("button", "session-main");
    main.type = "button";
    main.title = session.title || "Untitled session";
    main.appendChild(el("span", "session-title", session.title || "New chat"));
    const meta = el("span", "session-meta",
      `${formatCount(session.message_count)} messages · ${relativeTime(session.updated)}`);
    main.appendChild(meta);
    main.addEventListener("click", () => selectSession(session.id));
    main.addEventListener("dblclick", () => openRename(session));
    item.appendChild(main);

    const actions = el("span", "session-actions");
    const rename = el("button", "", "✎");
    rename.type = "button";
    rename.title = "Rename session";
    rename.setAttribute("aria-label", `Rename ${session.title || "session"}`);
    rename.addEventListener("click", (event) => {
      event.stopPropagation();
      openRename(session);
    });
    const remove = el("button", "", "×");
    remove.type = "button";
    remove.title = "Delete session";
    remove.setAttribute("aria-label", `Delete ${session.title || "session"}`);
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      removeSession(session);
    });
    actions.append(rename, remove);
    item.appendChild(actions);
    dom.sessionList.appendChild(item);
  }
}

async function newChat() {
  if (state.busy || state.streaming) {
    toast("Stop the current response first.", "bad");
    return;
  }
  if (state.currentSessionId && state.messages.length === 0) {
    dom.message.focus();
    closePanels();
    return;
  }
  const empty = state.sessions.find((session) =>
    Number(session.message_count) === 0 && String(session.title || "") === "New chat");
  if (empty) {
    await selectSession(empty.id);
    return;
  }
  try {
    const data = await apiJson("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: "New chat" }),
    });
    state.currentSessionId = data.session.id;
    state.messages = [];
    state.inspectPayload = null;
    await loadSessions();
    renderChat();
    renderTrace(null);
    updateChatHeading();
    closePanels();
    dom.message.focus();
  } catch (error) {
    if (error.status !== 401) toast(error.message || "Could not create a session", "bad");
  }
}

async function selectSession(sessionId, options = {}) {
  if (state.busy || state.streaming) {
    toast("Stop the current response first.", "bad");
    return;
  }
  if (!sessionId) return;
  try {
    const data = await apiJson(`/api/sessions/${encodeURIComponent(sessionId)}`);
    state.currentSessionId = data.session.id;
    state.messages = Array.isArray(data.messages) ? data.messages : [];
    const last = [...state.messages].reverse().find((message) =>
      message.role === "assistant" && message.meta && message.meta.trace);
    state.inspectPayload = last ? payloadFromMessage(last) : null;
    renderChat();
    renderSessions();
    updateChatHeading();
    if (!options.quiet) closePanels();
    if (options.quiet) {
      chatScrollToBottom(false);
    } else {
      chatScrollToBottom(true);
    }
    renderTrace(state.inspectPayload);
  } catch (error) {
    if (error.status === 404) {
      toast("That session no longer exists.", "bad");
      await loadSessions();
      if (state.sessions.length) await selectSession(state.sessions[0].id, { quiet: true });
      else await newChat();
    } else if (error.status !== 401) {
      toast(error.message || "Could not open the session", "bad");
    }
  }
}

function openRename(session) {
  state.renameSessionId = session.id;
  dom.renameTitle.value = session.title || "";
  dom.renameError.hidden = true;
  dom.renameDialog.showModal();
  dom.renameTitle.focus();
  dom.renameTitle.select();
}

async function submitRename(event) {
  event.preventDefault();
  const title = dom.renameTitle.value.trim();
  if (!title || !state.renameSessionId) return;
  try {
    const data = await apiJson(`/api/sessions/${encodeURIComponent(state.renameSessionId)}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
    const index = state.sessions.findIndex((session) => session.id === data.session.id);
    if (index >= 0) state.sessions[index] = { ...state.sessions[index], ...data.session };
    closeDialog(dom.renameDialog);
    renderSessions();
    updateChatHeading();
    toast("Session renamed");
  } catch (error) {
    dom.renameError.textContent = error.message || "Could not rename";
    dom.renameError.hidden = false;
  }
}

function askConfirm(message) {
  return new Promise((resolve) => {
    dom.confirmMessage.textContent = message;
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      dom.confirmDialog.removeEventListener("click", onClick);
      dom.confirmDialog.removeEventListener("cancel", onCancel);
      if (dom.confirmDialog.open) dom.confirmDialog.close();
      resolve(value);
    };
    const onClick = (event) => {
      const button = event.target.closest("[data-confirm]");
      if (!button) return;
      finish(button.dataset.confirm === "yes");
    };
    const onCancel = (event) => {
      event.preventDefault();
      finish(false);
    };
    dom.confirmDialog.addEventListener("click", onClick);
    dom.confirmDialog.addEventListener("cancel", onCancel);
    dom.confirmDialog.showModal();
  });
}

async function removeSession(session) {
  if (state.streaming || state.busy) {
    toast("Stop the current response first.", "bad");
    return;
  }
  const confirmed = await askConfirm(`Delete “${session.title || "this session"}” and its messages?`);
  if (!confirmed) return;
  try {
    await apiJson(`/api/sessions/${encodeURIComponent(session.id)}`, { method: "DELETE" });
    if (state.currentSessionId === session.id) {
      state.currentSessionId = null;
      state.messages = [];
      state.inspectPayload = null;
    }
    await loadSessions();
    if (!state.currentSessionId) {
      if (state.sessions.length) await selectSession(state.sessions[0].id, { quiet: true });
      else await newChat();
    } else {
      renderChat();
      updateChatHeading();
    }
    toast("Session deleted");
  } catch (error) {
    if (error.status !== 401) toast(error.message || "Could not delete the session", "bad");
  }
}

function updateChatHeading() {
  const session = state.sessions.find((item) => item.id === state.currentSessionId);
  if (dom.chatTitle) dom.chatTitle.textContent = session ? (session.title || "New chat") : "New chat";
  if (dom.chatSubtitle) {
    const model = state.status && state.status.model ? state.status.model : "local model";
    const count = state.messages.length;
    dom.chatSubtitle.textContent = count
      ? `${count} message${count === 1 ? "" : "s"} · ${model}`
      : "Streaming local answers with a measured trace.";
  }
  if (dom.exportChat) dom.exportChat.disabled = !state.currentSessionId;
}

/* --------------------------------------------------------------------------------------
   Markdown
   -------------------------------------------------------------------------------------- */

function renderCodeBlock(block) {
  const language = escapeHtml(String(block.lang || "code").replace(/[^A-Za-z0-9_+.-]/g, "")) || "code";
  const code = escapeHtml(String(block.code || "").replace(/\n$/, ""));
  return `<div class="code-block"><div class="code-head"><span>${language}</span>` +
    `<button type="button" class="copy-code" data-action="copy-code">Copy</button></div>` +
    `<pre><code>${code}</code></pre></div>`;
}

function renderMarkdown(source) {
  const text = String(source ?? "");
  const codeBlocks = [];
  let working = text.replace(/```([A-Za-z0-9_+.-]*)[ \t]*\r?\n?([\s\S]*?)```/g,
    (match, lang, code) => {
      codeBlocks.push({ lang, code });
      return `\n\u0000CODE${codeBlocks.length - 1}\u0000\n`;
    });
  const inlineCodes = [];
  working = working.replace(/`([^`\n]+)`/g, (match, code) => {
    inlineCodes.push(code);
    return `\u0001IC${inlineCodes.length - 1}\u0001`;
  });

  let html = escapeHtml(working);
  html = html.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g,
    (match, label, url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`);
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  html = html.replace(/~~([^~\n]+)~~/g, "<del>$1</del>");

  const lines = html.split("\n");
  const output = [];
  let listType = null;
  const closeList = () => {
    if (listType) {
      output.push(`</${listType}>`);
      listType = null;
    }
  };
  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    const trimmed = line.trim();
    if (!trimmed) {
      closeList();
      continue;
    }
    let match;
    if ((match = trimmed.match(/^\u0000CODE(\d+)\u0000$/))) {
      closeList();
      output.push(renderCodeBlock(codeBlocks[Number(match[1])] || { code: "" }));
      continue;
    }
    if ((match = trimmed.match(/^(#{1,4})\s+(.*)$/))) {
      closeList();
      const level = Math.min(6, match[1].length + 2);
      output.push(`<h${level}>${match[2]}</h${level}>`);
      continue;
    }
    if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
      closeList();
      output.push("<hr>");
      continue;
    }
    if ((match = trimmed.match(/^&gt;\s?(.*)$/))) {
      closeList();
      output.push(`<blockquote>${match[1]}</blockquote>`);
      continue;
    }
    if ((match = trimmed.match(/^[-*+]\s+(.*)$/))) {
      if (listType !== "ul") {
        closeList();
        output.push("<ul>");
        listType = "ul";
      }
      output.push(`<li>${match[1]}</li>`);
      continue;
    }
    if ((match = trimmed.match(/^\d+[.)]\s+(.*)$/))) {
      if (listType !== "ol") {
        closeList();
        output.push("<ol>");
        listType = "ol";
      }
      output.push(`<li>${match[1]}</li>`);
      continue;
    }
    closeList();
    output.push(`<p>${trimmed}</p>`);
  }
  closeList();
  let result = output.join("");
  result = result.replace(/\u0001IC(\d+)\u0001/g,
    (match, index) => `<code>${escapeHtml(inlineCodes[Number(index)] ?? "")}</code>`);
  return result;
}

/* --------------------------------------------------------------------------------------
   Chat rendering
   -------------------------------------------------------------------------------------- */

function payloadFromMessage(message) {
  const meta = message.meta || {};
  return {
    text: message.content || "",
    verified: meta.verified,
    verification: meta.verification,
    admission: meta.admission,
    attribution: meta.attribution,
    correction: meta.correction,
    model: meta.model,
    trace: meta.trace,
  };
}

function messageFromPayload(payload, overrides = {}) {
  return {
    id: payload.assistant_message_id || null,
    role: "assistant",
    content: payload.text || "",
    ts: Date.now() / 1000,
    meta: payloadFromMessage({
      content: payload.text || "",
      meta: {
        kind: payload.kind || "chat",
        model: payload.model,
        verified: payload.verified,
        verification: payload.verification,
        admission: payload.admission,
        attribution: payload.attribution,
        correction: payload.correction,
        trace: payload.trace,
      },
    }),
    ...overrides,
  };
}

function renderMeta(payload) {
  const meta = el("div", "msg-meta");
  if (payload.verified === true) meta.appendChild(badge("verified", "ok"));
  else if (payload.verified === false) meta.appendChild(badge("unverified", "warn"));
  else if (payload.verification === "unavailable") meta.appendChild(badge("unverified", "warn"));
  if (payload.model) meta.appendChild(badge(payload.model));
  if (payload.admission) meta.appendChild(badge(payload.admission));
  if (payload.correction) meta.appendChild(badge("correction", "warn"));
  if (payload.stopped) meta.appendChild(badge("stopped", "warn"));
  return meta;
}

function buildInlineTrace(payload) {
  const trace = payload.trace;
  if (!trace || !Array.isArray(trace.steps) || !trace.steps.length) return null;
  const details = el("details", "trace-inline");
  const summary = el("summary", "",
    `Trace · ${trace.steps.length} step${trace.steps.length === 1 ? "" : "s"} · ${formatMs(trace.total_ms)}`);
  details.appendChild(summary);
  const body = el("div", "trace-inline-body");
  const route = trace.routing && Array.isArray(trace.routing.selected)
    ? trace.routing.selected.join(", ")
    : "none";
  body.appendChild(el("p", "muted small", `route: ${route}`));
  for (const step of trace.steps.slice(0, 6)) {
    const row = el("p", "trace-inline-row");
    row.appendChild(el("strong", "", step.module));
    row.appendChild(document.createTextNode(` · ${formatMs(step.ms)}`));
    const detail = step.ok === false ? (step.note || step.output || "failed") : (step.note || step.output || "");
    if (detail) row.appendChild(document.createTextNode(` — ${detail}`));
    body.appendChild(row);
  }
  if (trace.steps.length > 6) {
    body.appendChild(el("p", "muted small", `+${trace.steps.length - 6} more in the inspector`));
  }
  details.appendChild(body);
  return details;
}

function renderMessage(message, index) {
  const role = message.role === "error" ? "error" : message.role === "user" ? "user" : "assistant";
  const wrap = el("div", `msg ${role}`);
  wrap.dataset.messageIndex = String(index);

  const head = el("div", "msg-head");
  head.appendChild(el("span", "", role === "user" ? "you" : role === "error" ? "error" : "ashura"));
  if (message.ts) head.appendChild(el("span", "muted", new Date(message.ts * 1000).toLocaleTimeString()));
  const actions = el("span", "msg-actions");
  if (message.content) {
    const copy = el("button", "", "Copy");
    copy.type = "button";
    copy.dataset.action = "copy";
    copy.title = "Copy message";
    actions.appendChild(copy);
  }
  if (role === "assistant" || role === "error") {
    const retry = el("button", "", "Retry");
    retry.type = "button";
    retry.dataset.action = "retry";
    retry.title = "Send the previous question again";
    actions.appendChild(retry);
  }
  const metaTrace = message.meta && message.meta.trace;
  if (metaTrace) {
    const inspect = el("button", "", "Trace");
    inspect.type = "button";
    inspect.dataset.action = "trace";
    inspect.title = "Inspect this answer";
    actions.appendChild(inspect);
  }
  head.appendChild(actions);
  wrap.appendChild(head);

  const bubble = el("div", "bubble");
  if (role === "user") {
    bubble.textContent = message.content || "";
  } else {
    bubble.innerHTML = renderMarkdown(message.content || "");
    bubble.classList.add("md");
  }
  wrap.appendChild(bubble);

  if (role === "assistant" && message.meta) {
    const payload = payloadFromMessage(message);
    const meta = renderMeta(payload);
    if (meta.childNodes.length) wrap.appendChild(meta);
    if (payload.attribution) {
      wrap.appendChild(el("div", "msg-attribution", payload.attribution));
    }
    const trace = buildInlineTrace(payload);
    if (trace) wrap.appendChild(trace);
  }
  return wrap;
}

function renderChat() {
  if (!dom.chat) return;
  dom.chat.replaceChildren();
  if (!state.messages.length) {
    if (emptyTemplate) dom.chat.appendChild(emptyTemplate.cloneNode(true));
    updateChatHeading();
    return;
  }
  state.messages.forEach((message, index) => {
    dom.chat.appendChild(renderMessage(message, index));
  });
  updateChatHeading();
}

function clearEmptyState() {
  const empty = dom.chat && dom.chat.querySelector(".empty-state");
  if (empty) empty.remove();
}

function chatScrollToBottom(force = true) {
  if (!dom.chat) return;
  if (force) dom.chat.scrollTop = dom.chat.scrollHeight;
  updateJumpLatest();
}

function nearBottom() {
  if (!dom.chat) return true;
  return dom.chat.scrollHeight - dom.chat.scrollTop - dom.chat.clientHeight < 140;
}

function updateJumpLatest() {
  if (!dom.jumpLatest) return;
  dom.jumpLatest.hidden = nearBottom();
}

function addStreamingMessage() {
  const wrap = el("div", "msg assistant streaming");
  const head = el("div", "msg-head");
  head.appendChild(el("span", "", "ashura"));
  head.appendChild(el("span", "muted", "streaming"));
  wrap.appendChild(head);
  const bubble = el("div", "bubble md");
  wrap.appendChild(bubble);
  dom.chat.appendChild(wrap);
  chatScrollToBottom(true);
  return { wrap, bubble };
}

function scheduleStreamRender() {
  if (streamRenderScheduled) return;
  streamRenderScheduled = true;
  requestAnimationFrame(() => {
    streamRenderScheduled = false;
    const stream = state.streaming;
    if (!stream || stream.finalized || !stream.bubble) return;
    stream.bubble.innerHTML = renderMarkdown(stream.text || "…");
    if (nearBottom()) chatScrollToBottom(false);
  });
}

function finishStreaming(payload) {
  const stream = state.streaming;
  if (!stream || stream.finalized) return;
  stream.finalized = true;
  const user = stream.user;
  if (user && payload.user_message_id) user.id = payload.user_message_id;
  const message = messageFromPayload(payload);
  state.messages.push(message);
  const node = renderMessage(message, state.messages.length - 1);
  stream.wrap.replaceWith(node);
  state.inspectPayload = payload;
  renderTrace(payload);
  updateChatHeading();
  if (nearBottom()) chatScrollToBottom(false);
  loadSessions();
  refreshStatus();
}

function cancelStreaming() {
  const stream = state.streaming;
  if (!stream || stream.finalized) return;
  stream.finalized = true;
  stream.stopped = true;
  const partial = (stream.text || "").trim();
  const message = {
    role: "assistant",
    content: partial || "Stopped.",
    ts: Date.now() / 1000,
    local: true,
    meta: { kind: "chat", stopped: true, verified: null, trace: null },
  };
  state.messages.push(message);
  const node = renderMessage(message, state.messages.length - 1);
  stream.wrap.replaceWith(node);
  updateChatHeading();
  toast("Generation stopped");
}

function failStreaming(message) {
  const stream = state.streaming;
  if (!stream || stream.finalized) return;
  stream.finalized = true;
  const errorMessage = {
    role: "error",
    content: message || "The local model did not return an answer.",
    ts: Date.now() / 1000,
    local: true,
    meta: { kind: "chat", verified: null },
  };
  state.messages.push(errorMessage);
  const node = renderMessage(errorMessage, state.messages.length - 1);
  stream.wrap.replaceWith(node);
  updateChatHeading();
  toast(errorMessage.content, "bad");
}

function setComposerBusy(busy, { canStop = false } = {}) {
  state.busy = busy;
  if (dom.send) {
    dom.send.disabled = busy;
    dom.send.textContent = busy && !canStop ? "Working…" : "Send";
  }
  if (dom.stop) dom.stop.hidden = !(busy && canStop);
  if (dom.composerHint) {
    dom.composerHint.textContent = busy
      ? (canStop ? "Streaming locally…" : "Working locally…")
      : "Enter sends · Shift+Enter adds a line";
  }
}

function consumeEvent(event) {
  const stream = state.streaming;
  if (event.name === "meta") {
    if (!stream) return;
    if (event.data.session_id) stream.sessionId = event.data.session_id;
    return;
  }
  if (!stream || stream.finalized) return;
  if (event.name === "token") {
    stream.text += event.data.text || "";
    scheduleStreamRender();
  } else if (event.name === "done") {
    finishStreaming(event.data);
  } else if (event.name === "error") {
    failStreaming(event.data.error || "The local model reported an error.");
  } else if (event.name === "cancelled") {
    cancelStreaming();
  }
}

function parseEventBlock(block) {
  let name = "message";
  const dataLines = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) name = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
  }
  if (!dataLines.length) return null;
  try {
    return { name, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

async function consumeSSE(response) {
  if (!response.body) throw new Error("streaming is not supported by this browser");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let index;
      while ((index = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);
        const event = parseEventBlock(block);
        if (event) consumeEvent(event);
        if (state.streaming && state.streaming.finalized) {
          try { await reader.cancel(); } catch { /* already gone */ }
          return;
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* ignore */ }
  }
}

async function sendMessage(rawText) {
  if (state.busy || state.streaming) return;
  const text = String(rawText || "").trim();
  if (!text) return;
  if (!state.csrf) {
    showUnlock();
    return;
  }
  if (!state.currentSessionId) {
    await newChat();
    if (!state.currentSessionId) return;
  }
  clearEmptyState();
  const user = {
    role: "user",
    content: text,
    ts: Date.now() / 1000,
    local: true,
    meta: { kind: "chat" },
  };
  state.messages.push(user);
  const userNode = renderMessage(user, state.messages.length - 1);
  dom.chat.appendChild(userNode);
  const placeholder = addStreamingMessage();
  dom.message.value = "";
  autoResize();
  setComposerBusy(true, { canStop: true });

  const controller = new AbortController();
  const stream = {
    controller,
    user,
    text: "",
    wrap: placeholder.wrap,
    bubble: placeholder.bubble,
    finalized: false,
    stopped: false,
    sessionId: state.currentSessionId,
  };
  state.streaming = stream;
  chatScrollToBottom(false);

  try {
    const response = await api("/api/chat/stream", {
      method: "POST",
      body: JSON.stringify({ message: text, session_id: state.currentSessionId }),
      signal: controller.signal,
    });
    if (!response.ok) {
      let message = `request failed (${response.status})`;
      try {
        const data = await response.json();
        if (data && data.error) message = data.error;
      } catch { /* keep fallback */ }
      throw new ApiError(message, response.status);
    }
    await consumeSSE(response);
    if (!stream.finalized) {
      if (stream.stopped) cancelStreaming();
      else failStreaming("The stream ended before an answer arrived.");
    }
  } catch (error) {
    if (error.name === "AbortError" || stream.stopped) {
      cancelStreaming();
    } else if (!stream.finalized) {
      failStreaming(error.message || "Could not reach the local model.");
    }
  } finally {
    if (state.streaming === stream) state.streaming = null;
    setComposerBusy(false);
    refreshStatus();
  }
}

function stopStreaming() {
  const stream = state.streaming;
  if (!stream) return;
  stream.stopped = true;
  try { stream.controller.abort(); } catch { /* ignore */ }
  cancelStreaming();
}

function retryAt(index) {
  if (state.busy || state.streaming) return;
  let cursor = index;
  while (cursor >= 0 && state.messages[cursor] && state.messages[cursor].role !== "user") cursor -= 1;
  if (cursor < 0) {
    toast("No earlier question to retry.", "bad");
    return;
  }
  const message = state.messages[cursor];
  if (message.content.startsWith("[image:")) {
    toast("Re-upload the image to retry OCR.", "bad");
    return;
  }
  sendMessage(message.content);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied");
  } catch {
    const area = el("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); toast("Copied"); }
    catch { toast("Could not copy", "bad"); }
    area.remove();
  }
}

function autoResize() {
  if (!dom.message) return;
  dom.message.style.height = "auto";
  dom.message.style.height = `${Math.min(dom.message.scrollHeight, 210)}px`;
}

/* --------------------------------------------------------------------------------------
   Inspector: trace
   -------------------------------------------------------------------------------------- */

function renderTrace(payload) {
  if (!dom.traceSummary || !dom.traceContent) return;
  dom.traceSummary.replaceChildren();
  dom.traceContent.replaceChildren();
  const trace = payload && payload.trace;
  if (!trace) {
    dom.traceContent.appendChild(el("p", "trace-empty",
      "No trace yet. Send a message, then choose Trace on an answer or use Latest."));
    return;
  }
  dom.traceSummary.appendChild(badge(payload.verified === true ? "verified" : "unverified",
    payload.verified === true ? "ok" : "warn"));
  if (payload.model) dom.traceSummary.appendChild(badge(payload.model));
  if (payload.admission) dom.traceSummary.appendChild(badge(payload.admission));
  dom.traceSummary.appendChild(badge(formatMs(trace.total_ms)));

  const routeBox = el("div", "trace-route");
  const selected = (trace.routing && trace.routing.selected) || [];
  const skipped = (trace.routing && trace.routing.skipped) || [];
  routeBox.appendChild(el("span", "muted small", "selected"));
  selected.forEach((name) => routeBox.appendChild(badge(name)));
  if (skipped.length) {
    routeBox.appendChild(el("span", "muted small", "skipped"));
    skipped.forEach((name) => routeBox.appendChild(badge(name)));
  }
  dom.traceContent.appendChild(routeBox);

  const totals = el("div", "trace-total");
  addStat(totals, "routing", formatMs(trace.routing_ms));
  addStat(totals, "total", formatMs(trace.total_ms));
  dom.traceContent.appendChild(totals);

  const table = el("div", "trace-table");
  const steps = Array.isArray(trace.steps) ? trace.steps : [];
  const maxMs = Math.max(1, ...steps.map((step) => Number(step.ms) || 0));
  for (const step of steps) {
    const row = el("div", `trace-step${step.ok === false ? " failed" : ""}`);
    const head = el("div", "trace-step-head");
    head.appendChild(el("strong", "", step.module || "step"));
    head.appendChild(el("span", "", formatMs(step.ms)));
    row.appendChild(head);
    const bar = el("progress");
    bar.max = maxMs;
    bar.value = Math.max(0, Number(step.ms) || 0);
    row.appendChild(bar);
    const detail = step.ok === false ? (step.note || step.output || "failed") : (step.output || "");
    if (detail) row.appendChild(el("p", "", String(detail)));
    if (step.note && step.ok !== false) row.appendChild(el("p", "step-note", step.note));
    if (step.verification) row.appendChild(badge(step.verification,
      step.verification === "verified" ? "ok" : step.verification === "failed" ? "bad" : ""));
    table.appendChild(row);
  }
  if (!steps.length) table.appendChild(el("p", "trace-empty", "No step records."));
  dom.traceContent.appendChild(table);
}

function openInspector(tab = null) {
  if (tab) switchTab(tab);
  if (isNarrow()) {
    document.body.classList.remove("sidebar-open");
    document.body.classList.add("inspector-open");
  } else {
    document.body.classList.remove("inspector-closed");
  }
  if (dom.inspectorToggle) dom.inspectorToggle.setAttribute("aria-expanded", "true");
  syncScrim();
}

function closeInspector() {
  if (isNarrow()) {
    document.body.classList.remove("inspector-open");
  } else {
    document.body.classList.add("inspector-closed");
  }
  if (dom.inspectorToggle) dom.inspectorToggle.setAttribute("aria-expanded", "false");
  syncScrim();
}

function switchTab(tab) {
  state.inspectorTab = tab;
  $$(".tab-button").forEach((button) => {
    const active = button.dataset.tab === tab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  $$(".inspector-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.dataset.panel === tab);
  });
  if (tab === "memory" && !state.memoryLoaded) loadMemory("");
  if (tab === "status") renderStatusPanel(state.status || {});
}

/* --------------------------------------------------------------------------------------
   Inspector: memory
   -------------------------------------------------------------------------------------- */

async function loadMemory(query) {
  if (state.memoryLoading) return;
  state.memoryLoading = true;
  state.memoryQuery = query || "";
  dom.memoryNote.textContent = query ? `Searching for “${query}”…` : "Loading recent admissions…";
  dom.memoryResults.replaceChildren();
  try {
    const data = await apiJson(`/api/memory?q=${encodeURIComponent(query || "")}&limit=30`);
    state.memoryLoaded = true;
    renderMemory(data.items || [], query);
  } catch (error) {
    if (error.status !== 401) {
      dom.memoryNote.textContent = `Search failed: ${error.message}`;
    }
  } finally {
    state.memoryLoading = false;
  }
}

function renderMemory(items, query) {
  dom.memoryResults.replaceChildren();
  dom.memoryNote.textContent = query
    ? `${items.length} result${items.length === 1 ? "" : "s"} for “${query}”`
    : `${items.length} recent admission${items.length === 1 ? "" : "s"}`;
  if (!items.length) {
    dom.memoryResults.appendChild(el("p", "muted small", "No matching memories."));
    return;
  }
  for (const item of items) {
    const card = el("button", "memory-item");
    card.type = "button";
    card.title = "Put this prompt in the composer";
    card.appendChild(el("div", "q", item.input || "(no input)"));
    card.appendChild(el("div", "a", item.output || "(no output)"));
    const meta = el("div", "memory-meta");
    const status = String(item.status || "unknown");
    meta.appendChild(badge(status,
      status === "verified" ? "ok" : status === "user_provided" ? "warn" : ""));
    if (item.category) meta.appendChild(badge(item.category));
    if (item.method) {
      const method = badge(item.method);
      method.title = item.method;
      meta.appendChild(method);
    }
    if (item.conflict) meta.appendChild(badge("conflict", "bad"));
    card.appendChild(meta);
    card.addEventListener("click", () => {
      dom.message.value = item.input || "";
      autoResize();
      dom.message.focus();
      toast("Prompt loaded into the composer");
    });
    dom.memoryResults.appendChild(card);
  }
}

/* --------------------------------------------------------------------------------------
   OCR
   -------------------------------------------------------------------------------------- */

function readFileAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Could not read the image"));
    reader.readAsDataURL(file);
  });
}

async function handleOcrFile(file) {
  if (!file) return;
  if (state.busy || state.streaming) {
    toast("Wait for the current response first.", "bad");
    return;
  }
  if (!file.type.startsWith("image/")) {
    toast("That file is not an image.", "bad");
    return;
  }
  if (file.size > 12 * 1024 * 1024) {
    toast("Image is too large (max 12 MB).", "bad");
    return;
  }
  if (!state.currentSessionId) {
    await newChat();
    if (!state.currentSessionId) return;
  }
  clearEmptyState();
  const user = {
    role: "user",
    content: `[image: ${file.name}]`,
    ts: Date.now() / 1000,
    local: true,
    meta: { kind: "ocr", filename: file.name },
  };
  state.messages.push(user);
  dom.chat.appendChild(renderMessage(user, state.messages.length - 1));
  const placeholder = el("div", "msg assistant streaming");
  const head = el("div", "msg-head");
  head.appendChild(el("span", "", "ashura"));
  head.appendChild(el("span", "muted", "OCR"));
  placeholder.appendChild(head);
  const bubble = el("div", "bubble md");
  bubble.textContent = "Reading the image locally…";
  placeholder.appendChild(bubble);
  dom.chat.appendChild(placeholder);
  chatScrollToBottom(false);
  setComposerBusy(true, { canStop: false });

  try {
    const dataUrl = await readFileAsDataURL(file);
    const encoded = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
    const data = await apiJson("/api/ocr", {
      method: "POST",
      body: JSON.stringify({
        filename: file.name,
        data: encoded,
        session_id: state.currentSessionId,
      }),
    });
    if (data.user_message_id) user.id = data.user_message_id;
    const message = messageFromPayload(data, { meta: { ...payloadFromMessage(data), kind: "ocr" } });
    state.messages.push(message);
    const node = renderMessage(message, state.messages.length - 1);
    placeholder.replaceWith(node);
    state.inspectPayload = data;
    renderTrace(data);
    updateChatHeading();
    if (nearBottom()) chatScrollToBottom(false);
    loadSessions();
    refreshStatus();
  } catch (error) {
    if (error.status !== 401) {
      const message = {
        role: "error",
        content: error.message || "OCR failed.",
        ts: Date.now() / 1000,
        local: true,
        meta: {},
      };
      state.messages.push(message);
      placeholder.replaceWith(renderMessage(message, state.messages.length - 1));
      toast(message.content, "bad");
    } else {
      placeholder.remove();
    }
  } finally {
    setComposerBusy(false);
    updateChatHeading();
  }
}

/* --------------------------------------------------------------------------------------
   Theme / dialogs / events
   -------------------------------------------------------------------------------------- */

function applyTheme(theme) {
  const value = theme === "light" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", value);
  if (dom.themeLabel) dom.themeLabel.textContent = value === "light" ? "☀" : "☾";
  try { localStorage.setItem("ashura-theme", value); } catch { /* storage may be disabled */ }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "dark";
  applyTheme(current === "dark" ? "light" : "dark");
}

function openHelp() {
  if (!dom.helpDialog.open) dom.helpDialog.showModal();
}

function wireEvents() {
  dom.composer.addEventListener("submit", (event) => {
    event.preventDefault();
    sendMessage(dom.message.value);
  });
  dom.message.addEventListener("input", autoResize);
  dom.message.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      dom.composer.requestSubmit();
    }
  });
  dom.stop.addEventListener("click", stopStreaming);
  dom.newChat.addEventListener("click", newChat);
  dom.sessionFilter.addEventListener("input", () => {
    state.sessionFilter = dom.sessionFilter.value;
    renderSessions();
  });
  dom.memorySearch.addEventListener("click", () => loadMemory(dom.memoryQuery.value.trim()));
  dom.memoryQuery.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      loadMemory(dom.memoryQuery.value.trim());
    }
  });
  dom.statusRefresh.addEventListener("click", refreshStatus);
  dom.traceLast.addEventListener("click", () => {
    const last = [...state.messages].reverse().find((message) =>
      message.role === "assistant" && message.meta && message.meta.trace);
    if (!last) {
      toast("No traced answer yet.", "bad");
      return;
    }
    state.inspectPayload = payloadFromMessage(last);
    renderTrace(state.inspectPayload);
  });
  dom.inspectorToggle.addEventListener("click", () => {
    if (isNarrow()) {
      if (document.body.classList.contains("inspector-open")) closeInspector();
      else openInspector();
    } else if (document.body.classList.contains("inspector-closed")) {
      openInspector();
    } else {
      closeInspector();
    }
  });
  dom.inspectorClose.addEventListener("click", closeInspector);
  dom.menuToggle.addEventListener("click", () => {
    document.body.classList.add("sidebar-open");
    syncScrim();
  });
  dom.sidebarClose.addEventListener("click", closePanels);
  dom.scrim.addEventListener("click", closePanels);
  dom.openMemory.addEventListener("click", () => openInspector("memory"));
  dom.openStatus.addEventListener("click", () => openInspector("status"));
  dom.helpButton.addEventListener("click", openHelp);
  dom.themeToggle.addEventListener("click", toggleTheme);
  dom.exportChat.addEventListener("click", exportChat);
  dom.unlockForm.addEventListener("submit", login);
  dom.renameForm.addEventListener("submit", submitRename);
  $$("[data-close-dialog]").forEach((button) => {
    button.addEventListener("click", () => closeDialog(document.getElementById(button.dataset.closeDialog)));
  });
  $$(".tab-button").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  dom.chat.addEventListener("click", onChatClick);
  dom.chat.addEventListener("scroll", updateJumpLatest, { passive: true });
  dom.jumpLatest.addEventListener("click", () => chatScrollToBottom(true));

  dom.ocrFile.addEventListener("change", () => {
    const file = dom.ocrFile.files && dom.ocrFile.files[0];
    dom.ocrFile.value = "";
    if (file) handleOcrFile(file);
  });

  document.addEventListener("keydown", onGlobalKeydown);
  document.addEventListener("paste", onPaste);

  window.addEventListener("dragenter", (event) => {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
    document.body.classList.add("dragging");
  });
  window.addEventListener("dragover", (event) => {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types).includes("Files")) return;
    event.preventDefault();
  });
  window.addEventListener("dragleave", (event) => {
    if (event.relatedTarget === null) document.body.classList.remove("dragging");
  });
  window.addEventListener("drop", (event) => {
    if (!event.dataTransfer) return;
    event.preventDefault();
    document.body.classList.remove("dragging");
    const file = Array.from(event.dataTransfer.files || []).find((item) => item.type.startsWith("image/"));
    if (file) handleOcrFile(file);
    else toast("Drop an image for OCR.", "bad");
  });
  window.addEventListener("resize", () => {
    if (!isNarrow()) {
      document.body.classList.remove("sidebar-open", "inspector-open");
      syncScrim();
    }
  });
}

function onChatClick(event) {
  const actionButton = event.target.closest("[data-action]");
  if (actionButton) {
    const wrap = actionButton.closest(".msg");
    const index = wrap ? Number(wrap.dataset.messageIndex) : -1;
    const message = state.messages[index];
    if (actionButton.dataset.action === "copy" && message) {
      copyText(message.content || "");
    } else if (actionButton.dataset.action === "retry") {
      retryAt(index);
    } else if (actionButton.dataset.action === "trace" && message) {
      state.inspectPayload = payloadFromMessage(message);
      renderTrace(state.inspectPayload);
      openInspector("trace");
    } else if (actionButton.dataset.action === "copy-code") {
      const code = actionButton.closest(".code-block")?.querySelector("code");
      if (code) copyText(code.textContent || "");
    }
    return;
  }
  const prompt = event.target.closest("[data-prompt]");
  if (prompt) {
    sendMessage(prompt.dataset.prompt);
  }
}

function onGlobalKeydown(event) {
  const target = event.target;
  const typing = target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);
  if (event.key === "Escape") {
    if (state.streaming) {
      event.preventDefault();
      stopStreaming();
      return;
    }
    if (document.body.classList.contains("sidebar-open") ||
        document.body.classList.contains("inspector-open")) {
      closePanels();
      return;
    }
  }
  const modifier = event.ctrlKey || event.metaKey;
  if (modifier && !event.shiftKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    dom.sessionFilter.focus();
    dom.sessionFilter.select();
    return;
  }
  if (modifier && event.shiftKey && event.key.toLowerCase() === "o") {
    event.preventDefault();
    newChat();
    return;
  }
  if (!typing && !modifier && event.key === "?") {
    event.preventDefault();
    openHelp();
  }
}

function onPaste(event) {
  const items = event.clipboardData && event.clipboardData.items;
  if (!items) return;
  for (const item of items) {
    if (item.type && item.type.startsWith("image/")) {
      const file = item.getAsFile();
      if (file) {
        event.preventDefault();
        handleOcrFile(file);
        return;
      }
    }
  }
}

function exportChat() {
  if (!state.currentSessionId) {
    toast("Open a session first.", "bad");
    return;
  }
  const link = document.createElement("a");
  link.href = `/api/sessions/${encodeURIComponent(state.currentSessionId)}/export?format=md`;
  link.download = "";
  document.body.appendChild(link);
  link.click();
  link.remove();
}

/* --------------------------------------------------------------------------------------
   Init
   -------------------------------------------------------------------------------------- */

function cacheDom() {
  const ids = [
    "app", "sidebar", "sidebar-close", "menu-toggle", "new-chat", "session-filter",
    "session-list", "session-count", "model-name", "model-detail", "connection-dot",
    "connection-text", "worker-pill", "chat-title", "chat-subtitle", "chat",
    "empty-state", "jump-latest", "composer", "message", "send", "stop", "ocr-file",
    "composer-hint", "export-chat", "theme-toggle", "theme-label", "inspector-toggle",
    "inspector", "inspector-close", "scrim", "trace-summary", "trace-content",
    "trace-last", "memory-query", "memory-search", "memory-results", "memory-note",
    "status-grid", "status-refresh", "status-updated", "toast", "unlock-dialog",
    "unlock-form", "unlock-token", "unlock-error", "unlock-submit", "rename-dialog",
    "rename-form", "rename-title", "rename-error", "confirm-dialog", "confirm-message",
    "help-dialog", "help-button", "open-memory", "open-status", "drop-hint",
  ];
  for (const id of ids) {
    dom[id.replace(/-([a-z])/g, (match, letter) => letter.toUpperCase())] = document.getElementById(id);
  }
  emptyTemplate = dom.emptyState.cloneNode(true);
}

function init() {
  cacheDom();
  let saved = null;
  try { saved = localStorage.getItem("ashura-theme"); } catch { /* ignore */ }
  if (!saved) saved = window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  applyTheme(saved);
  wireEvents();
  autoResize();
  if (isNarrow()) {
    document.body.classList.remove("inspector-open");
  }
  bootstrap();
  setInterval(refreshStatus, 15000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
