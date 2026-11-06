/* Command Center: sessions, transcript, streaming, OCR and the turn inspector. */

import { api } from "../api.js";
import { state } from "../store.js";
import {
  $, $$, el, icon, badge, toast, announce, copyText,
  renderMarkdown, openDialog, closeDialog, confirmAction,
} from "../components.js";
import {
  formatMs, formatTime, formatTimestamp, relativeTime, formatCount,
  verificationInfo, admissionInfo, sessionGroup,
} from "../format.js";

const MAX_MESSAGE = 16000;
const MAX_UPLOAD = 16 * 1024 * 1024;
const PAGE_SIZE = 200;
const SESSION_KEY = "ashura-session";
const SESSIONS_HIDDEN_KEY = "ashura-sessions-hidden";
const IDLE_HINT = "Enter sends · Shift+Enter adds a line · drop a file to extract";
const IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "bmp", "tif", "tiff", "webp"]);
const DOCUMENT_EXTENSIONS = new Set([
  "pdf", "docx", "pptx", "odt", "odp", "ods", "html", "htm", "txt", "md", "markdown",
  "rst", "csv", "tsv", "json", "jsonl", "log", "ini", "cfg", "conf", "toml", "yaml",
  "yml", "xml", "css", "js", "mjs", "ts", "tsx", "jsx", "py", "sql", "sh", "ps1",
  "bat", "c", "h", "cpp", "hpp", "cs", "java", "go", "rs", "rb", "php", "tex",
]);

function fileExtension(name) {
  const value = String(name || "");
  const index = value.lastIndexOf(".");
  return index >= 0 ? value.slice(index + 1).toLowerCase() : "";
}

function uploadKind(file) {
  const extension = fileExtension(file && file.name);
  if ((file && String(file.type || "").startsWith("image/")) || IMAGE_EXTENSIONS.has(extension)) {
    return "image";
  }
  if (DOCUMENT_EXTENSIONS.has(extension)) return "document";
  return null;
}

function storeSession(id) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id);
    else localStorage.removeItem(SESSION_KEY);
  } catch (error) {
    // Storage is optional.
  }
}

function readSession() {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch (error) {
    return null;
  }
}

function readSessionsHidden() {
  try {
    return localStorage.getItem(SESSIONS_HIDDEN_KEY) === "true";
  } catch (error) {
    return false;
  }
}

function storeSessionsHidden(hidden) {
  try {
    localStorage.setItem(SESSIONS_HIDDEN_KEY, String(hidden));
  } catch (error) {
    // Storage is optional.
  }
}

function isNarrow() {
  return window.matchMedia("(max-width: 1180px)").matches;
}

function isMobile() {
  return window.matchMedia("(max-width: 860px)").matches;
}

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
    kind: meta.kind || "chat",
    sources: meta.sources || [],
    truncated: Boolean(meta.truncated),
    tool_calls: meta.tool_calls || [],
    document: meta.document || null,
    web: meta.web || null,
    ts: message.ts,
    assistant_message_id: message.id || null,
    session_id: state.currentSessionId,
  };
}

function messageFromPayload(payload) {
  return {
    id: payload.assistant_message_id || null,
    role: "assistant",
    content: payload.text || "",
    ts: Date.now() / 1000,
    meta: {
      kind: payload.kind || "chat",
      model: payload.model,
      verified: payload.verified,
      verification: payload.verification,
      admission: payload.admission,
      attribution: payload.attribution,
      correction: payload.correction,
      trace: payload.trace,
      total_ms: payload.trace ? payload.trace.total_ms : null,
      sources: Array.isArray(payload.sources) ? payload.sources : [],
      truncated: Boolean(payload.truncated),
      tool_calls: Array.isArray(payload.tool_calls) ? payload.tool_calls : [],
      document: payload.document || null,
      web: payload.web || null,
    },
  };
}

function factCell(key, value) {
  const cell = el("div", "fact-cell");
  cell.appendChild(el("span", "k", key));
  const text = el("span", "v");
  if (value instanceof Node) text.appendChild(value);
  else text.textContent = value === null || value === undefined || value === "" ? "Not available" : String(value);
  cell.appendChild(text);
  return cell;
}

function routeChips(selected, skipped) {
  const box = el("div", "route-chips");
  for (const name of selected || []) box.appendChild(badge(name));
  if ((skipped || []).length) {
    for (const name of skipped) box.appendChild(badge(name, "plain"));
  }
  return box;
}

export function createCommandView(actions) {
  const view = $('.command-view');
  if (readSessionsHidden()) view.classList.add("sessions-off");
  const sessionPane = $("#session-pane");
  const sessionList = $("#session-list");
  const sessionCount = $("#session-count");
  const sessionFilter = $("#session-filter");
  const sessionToggle = $("#sessions-toggle");
  const sessionsClose = $("#sessions-close");
  const transcript = $("#transcript");
  const emptyTemplate = $("#empty-state").cloneNode(true);
  const jumpLatest = $("#jump-latest");
  const composer = $("#composer");
  const messageInput = $("#message");
  const sendButton = $("#send");
  const stopButton = $("#stop");
  const composerHint = $("#composer-hint");
  const charCount = $("#char-count");
  const ocrButton = $("#ocr-button");
  const ocrFile = $("#ocr-file");
  const inspector = $("#turn-inspector");
  const inspectorToggle = $("#inspector-toggle");
  const inspectorClose = $("#inspector-close");
  const summaryPanel = $("#inspector-summary");
  const tracePanel = $("#inspector-trace");
  const exportMd = $("#export-md");
  const exportJson = $("#export-json");
  const conversationTitle = $("#conversation-title");
  const conversationSub = $("#conversation-sub");
  const renameDialog = $("#rename-dialog");
  const renameForm = $("#rename-form");
  const renameInput = $("#rename-input");
  const renameError = $("#rename-error");

  let renameSessionId = null;
  let streamRenderScheduled = false;
  let scrollFrame = null;

  /* ---- session list -------------------------------------------------------------------- */

  function filteredSessions() {
    const needle = state.sessionFilter.trim().toLowerCase();
    if (!needle) return state.sessions;
    return state.sessions.filter((session) =>
      String(session.title || "").toLowerCase().includes(needle));
  }

  function renderSessions() {
    if (!sessionList) return;
    sessionList.replaceChildren();
    if (sessionCount) sessionCount.textContent = String(state.sessions.length);
    if (state.sessionsLoading && !state.sessions.length) {
      sessionList.appendChild(el("p", "session-empty", "Loading sessions…"));
      return;
    }
    if (state.sessionsError) {
      sessionList.appendChild(el("p", "session-empty", state.sessionsError));
      return;
    }
    const sessions = filteredSessions();
    if (!sessions.length) {
      sessionList.appendChild(el("p", "session-empty",
        state.sessionFilter.trim() ? "No sessions match that filter." : "No sessions yet. Start a new task."));
      return;
    }
    let group = null;
    for (const session of sessions) {
      const next = sessionGroup(session.updated);
      if (next !== group) {
        group = next;
        sessionList.appendChild(el("p", "session-group", group));
      }
      const row = el("div", "session-row");
      row.setAttribute("role", "listitem");
      if (session.id === state.currentSessionId) row.classList.add("is-active");

      const main = el("button", "session-main");
      main.type = "button";
      main.dataset.sessionId = session.id;
      main.title = session.title || "Untitled session";
      main.appendChild(el("span", "session-title", session.title || "New chat"));
      const count = session.message_count === undefined ? "" :
        `${formatCount(session.message_count)} message${Number(session.message_count) === 1 ? "" : "s"} · `;
      main.appendChild(el("span", "session-meta", `${count}${relativeTime(session.updated)}`));
      row.appendChild(main);

      const tools = el("span", "session-actions");
      const rename = el("button", "", "✎");
      rename.type = "button";
      rename.dataset.sessionAction = "rename";
      rename.dataset.sessionId = session.id;
      rename.title = "Rename session";
      rename.setAttribute("aria-label", `Rename ${session.title || "session"}`);
      const remove = el("button", "", "×");
      remove.type = "button";
      remove.dataset.sessionAction = "delete";
      remove.dataset.sessionId = session.id;
      remove.title = "Delete session";
      remove.setAttribute("aria-label", `Delete ${session.title || "session"}`);
      tools.append(rename, remove);
      row.appendChild(tools);
      sessionList.appendChild(row);
    }
  }

  function findSession(id) {
    return state.sessions.find((session) => session.id === id) || null;
  }

  function currentSession() {
    return findSession(state.currentSessionId);
  }

  /* ---- conversation -------------------------------------------------------------------- */

  function updateHeading() {
    const session = currentSession();
    if (conversationTitle) conversationTitle.textContent = session ? (session.title || "New chat") : "New chat";
    if (conversationSub) {
      const total = state.transcript.total;
      const loaded = state.messages.length;
      if (!state.currentSessionId) {
        conversationSub.textContent = "No session selected";
      } else if (!loaded) {
        conversationSub.textContent = "No messages yet";
      } else {
        const scope = total !== null && total !== undefined && total !== loaded
          ? `${formatCount(loaded)} of ${formatCount(total)} messages loaded`
          : `${formatCount(loaded)} message${loaded === 1 ? "" : "s"}`;
        const model = state.status && state.status.model ? state.status.model : "model not reported";
        conversationSub.textContent = `${scope} · ${model}`;
      }
    }
    if (exportMd) exportMd.disabled = !state.currentSessionId;
    if (exportJson) exportJson.disabled = !state.currentSessionId;
    actions.updateChrome();
  }

  function messageBadges(message) {
    const payload = payloadFromMessage(message);
    const row = el("div", "msg-meta");
    const info = verificationInfo(payload);
    row.appendChild(badge(info.label, info.tone, info.note));
    const admission = admissionInfo(payload.admission);
    if (admission) row.appendChild(badge(admission.label, admission.tone, admission.raw));
    if (payload.model) row.appendChild(badge(payload.model));
    if (payload.kind === "ocr") row.appendChild(badge("OCR turn", "info"));
    if (payload.kind === "document") row.appendChild(badge("Document turn", "info"));
    if (payload.tool_calls.length) {
      row.appendChild(badge(`${payload.tool_calls.length} tool call${payload.tool_calls.length === 1 ? "" : "s"}`, "info",
        "Local or web tools executed for this turn. See the evidence section for observations."));
    }
    if (payload.sources.length) {
      row.appendChild(badge(`${payload.sources.length} web source${payload.sources.length === 1 ? "" : "s"}`, "info",
        "External pages used as unverified evidence."));
    }
    if (payload.document && payload.document.ok === false) {
      row.appendChild(badge("Extraction failed", "bad", payload.document.reason || ""));
    }
    if (payload.truncated) {
      row.appendChild(badge("Truncated", "warn",
        "The model stopped at its token limit even after continuation. The answer may be incomplete."));
    }
    if (message.meta && message.meta.stopped) row.appendChild(badge("Stopped · not saved", "warn"));
    if (message.local && !message.meta?.stopped) row.appendChild(badge("Not saved", "warn"));
    if (payload.correction) row.appendChild(badge("Correction recorded", "warn"));
    return row;
  }

  function sourceList(sources) {
    const list = el("ul", "source-list");
    for (const source of sources || []) {
      const item = el("li");
      const url = String(source.url || "");
      if (/^https?:\/\//i.test(url)) {
        const link = el("a", "source-link", source.title || url);
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        item.appendChild(link);
      } else {
        item.appendChild(el("span", "source-link", source.title || url || "Source"));
      }
      if (source.provider) item.appendChild(el("span", "source-provider", String(source.provider)));
      if (source.snippet) item.appendChild(el("p", "source-snippet", String(source.snippet).slice(0, 240)));
      list.appendChild(item);
    }
    return list;
  }

  function evidenceBlock(payload) {
    const box = el("div", "msg-evidence");
    let hasContent = false;

    if (payload.document) {
      const doc = payload.document;
      const row = el("div", `document-card${doc.ok === false ? " is-bad" : ""}`);
      row.appendChild(icon(doc.kind === "image" ? "image" : "file", "icon"));
      const body = el("div", "document-body");
      body.appendChild(el("strong", "", doc.name || "Attached file"));
      const meta = [doc.kind || "document"];
      if (doc.pages) meta.push(`${doc.pages} page${Number(doc.pages) === 1 ? "" : "s"}`);
      if (doc.engine) meta.push(doc.engine);
      if (doc.truncated) meta.push("extracted text truncated");
      body.appendChild(el("span", "document-meta", meta.join(" · ")));
      body.appendChild(el("span", "document-note", doc.ok === false
        ? `Local extraction failed: ${doc.reason || "unknown reason"}`
        : "Local extraction; content is not independently verified."));
      row.appendChild(body);
      box.appendChild(row);
      hasContent = true;
    }

    if (payload.tool_calls.length) {
      const details = el("details", "tool-details");
      const summary = el("summary", "", `Tool observations · ${payload.tool_calls.length}`);
      details.appendChild(summary);
      const list = el("ul", "tool-list");
      for (const call of payload.tool_calls) {
        const item = el("li");
        item.appendChild(el("code", "", call.name || "tool"));
        item.appendChild(badge(call.ok ? "ok" : "failed", call.ok ? "ok" : "bad",
          call.error || "Observation executed locally."));
        if (call.elapsed_ms !== undefined) item.appendChild(el("span", "tool-time", formatMs(call.elapsed_ms)));
        list.appendChild(item);
      }
      details.appendChild(list);
      box.appendChild(details);
      hasContent = true;
    }

    if (payload.sources.length) {
      const details = el("details", "source-details");
      details.appendChild(el("summary", "", `Web sources · ${payload.sources.length}`));
      details.appendChild(sourceList(payload.sources));
      details.appendChild(el("p", "source-note",
        "External pages are untrusted evidence, not verified facts. The fact store keeps them as review candidates."));
      box.appendChild(details);
      hasContent = true;
    }

    if (payload.truncated) {
      const warning = el("p", "evidence-warning",
        "This answer reached the model's token limit after continuation. Treat it as incomplete.");
      box.appendChild(warning);
      hasContent = true;
    }

    return hasContent ? box : null;
  }

  function traceButton(payload) {
    const trace = payload.trace;
    if (!trace || !Array.isArray(trace.steps) || !trace.steps.length) return null;
    const row = el("div", "msg-trace");
    const button = el("button");
    button.type = "button";
    button.appendChild(icon("inspect", "icon"));
    const label = payload.kind === "ocr" ? "OCR trace" : "Trace";
    button.appendChild(el("span", "", `${label} · ${trace.steps.length} step${trace.steps.length === 1 ? "" : "s"} · ${formatMs(trace.total_ms)}`));
    row.appendChild(button);
    return row;
  }

  function renderMessage(message, index) {
    const role = message.role === "error" ? "error" : message.role === "user" ? "user" : "assistant";
    const wrap = el("div", `msg ${role}`);
    wrap.dataset.messageIndex = String(index);

    const head = el("div", "msg-head");
    head.appendChild(el("span", "msg-author", role === "user" ? "You" : role === "error" ? "Error" : "ASHURA"));
    if (message.ts) head.appendChild(el("span", "msg-time", formatTime(message.ts)));

    const tools = el("span", "msg-actions");
    if (message.content) {
      const copy = el("button", "", "Copy");
      copy.type = "button";
      copy.dataset.messageAction = "copy";
      copy.title = "Copy message";
      tools.appendChild(copy);
    }
    if (role === "assistant" || role === "error") {
      const retry = el("button", "", "Retry");
      retry.type = "button";
      retry.dataset.messageAction = "retry";
      retry.title = "Send the preceding question again";
      tools.appendChild(retry);
    }
    if (message.meta && message.meta.trace) {
      const inspect = el("button", "", "Inspect");
      inspect.type = "button";
      inspect.dataset.messageAction = "inspect";
      inspect.title = "Inspect this turn";
      tools.appendChild(inspect);
    }
    head.appendChild(tools);
    wrap.appendChild(head);

    const bubble = el("div", "bubble");
    if (role === "user") {
      bubble.textContent = message.content || "";
    } else {
      bubble.classList.add("md");
      bubble.innerHTML = renderMarkdown(message.content || "");
    }
    wrap.appendChild(bubble);

    if (role === "assistant" && message.meta) {
      wrap.appendChild(messageBadges(message));
      if (message.meta.attribution) {
        wrap.appendChild(el("div", "msg-attribution", message.meta.attribution));
      }
      const evidence = evidenceBlock(payloadFromMessage(message));
      if (evidence) wrap.appendChild(evidence);
      const trace = traceButton(payloadFromMessage(message));
      if (trace) wrap.appendChild(trace);
    }
    return wrap;
  }

  function renderConversation({ keepScroll = false } = {}) {
    if (!transcript) return;
    const previousTop = transcript.scrollTop;
    const previousHeight = transcript.scrollHeight;
    transcript.replaceChildren();
    if (!state.messages.length) {
      transcript.appendChild(emptyTemplate.cloneNode(true));
      updateHeading();
      return;
    }
    if (state.transcript.hasMore) {
      const bar = el("div", "load-earlier");
      const button = el("button", "button ghost small");
      button.type = "button";
      button.dataset.action = "load-earlier";
      button.textContent = state.transcript.loadingOlder
        ? "Loading earlier messages…"
        : `Load earlier messages (showing ${formatCount(state.messages.length)} of ${formatCount(state.transcript.total)})`;
      button.disabled = state.transcript.loadingOlder;
      bar.appendChild(button);
      transcript.appendChild(bar);
    }
    state.messages.forEach((message, index) => {
      transcript.appendChild(renderMessage(message, index));
    });
    const note = el("p", "transcript-note",
      `Showing ${formatCount(state.messages.length)} of ${formatCount(state.transcript.total)} messages. ` +
      "Export includes the full transcript.");
    transcript.appendChild(note);
    updateHeading();
    if (keepScroll) transcript.scrollTop = transcript.scrollHeight - previousHeight + previousTop;
    else scrollToBottom(false);
  }

  function scrollToBottom(force = true) {
    if (!transcript) return;
    if (force) transcript.scrollTop = transcript.scrollHeight;
    updateJumpLatest();
  }

  function nearBottom() {
    if (!transcript) return true;
    return transcript.scrollHeight - transcript.scrollTop - transcript.clientHeight < 140;
  }

  function updateJumpLatest() {
    if (jumpLatest) jumpLatest.hidden = nearBottom();
  }

  function scheduleStreamRender(stream) {
    if (streamRenderScheduled) return;
    streamRenderScheduled = true;
    requestAnimationFrame(() => {
      streamRenderScheduled = false;
      if (!stream || stream.finalized || !stream.bubble) return;
      stream.bubble.innerHTML = renderMarkdown(stream.text || "…");
      if (nearBottom()) scrollToBottom(false);
    });
  }

  function addStreamingMessage(label = "streaming") {
    const wrap = el("div", "msg assistant streaming");
    const head = el("div", "msg-head");
    head.appendChild(el("span", "msg-author", "ASHURA"));
    head.appendChild(el("span", "msg-time", label));
    wrap.appendChild(head);
    const bubble = el("div", "bubble md");
    wrap.appendChild(bubble);
    transcript.appendChild(wrap);
    scrollToBottom(false);
    return { wrap, bubble };
  }

  /* ---- inspector ----------------------------------------------------------------------- */

  function setInspectorTab(tab, { focus = false } = {}) {
    const next = tab === "trace" ? "trace" : "summary";
    state.inspectorTab = next;
    const tabs = $$(".inspector-head .tab");
    const panels = $$(".tab-panel");
    for (const button of tabs) {
      const active = button.dataset.tab === next;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-selected", active ? "true" : "false");
      button.tabIndex = active ? 0 : -1;
      if (active && focus) button.focus();
    }
    for (const panel of panels) panel.hidden = panel.dataset.panel !== next;
    renderInspector();
  }

  function renderInspector() {
    if (!summaryPanel || !tracePanel) return;
    const payload = state.inspectPayload;
    if (!payload) {
      summaryPanel.replaceChildren();
      const empty = el("div", "inspector-empty");
      empty.appendChild(icon("inspect", "icon"));
      empty.appendChild(el("p", "", "Select a turn to inspect its verification and execution evidence."));
      summaryPanel.appendChild(empty);
      tracePanel.replaceChildren();
      const traceEmpty = el("div", "inspector-empty");
      traceEmpty.appendChild(icon("terminal", "icon"));
      traceEmpty.appendChild(el("p", "", "No trace selected. Choose Trace on an answer or Inspect on a recorded turn."));
      tracePanel.appendChild(traceEmpty);
      return;
    }
    renderSummary(payload);
    renderTrace(payload);
  }

  function renderSummary(payload) {
    summaryPanel.replaceChildren();
    const info = verificationInfo(payload);
    const box = el("div", `verdict ${info.tone === "ok" ? "ok" : info.tone === "bad" ? "bad" : info.tone === "warn" ? "warn" : "neutral"}`);
    box.appendChild(el("strong", "", info.label));
    box.appendChild(el("p", "", info.note));
    summaryPanel.appendChild(box);

    const chips = el("div", "trace-meta-row");
    const admission = admissionInfo(payload.admission);
    if (admission) chips.appendChild(badge(admission.label, admission.tone));
    if (payload.model) chips.appendChild(badge(payload.model));
    if (payload.trace) chips.appendChild(badge(formatMs(payload.trace.total_ms)));
    if (payload.kind === "ocr") chips.appendChild(badge("OCR", "info"));
    if (chips.childNodes.length) summaryPanel.appendChild(chips);

    const section = el("div", "inspector-section");
    section.appendChild(el("h3", "", "Turn facts"));
    const grid = el("div", "fact-grid");
    grid.appendChild(factCell("Verification", info.label));
    grid.appendChild(factCell("Admission", admission ? admission.raw : "No admission record"));
    grid.appendChild(factCell("Model", payload.model));
    grid.appendChild(factCell("Total time", payload.trace ? formatMs(payload.trace.total_ms) : "No trace record"));
    grid.appendChild(factCell("Routing", payload.trace && payload.trace.routing
      ? (payload.trace.routing.selected || []).join(", ") || "none selected" : "No routing record"));
    grid.appendChild(factCell("Steps", payload.trace && Array.isArray(payload.trace.steps)
      ? String(payload.trace.steps.length) : "No trace record"));
    grid.appendChild(factCell("Message ID", payload.assistant_message_id || "Not persisted"));
    grid.appendChild(factCell("Recorded", payload.ts ? formatTimestamp(payload.ts) : "Not recorded"));
    section.appendChild(grid);
    summaryPanel.appendChild(section);

    if (payload.attribution) {
      const attribution = el("div", "inspector-section");
      attribution.appendChild(el("h3", "", "Attribution"));
      attribution.appendChild(el("p", "muted small", payload.attribution));
      summaryPanel.appendChild(attribution);
    }
    if (payload.correction) {
      const correction = el("div", "inspector-section");
      correction.appendChild(el("h3", "", "Correction"));
      correction.appendChild(el("pre", "raw-record", JSON.stringify(payload.correction, null, 2)));
      summaryPanel.appendChild(correction);
    }

    const evidence = el("div", "inspector-section");
    evidence.appendChild(el("h3", "", "Evidence"));
    const linkRow = el("div", "inline-actions");
    const execution = el("button", "button small");
    execution.type = "button";
    execution.dataset.inspectorAction = "execution";
    execution.appendChild(icon("execution", "icon icon-sm"));
    execution.appendChild(el("span", "", "Execution timeline"));
    linkRow.appendChild(execution);
    const knowledge = el("button", "button small");
    knowledge.type = "button";
    knowledge.dataset.inspectorAction = "knowledge";
    knowledge.appendChild(icon("knowledge", "icon icon-sm"));
    knowledge.appendChild(el("span", "", "Knowledge Studio"));
    linkRow.appendChild(knowledge);
    evidence.appendChild(linkRow);
    evidence.appendChild(el("p", "provenance-note",
      "Only completed turns are persisted. Failed and cancelled generations are shown in this browser only and are not part of the session transcript."));
    summaryPanel.appendChild(evidence);
  }

  function renderTrace(payload) {
    tracePanel.replaceChildren();
    const trace = payload.trace;
    if (!trace || !Array.isArray(trace.steps)) {
      const empty = el("div", "inspector-empty");
      empty.appendChild(icon("terminal", "icon"));
      empty.appendChild(el("p", "", "No trace record for this turn. The answer is still shown, but its execution steps were not persisted."));
      tracePanel.appendChild(empty);
      return;
    }
    const routing = trace.routing || {};
    const routeSection = el("div", "inspector-section");
    routeSection.appendChild(el("h3", "", "Route"));
    if ((routing.selected || []).length) {
      routeSection.appendChild(el("p", "muted small", "Selected"));
      routeSection.appendChild(routeChips(routing.selected, []));
    } else {
      routeSection.appendChild(el("p", "muted small", "No module route was recorded."));
    }
    if ((routing.skipped || []).length) {
      routeSection.appendChild(el("p", "muted small", "Skipped"));
      routeSection.appendChild(routeChips([], routing.skipped));
    }
    const totals = el("div", "fact-grid");
    totals.appendChild(factCell("Routing", formatMs(trace.routing_ms)));
    totals.appendChild(factCell("Total", formatMs(trace.total_ms)));
    routeSection.appendChild(totals);
    tracePanel.appendChild(routeSection);

    const stepsSection = el("div", "inspector-section");
    stepsSection.appendChild(el("h3", "", `Steps (${trace.steps.length})`));
    const list = el("div", "trace-steps");
    for (const step of trace.steps) {
      const card = el("div", `step-card${step.ok === false ? " is-failed" : ""}`);
      const head = el("div", "step-head");
      head.appendChild(el("strong", "", step.module || "step"));
      const info = step.verification ? verificationInfo({ verification: step.verification }) : null;
      if (info) head.appendChild(badge(info.label, info.tone));
      if (step.ok === false) head.appendChild(badge("Step error", "bad"));
      head.appendChild(el("span", "ms", formatMs(step.ms)));
      card.appendChild(head);
      if (step.note) card.appendChild(el("p", "step-note", step.note));
      const input = String(step.input || "");
      const output = String(step.output || "");
      if (input || output) {
        const details = el("details", "step-io");
        details.appendChild(el("summary", "", "Input and output"));
        const pre = el("pre", "", `Input\n${input || "(empty)"}\n\nOutput\n${output || "(empty)"}`);
        details.appendChild(pre);
        card.appendChild(details);
      }
      list.appendChild(card);
    }
    if (!trace.steps.length) list.appendChild(el("p", "muted small", "No module steps were recorded."));
    stepsSection.appendChild(list);
    tracePanel.appendChild(stepsSection);
  }

  function openInspector(tab = null) {
    if (tab) setInspectorTab(tab);
    if (isNarrow()) {
      document.body.classList.remove("sessions-open", "rail-open");
      document.body.classList.add("inspector-open");
    } else {
      view.classList.remove("inspector-off");
    }
    if (inspectorToggle) inspectorToggle.setAttribute("aria-expanded", "true");
    actions.syncScrim();
    if (isNarrow()) {
      const active = $(".inspector-head .tab.is-active");
      if (active) active.focus();
    }
  }

  function closeInspector() {
    if (isNarrow()) {
      document.body.classList.remove("inspector-open");
    } else {
      view.classList.add("inspector-off");
    }
    if (inspectorToggle) inspectorToggle.setAttribute("aria-expanded", "false");
    actions.syncScrim();
  }

  function toggleInspector() {
    if (isNarrow()) {
      if (document.body.classList.contains("inspector-open")) closeInspector();
      else openInspector();
    } else if (view.classList.contains("inspector-off")) {
      openInspector();
    } else {
      closeInspector();
    }
  }

  function inspectMessage(index, tab = null) {
    const message = state.messages[index];
    if (!message || !message.meta) return;
    state.inspectPayload = payloadFromMessage(message);
    state.inspectMessageIndex = index;
    renderInspector();
    openInspector(tab || "summary");
  }

  function inspectLast() {
    for (let index = state.messages.length - 1; index >= 0; index -= 1) {
      const message = state.messages[index];
      if (message.role === "assistant" && message.meta && message.meta.trace) {
        inspectMessage(index, "summary");
        return;
      }
    }
    toast("No traced answer in this session.", "bad");
  }

  /* ---- sessions ------------------------------------------------------------------------ */

  async function selectSession(sessionId, { quiet = false, focus = false } = {}) {
    if (!sessionId) return;
    if (!state.authenticated) {
      actions.onAuthRequired();
      return;
    }
    if (state.busy || state.streaming) {
      toast("Stop the current response first.", "bad");
      return;
    }
    try {
      const data = await api.session(sessionId, { limit: PAGE_SIZE });
      state.currentSessionId = data.session.id;
      state.messages = Array.isArray(data.messages) ? data.messages : [];
      state.transcript = {
        hasMore: Boolean(data.has_more),
        total: Number.isFinite(Number(data.total)) ? Number(data.total) : state.messages.length,
        loadingOlder: false,
      };
      state.inspectPayload = null;
      state.inspectMessageIndex = null;
      for (let index = state.messages.length - 1; index >= 0; index -= 1) {
        const message = state.messages[index];
        if (message.role === "assistant" && message.meta && message.meta.trace) {
          state.inspectPayload = payloadFromMessage(message);
          state.inspectMessageIndex = index;
          break;
        }
      }
      storeSession(state.currentSessionId);
      renderSessions();
      renderConversation();
      renderInspector();
      scrollToBottom(true);
      if (!quiet) closeSessionDrawer();
      if (focus && messageInput) messageInput.focus();
    } catch (error) {
      if (error.status === 404) {
        toast("That session no longer exists.", "bad");
        await actions.loadSessions({ quiet: true });
        if (state.sessions.length) await selectSession(state.sessions[0].id, { quiet: true });
        else resetSelection();
      } else if (!actions.handleError(error, "Could not open the session.")) {
        // handled
      }
    }
  }

  async function loadEarlier() {
    if (state.transcript.loadingOlder || !state.currentSessionId || !state.transcript.hasMore) return;
    const first = state.messages[0];
    if (!first) return;
    state.transcript.loadingOlder = true;
    renderConversation({ keepScroll: true });
    try {
      const data = await api.session(state.currentSessionId, {
        limit: PAGE_SIZE,
        before: first.id,
      });
      const older = Array.isArray(data.messages) ? data.messages : [];
      state.messages = [...older, ...state.messages];
      state.transcript.hasMore = Boolean(data.has_more);
      state.transcript.loadingOlder = false;
      if (Number.isFinite(Number(data.total))) state.transcript.total = Number(data.total);
      renderConversation({ keepScroll: true });
      announce(`Loaded ${older.length} earlier messages.`);
    } catch (error) {
      state.transcript.loadingOlder = false;
      renderConversation({ keepScroll: true });
      actions.handleError(error, "Could not load earlier messages.");
    }
  }

  async function newChat({ focus = true } = {}) {
    if (!state.authenticated) {
      actions.onAuthRequired();
      return;
    }
    if (state.busy || state.streaming) {
      toast("Stop the current response first.", "bad");
      return;
    }
    actions.go("command");
    if (state.currentSessionId && state.messages.length === 0) {
      if (focus && messageInput) messageInput.focus();
      closeSessionDrawer();
      return;
    }
    const empty = state.sessions.find((session) =>
      Number(session.message_count) === 0 && String(session.title || "") === "New chat");
    if (empty) {
      await selectSession(empty.id);
      if (focus && messageInput) messageInput.focus();
      return;
    }
    try {
      const data = await api.createSession("New chat");
      state.currentSessionId = data.session.id;
      state.messages = [];
      state.transcript = { hasMore: false, total: 0, loadingOlder: false };
      state.inspectPayload = null;
      state.inspectMessageIndex = null;
      storeSession(state.currentSessionId);
      await actions.loadSessions({ quiet: true });
      renderConversation();
      renderInspector();
      closeSessionDrawer();
      if (focus && messageInput) messageInput.focus();
      announce("New task created.");
    } catch (error) {
      actions.handleError(error, "Could not create a session.");
    }
  }

  function resetSelection() {
    state.currentSessionId = null;
    state.messages = [];
    state.transcript = { hasMore: false, total: 0, loadingOlder: false };
    state.inspectPayload = null;
    state.inspectMessageIndex = null;
    storeSession(null);
    renderSessions();
    renderConversation();
    renderInspector();
  }

  function openRename(session) {
    renameSessionId = session.id;
    renameInput.value = session.title || "";
    renameError.hidden = true;
    openDialog(renameDialog);
    renameInput.focus();
    renameInput.select();
  }

  async function submitRename(event) {
    event.preventDefault();
    const title = renameInput.value.trim();
    if (!title || !renameSessionId) return;
    try {
      const data = await api.renameSession(renameSessionId, title);
      const index = state.sessions.findIndex((session) => session.id === data.session.id);
      if (index >= 0) state.sessions[index] = { ...state.sessions[index], ...data.session };
      closeDialog(renameDialog);
      renderSessions();
      updateHeading();
      toast("Session renamed");
    } catch (error) {
      if (actions.handleError(error, "Could not rename the session.")) return;
      renameError.textContent = error.message || "Could not rename the session.";
      renameError.hidden = false;
    }
  }

  async function removeSession(session) {
    if (state.busy || state.streaming) {
      toast("Stop the current response first.", "bad");
      return;
    }
    const confirmed = await confirmAction({
      title: "Delete this session?",
      message: `“${session.title || "New chat"}” and its stored messages will be removed. This cannot be undone.`,
      confirmLabel: "Delete session",
    });
    if (!confirmed) return;
    try {
      await api.deleteSession(session.id);
      const wasCurrent = session.id === state.currentSessionId;
      state.sessions = state.sessions.filter((item) => item.id !== session.id);
      renderSessions();
      toast("Session deleted");
      if (wasCurrent) {
        resetSelection();
        if (state.sessions.length) await selectSession(state.sessions[0].id, { quiet: true });
        else renderConversation();
      }
      actions.updateChrome();
    } catch (error) {
      actions.handleError(error, "Could not delete the session.");
    }
  }

  /* ---- streaming ----------------------------------------------------------------------- */

  function setBusy(busy, { canStop = false } = {}) {
    state.busy = busy;
    if (sendButton) {
      sendButton.disabled = busy;
      sendButton.textContent = busy && !canStop ? "Working…" : "Send";
    }
    if (stopButton) stopButton.hidden = !(busy && canStop);
    if (composerHint) {
      composerHint.textContent = busy
        ? (canStop ? "Streaming locally…" : "Working locally…")
        : IDLE_HINT;
    }
    if (transcript) transcript.setAttribute("aria-busy", busy ? "true" : "false");
  }

  function finishStreaming(payload) {
    const stream = state.streaming;
    if (!stream || stream.finalized) return;
    stream.finalized = true;
    if (stream.user && payload.user_message_id) stream.user.id = payload.user_message_id;
    if (payload.session_id && payload.session_id !== state.currentSessionId) {
      state.currentSessionId = payload.session_id;
      storeSession(state.currentSessionId);
    }
    const message = messageFromPayload(payload);
    payload.ts = message.ts;
    payload.kind = "chat";
    state.messages.push(message);
    const index = state.messages.length - 1;
    const node = renderMessage(message, index);
    stream.wrap.replaceWith(node);
    state.inspectPayload = payload;
    state.inspectMessageIndex = index;
    renderInspector();
    updateHeading();
    if (nearBottom()) scrollToBottom(false);
    actions.loadSessions({ quiet: true });
    actions.refreshStatus({ quiet: true });
    announce("Answer received.");
  }

  function cancelStreaming() {
    const stream = state.streaming;
    if (!stream || stream.finalized) return;
    stream.finalized = true;
    const partial = (stream.text || "").trim();
    const message = {
      role: "assistant",
      content: partial || "Stopped before an answer arrived.",
      ts: Date.now() / 1000,
      local: true,
      meta: { kind: "chat", stopped: true, verification: null, trace: null },
    };
    state.messages.push(message);
    const node = renderMessage(message, state.messages.length - 1);
    stream.wrap.replaceWith(node);
    updateHeading();
    toast("Generation stopped. This partial answer was not saved.");
  }

  function failStreaming(reason) {
    const stream = state.streaming;
    if (!stream || stream.finalized) return;
    stream.finalized = true;
    const message = {
      role: "error",
      content: reason || "The local model did not return an answer.",
      ts: Date.now() / 1000,
      local: true,
      meta: { kind: "chat", verification: null },
    };
    state.messages.push(message);
    const node = renderMessage(message, state.messages.length - 1);
    stream.wrap.replaceWith(node);
    updateHeading();
    toast(message.content, "bad");
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
    } catch (error) {
      return null;
    }
  }

  function consumeEvent(event, stream) {
    if (event.name === "meta") {
      if (event.data.session_id) stream.sessionId = event.data.session_id;
      return;
    }
    if (stream.finalized) return;
    if (event.name === "token") {
      stream.text += event.data.text || "";
      scheduleStreamRender(stream);
    } else if (event.name === "done") {
      finishStreaming(event.data);
    } else if (event.name === "error") {
      failStreaming(event.data.error || "The local model reported an error.");
    } else if (event.name === "cancelled") {
      cancelStreaming();
    }
  }

  async function consumeSSE(response, stream) {
    if (!response.body) throw new Error("Streaming is not supported by this browser.");
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
          if (event) consumeEvent(event, stream);
          if (stream.finalized) {
            try { await reader.cancel(); } catch (error) { /* already gone */ }
            return;
          }
        }
      }
    } finally {
      try { reader.releaseLock(); } catch (error) { /* ignore */ }
    }
  }

  async function sendMessage(rawText) {
    if (state.busy || state.streaming) return;
    if (!state.authenticated) {
      actions.onAuthRequired();
      return;
    }
    const text = String(rawText || "").trim();
    if (!text) return;
    if (text.length > MAX_MESSAGE) {
      toast(`Message is too long (max ${MAX_MESSAGE.toLocaleString()} characters).`, "bad");
      return;
    }
    actions.go("command");
    if (!state.currentSessionId) {
      await newChat({ focus: false });
      if (!state.currentSessionId) return;
    }
    const empty = transcript.querySelector(".empty-state");
    if (empty) empty.remove();

    const user = {
      role: "user",
      content: text,
      ts: Date.now() / 1000,
      local: true,
      meta: { kind: "chat" },
    };
    state.messages.push(user);
    transcript.appendChild(renderMessage(user, state.messages.length - 1));
    const placeholder = addStreamingMessage();
    messageInput.value = "";
    autoResize();
    updateCharCount();
    setBusy(true, { canStop: true });
    scrollToBottom(false);

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

    try {
      const response = await api.stream(text, state.currentSessionId, controller.signal);
      await consumeSSE(response, stream);
      if (!stream.finalized) {
        if (stream.stopped) cancelStreaming();
        else failStreaming("The stream ended before an answer arrived.");
      }
    } catch (error) {
      if (error.name === "AbortError" || stream.stopped) {
        cancelStreaming();
      } else if (error.status === 401) {
        failStreaming("Session locked. Unlock to continue.");
        actions.onAuthRequired();
      } else if (!stream.finalized) {
        failStreaming(error.message || "Could not reach the local model.");
      }
    } finally {
      if (state.streaming === stream) state.streaming = null;
      setBusy(false);
      actions.refreshStatus({ quiet: true });
    }
  }

  function stopStreaming() {
    const stream = state.streaming;
    if (!stream) return;
    stream.stopped = true;
    try { stream.controller.abort(); } catch (error) { /* already aborted */ }
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
    if (message.content.startsWith("[image:") || message.content.startsWith("[document:")) {
      toast("Re-upload the file to retry extraction.", "bad");
      return;
    }
    sendMessage(message.content);
  }

  /* ---- OCR ----------------------------------------------------------------------------- */

  function readFileAsDataURL(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("Could not read the image."));
      reader.readAsDataURL(file);
    });
  }

  async function handleOcrFile(file) {
    if (!file) return;
    if (!state.authenticated) {
      actions.onAuthRequired();
      return;
    }
    if (state.busy || state.streaming) {
      toast("Wait for the current response first.", "bad");
      return;
    }
    const kind = uploadKind(file);
    if (!kind) {
      toast("Unsupported file type. Attach an image, PDF, DOCX/PPTX, ODT/ODP/ODS, HTML or a text/code file.", "bad");
      return;
    }
    if (file.size > MAX_UPLOAD) {
      toast("File is too large (max 16 MB).", "bad");
      return;
    }
    actions.go("command");
    if (!state.currentSessionId) {
      await newChat({ focus: false });
      if (!state.currentSessionId) return;
    }
    const empty = transcript.querySelector(".empty-state");
    if (empty) empty.remove();
    const label = kind === "image" ? "image" : "document";
    const user = {
      role: "user",
      content: `[${label}: ${file.name}]`,
      ts: Date.now() / 1000,
      local: true,
      meta: { kind, filename: file.name },
    };
    state.messages.push(user);
    transcript.appendChild(renderMessage(user, state.messages.length - 1));
    const placeholder = el("div", "msg assistant streaming");
    const head = el("div", "msg-head");
    head.appendChild(el("span", "msg-author", "ASHURA"));
    head.appendChild(el("span", "msg-time", kind === "image" ? "OCR" : "Extracting"));
    placeholder.appendChild(head);
    const bubble = el("div", "bubble md");
    bubble.textContent = kind === "image"
      ? "Reading the image locally…"
      : "Extracting text locally…";
    placeholder.appendChild(bubble);
    transcript.appendChild(placeholder);
    scrollToBottom(false);
    setBusy(true, { canStop: false });

    try {
      const dataUrl = await readFileAsDataURL(file);
      const encoded = dataUrl.includes(",") ? dataUrl.split(",", 2)[1] : dataUrl;
      const data = await api.ocr(file.name, encoded, state.currentSessionId);
      if (data.user_message_id) user.id = data.user_message_id;
      const message = messageFromPayload(data);
      state.messages.push(message);
      const index = state.messages.length - 1;
      placeholder.replaceWith(renderMessage(message, index));
      state.inspectPayload = { ...data, assistant_message_id: data.assistant_message_id, ts: message.ts };
      state.inspectMessageIndex = index;
      renderInspector();
      updateHeading();
      if (nearBottom()) scrollToBottom(false);
      actions.loadSessions({ quiet: true });
      actions.refreshStatus({ quiet: true });
      announce(kind === "image" ? "OCR completed." : "Document extraction completed.");
    } catch (error) {
      if (error.status === 401) {
        placeholder.remove();
        actions.onAuthRequired();
      } else {
        const message = {
          role: "error",
          content: error.message || (kind === "image" ? "OCR failed." : "Document extraction failed."),
          ts: Date.now() / 1000,
          local: true,
          meta: {},
        };
        state.messages.push(message);
        placeholder.replaceWith(renderMessage(message, state.messages.length - 1));
        toast(message.content, "bad");
      }
    } finally {
      setBusy(false);
      updateHeading();
    }
  }

  /* ---- composer ------------------------------------------------------------------------ */

  function autoResize() {
    if (!messageInput) return;
    messageInput.style.height = "auto";
    messageInput.style.height = `${Math.min(messageInput.scrollHeight, 210)}px`;
  }

  function updateCharCount() {
    if (!charCount || !messageInput) return;
    const length = messageInput.value.length;
    if (!length) {
      charCount.hidden = true;
      charCount.textContent = "";
      charCount.className = "char-count";
      if (sendButton) sendButton.disabled = state.busy;
      return;
    }
    charCount.hidden = false;
    charCount.textContent = `${length.toLocaleString()} / ${MAX_MESSAGE.toLocaleString()}`;
    const over = length > MAX_MESSAGE;
    const near = length > MAX_MESSAGE * 0.875;
    charCount.className = `char-count${near ? " near" : ""}${over ? " over" : ""}`;
    if (sendButton) sendButton.disabled = state.busy || over;
  }

  /* ---- drawers and tabs ---------------------------------------------------------------- */

  function openSessionDrawer() {
    document.body.classList.remove("inspector-open", "rail-open");
    document.body.classList.add("sessions-open");
    if (sessionToggle) sessionToggle.setAttribute("aria-expanded", "true");
    actions.syncScrim();
    if (sessionFilter) sessionFilter.focus();
    updateSessionsToggle();
  }

  function closeSessionDrawer() {
    document.body.classList.remove("sessions-open");
    if (sessionToggle) sessionToggle.setAttribute("aria-expanded", "false");
    actions.syncScrim();
    updateSessionsToggle();
  }

  function toggleSessionDrawer() {
    if (document.body.classList.contains("sessions-open")) closeSessionDrawer();
    else openSessionDrawer();
  }

  function updateSessionsToggle() {
    if (!sessionToggle) return;
    const visible = isMobile()
      ? document.body.classList.contains("sessions-open")
      : !view.classList.contains("sessions-off");
    sessionToggle.setAttribute("aria-expanded", String(visible));
    sessionToggle.setAttribute("aria-label", visible ? "Hide sessions" : "Show sessions");
    sessionToggle.title = visible ? "Hide sessions" : "Show sessions";
  }

  function toggleSessions() {
    if (isMobile()) {
      toggleSessionDrawer();
      updateSessionsToggle();
      return;
    }
    const hidden = !view.classList.contains("sessions-off");
    view.classList.toggle("sessions-off", hidden);
    storeSessionsHidden(hidden);
    updateSessionsToggle();
  }

  function onTranscriptClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const action = target.closest("[data-action]");
    if (action) {
      if (action.dataset.action === "load-earlier") {
        loadEarlier();
        return;
      }
      if (action.dataset.action === "copy-code") {
        const code = action.closest(".code-block") ? action.closest(".code-block").querySelector("code") : null;
        if (code) copyText(code.textContent || "");
        return;
      }
      if (action.dataset.action === "inspect-last") {
        inspectLast();
        return;
      }
    }
    const messageAction = target.closest("[data-message-action]");
    if (messageAction) {
      const wrap = messageAction.closest(".msg");
      const index = wrap ? Number(wrap.dataset.messageIndex) : -1;
      const message = state.messages[index];
      if (messageAction.dataset.messageAction === "copy" && message) {
        copyText(message.content || "");
      } else if (messageAction.dataset.messageAction === "retry") {
        retryAt(index);
      } else if (messageAction.dataset.messageAction === "inspect" && message) {
        inspectMessage(index, "summary");
      }
      return;
    }
    const trace = target.closest(".msg-trace button");
    if (trace) {
      const wrap = trace.closest(".msg");
      if (wrap) inspectMessage(Number(wrap.dataset.messageIndex), "trace");
      return;
    }
    const prompt = target.closest("[data-prompt]");
    if (prompt) {
      sendMessage(prompt.dataset.prompt || "");
    }
  }

  function onSessionListClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const action = target.closest("[data-session-action]");
    if (action) {
      event.stopPropagation();
      const session = findSession(action.dataset.sessionId);
      if (!session) return;
      if (action.dataset.sessionAction === "rename") openRename(session);
      else if (action.dataset.sessionAction === "delete") removeSession(session);
      return;
    }
    const main = target.closest("[data-session-id]");
    if (main) selectSession(main.dataset.sessionId);
  }

  function onInspectorClick(event) {
    const target = event.target instanceof Element ? event.target : null;
    if (!target) return;
    const action = target.closest("[data-inspector-action]");
    if (!action) return;
    if (action.dataset.inspectorAction === "execution") {
      state.execution.sessionId = state.currentSessionId;
      state.execution.selectedId = state.inspectPayload
        ? (state.inspectPayload.assistant_message_id || null) : null;
      actions.go("execution");
    } else if (action.dataset.inspectorAction === "knowledge") {
      actions.go("knowledge");
    }
  }

  function onTabKeydown(event) {
    const tabs = $$(".inspector-head .tab");
    const current = tabs.findIndex((tab) => tab.classList.contains("is-active"));
    if (current < 0) return;
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    setInspectorTab(tabs[next].dataset.tab, { focus: true });
  }

  function exportSession(format) {
    if (!state.currentSessionId) {
      toast("Open a session first.", "bad");
      return;
    }
    const link = document.createElement("a");
    link.href = api.exportUrl(state.currentSessionId, format);
    link.download = "";
    document.body.appendChild(link);
    link.click();
    link.remove();
  }

  /* ---- wiring -------------------------------------------------------------------------- */

  function onDragOver(event) {
    if (!event.dataTransfer || !Array.from(event.dataTransfer.types || []).includes("Files")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    view.classList.add("is-dragging");
  }

  function onDragLeave(event) {
    if (event.relatedTarget && view.contains(event.relatedTarget)) return;
    view.classList.remove("is-dragging");
  }

  function onDrop(event) {
    view.classList.remove("is-dragging");
    if (!event.dataTransfer || !event.dataTransfer.files || !event.dataTransfer.files.length) return;
    event.preventDefault();
    handleOcrFile(event.dataTransfer.files[0]);
  }

  function mount() {
    if (view) {
      view.addEventListener("dragover", onDragOver);
      view.addEventListener("dragleave", onDragLeave);
      view.addEventListener("drop", onDrop);
    }
    if (sessionList) sessionList.addEventListener("click", onSessionListClick);
    if (transcript) {
      transcript.addEventListener("click", onTranscriptClick);
      transcript.addEventListener("scroll", updateJumpLatest, { passive: true });
    }
    if (jumpLatest) jumpLatest.addEventListener("click", () => scrollToBottom(true));
    if (composer) {
      composer.addEventListener("submit", (event) => {
        event.preventDefault();
        sendMessage(messageInput ? messageInput.value : "");
      });
    }
    if (messageInput) {
      messageInput.addEventListener("input", () => {
        autoResize();
        updateCharCount();
      });
      messageInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          if (composer) composer.requestSubmit();
        }
      });
    }
    if (stopButton) stopButton.addEventListener("click", stopStreaming);
    if (ocrButton && ocrFile) {
      ocrButton.addEventListener("click", () => ocrFile.click());
      ocrFile.addEventListener("change", () => {
        const file = ocrFile.files && ocrFile.files[0];
        ocrFile.value = "";
        if (file) handleOcrFile(file);
      });
    }
    if (sessionFilter) {
      sessionFilter.addEventListener("input", () => {
        state.sessionFilter = sessionFilter.value;
        renderSessions();
      });
    }
    const newButton = $("#new-session");
    if (newButton) newButton.addEventListener("click", () => newChat());
    if (sessionToggle) sessionToggle.addEventListener("click", toggleSessions);
    if (sessionsClose) sessionsClose.addEventListener("click", closeSessionDrawer);
    if (inspectorToggle) inspectorToggle.addEventListener("click", toggleInspector);
    if (inspectorClose) inspectorClose.addEventListener("click", closeInspector);
    $$(".inspector-head .tab").forEach((tab) => {
      tab.addEventListener("click", () => setInspectorTab(tab.dataset.tab));
      tab.addEventListener("keydown", onTabKeydown);
    });
    if (summaryPanel) summaryPanel.addEventListener("click", onInspectorClick);
    if (tracePanel) tracePanel.addEventListener("click", onInspectorClick);
    if (renameForm) renameForm.addEventListener("submit", submitRename);
    if (exportMd) exportMd.addEventListener("click", () => exportSession("md"));
    if (exportJson) exportJson.addEventListener("click", () => exportSession("json"));
    autoResize();
    updateCharCount();
    renderSessions();
    renderConversation();
    renderInspector();
    updateSessionsToggle();
  }

  function activate() {
    renderSessions();
    syncResponsive();
    updateHeading();
    if (!state.inspectPayload) renderInspector();
  }

  async function restore() {
    const saved = readSession();
    if (saved && state.sessions.some((session) => session.id === saved)) {
      await selectSession(saved, { quiet: true });
      return;
    }
    if (state.sessions.length) {
      await selectSession(state.sessions[0].id, { quiet: true });
    } else {
      renderConversation();
      renderInspector();
    }
  }

  function syncResponsive() {
    if (!isNarrow()) {
      document.body.classList.remove("sessions-open", "inspector-open");
      if (inspectorToggle) {
        inspectorToggle.setAttribute("aria-expanded", view.classList.contains("inspector-off") ? "false" : "true");
      }
    } else if (!document.body.classList.contains("inspector-open")) {
      if (inspectorToggle) inspectorToggle.setAttribute("aria-expanded", "false");
    }
    if (!isMobile()) document.body.classList.remove("sessions-open");
    updateSessionsToggle();
  }

  function handleKeydown(event) {
    if (event.key === "Escape" && state.streaming) {
      event.preventDefault();
      stopStreaming();
      return true;
    }
    return false;
  }

  mount();

  return {
    activate,
    restore,
    renderSessions,
    renderConversation,
    renderInspector,
    updateHeading,
    newChat,
    selectSession,
    async selectTurn(sessionId, messageId) {
      await selectSession(sessionId, { quiet: true });
      const index = state.messages.findIndex((message) => String(message.id) === String(messageId));
      if (index >= 0) inspectMessage(index, "summary");
    },
    sendMessage,
    handleOcrFile,
    inspectLast,
    exportSession,
    syncResponsive,
    handleKeydown,
    closeInspector,
    openInspector,
    focusComposer() {
      if (messageInput) messageInput.focus();
    },
    setComposer(text) {
      if (!messageInput) return;
      messageInput.value = String(text || "");
      autoResize();
      updateCharCount();
      actions.go("command");
      messageInput.focus();
    },
    focusSessionFilter() {
      if (isMobile()) openSessionDrawer();
      if (sessionFilter) {
        sessionFilter.focus();
        sessionFilter.select();
      }
    },
    currentTitle() {
      const session = currentSession();
      return session ? (session.title || "New chat") : "";
    },
    resetForLock() {
      resetSelection();
    },
    sessionPaneOpen() {
      return document.body.classList.contains("sessions-open");
    },
  };
}
