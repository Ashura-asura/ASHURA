/* Execution Studio: worker state and the recorded traces of completed turns. */

import { api } from "../api.js";
import { state } from "../store.js";
import {
  $, el, icon, badge, toast, announce, copyText,
} from "../components.js";
import {
  formatMs, formatTimestamp, formatTime, relativeTime, formatCount, truncate,
  verificationInfo, admissionInfo,
} from "../format.js";

function statusTone(info) {
  if (info.state === "verified") return "ok";
  if (info.state === "failed") return "bad";
  return "warn";
}

function summaryCell(key, value) {
  const cell = el("div", "cell");
  cell.appendChild(el("span", "k", key));
  cell.appendChild(el("span", "v", value));
  return cell;
}

function routeRow(key, values, emptyLabel) {
  const row = el("div", "route-row");
  row.appendChild(el("span", "k", key));
  if (!values || !values.length) {
    row.appendChild(el("span", "muted small", emptyLabel));
  } else {
    for (const value of values) row.appendChild(badge(value, key === "Skipped" ? "plain" : ""));
  }
  return row;
}

export function createExecutionView(actions) {
  const workerCell = $("#live-worker");
  const queueCell = $("#live-queue");
  const lastCell = $("#live-last");
  const failedCell = $("#live-failed");
  const sessionSelect = $("#execution-session");
  const operationsList = $("#operations-list");
  const timelineHead = $("#timeline-head");
  const timeline = $("#timeline");
  const evidenceBody = $("#evidence-body");
  const refresh = $("#execution-refresh");
  const operationsToggle = $("#operations-toggle");
  const operationsClose = $("#operations-close");
  const evidenceToggle = $("#evidence-toggle");
  const evidenceClose = $("#evidence-close");

  let hasMore = false;
  let total = null;
  let loadedSessionId = null;

  function selectedMessage() {
    return state.execution.messages.find((message) => String(message.id) === String(state.execution.selectedId)) || null;
  }

  function operations() {
    return state.execution.messages.filter((message) =>
      message.role === "assistant" && message.meta && message.meta.trace);
  }

  function questionFor(message) {
    const index = state.execution.messages.indexOf(message);
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
      if (state.execution.messages[cursor].role === "user") return state.execution.messages[cursor].content;
    }
    return "";
  }

  function renderLive() {
    const status = state.status;
    const worker = status && status.worker ? status.worker : null;
    if (workerCell) {
      if (!worker) workerCell.textContent = "Not available";
      else if (worker.active) workerCell.textContent = `${worker.active} · ${worker.active_id || "running"}`;
      else if (worker.alive) workerCell.textContent = "Idle · worker alive";
      else workerCell.textContent = "Worker not running";
    }
    if (queueCell) {
      queueCell.textContent = worker
        ? `${worker.queue_depth} waiting / ${worker.max_queue} max`
        : "Not available";
    }
    if (lastCell) {
      if (worker && worker.last) {
        const last = worker.last;
        lastCell.textContent = `${last.kind || "job"} · ${last.status || "unknown"} · ${formatMs(last.run_ms)}`;
      } else {
        lastCell.textContent = "None since start";
      }
    }
    if (failedCell) {
      failedCell.textContent = worker
        ? `${formatCount(worker.failed)} failed · ${formatCount(worker.cancelled)} cancelled`
        : "Not available";
    }
  }

  function renderSessionOptions() {
    if (!sessionSelect) return;
    sessionSelect.replaceChildren();
    if (!state.sessions.length) {
      const option = el("option", "", "No stored sessions");
      option.value = "";
      sessionSelect.appendChild(option);
      sessionSelect.disabled = true;
      return;
    }
    sessionSelect.disabled = false;
    for (const session of state.sessions) {
      const option = el("option", "", session.title || "New chat");
      option.value = session.id;
      sessionSelect.appendChild(option);
    }
    if (state.execution.sessionId) sessionSelect.value = state.execution.sessionId;
  }

  function renderOperations() {
    if (!operationsList) return;
    operationsList.replaceChildren();
    if (state.execution.loading) {
      operationsList.appendChild(el("p", "operations-empty", "Loading recorded operations…"));
      return;
    }
    if (state.execution.error) {
      operationsList.appendChild(el("p", "operations-empty", state.execution.error));
      return;
    }
    if (!state.execution.sessionId) {
      operationsList.appendChild(el("p", "operations-empty",
        "No stored session is open. Completed turns from Command Center appear here."));
      return;
    }
    const items = operations();
    if (!items.length) {
      operationsList.appendChild(el("p", "operations-empty",
        "No traced answers in this session. Only completed turns with a persisted trace are listed."));
      return;
    }
    for (const message of items) {
      const info = verificationInfo(message.meta);
      const row = el("button", `operation-row${String(message.id) === String(state.execution.selectedId) ? " is-active" : ""}`);
      row.type = "button";
      row.dataset.operationId = String(message.id);
      const title = el("div", "op-title");
      title.appendChild(el("span", `dot ${statusTone(info)}`));
      title.appendChild(el("strong", "", truncate(questionFor(message) || "Traced answer", 52)));
      row.appendChild(title);
      const meta = el("div", "op-meta");
      meta.appendChild(el("span", "", info.label));
      if (message.meta.model) meta.appendChild(el("span", "", message.meta.model));
      if (message.meta.trace) meta.appendChild(el("span", "", formatMs(message.meta.trace.total_ms)));
      meta.appendChild(el("span", "", relativeTime(message.ts)));
      row.appendChild(meta);
      row.appendChild(el("div", "op-preview", truncate(message.content, 90)));
      row.addEventListener("click", () => selectOperation(message.id));
      operationsList.appendChild(row);
    }
    if (hasMore) {
      operationsList.appendChild(el("p", "operations-empty",
        `Only the latest ${formatCount(state.execution.messages.length)} messages were loaded` +
        (total ? ` of ${formatCount(total)}` : "") + ". Older operations are not listed."));
    }
  }

  function renderTimeline() {
    if (!timelineHead || !timeline) return;
    timelineHead.replaceChildren();
    timeline.replaceChildren();
    const message = selectedMessage();
    if (!message) {
      timeline.appendChild(emptyTimeline());
      return;
    }
    const info = verificationInfo(message.meta);
    const admission = admissionInfo(message.meta.admission);
    const trace = message.meta.trace || {};

    const head = el("div", "timeline-head");
    const titleRow = el("div", "timeline-title-row");
    const heading = el("h2", "", "Traced answer");
    titleRow.appendChild(heading);
    titleRow.appendChild(badge(info.label, info.tone, info.note));
    if (admission) titleRow.appendChild(badge(admission.label, admission.tone));
    if (message.meta.model) titleRow.appendChild(badge(message.meta.model));
    head.appendChild(titleRow);
    head.appendChild(el("p", "section-sub", truncate(questionFor(message) || "No question recorded before this answer.", 180)));

    const summary = el("div", "timeline-summary");
    summary.appendChild(summaryCell("Total", formatMs(trace.total_ms)));
    summary.appendChild(summaryCell("Routing", formatMs(trace.routing_ms)));
    summary.appendChild(summaryCell("Steps", trace.steps ? String(trace.steps.length) : "—"));
    summary.appendChild(summaryCell("Recorded", formatTime(message.ts) || "—"));
    head.appendChild(summary);
    head.appendChild(el("p", "timeline-note",
      "This is a completed, persisted turn. Failed and cancelled generations are not stored in the transcript, so they cannot appear as operations."));
    timelineHead.appendChild(head);

    const route = trace.routing || {};
    const routeBox = el("div", "route-line");
    routeBox.appendChild(routeRow("Selected", route.selected, "No selected modules recorded"));
    routeBox.appendChild(routeRow("Skipped", route.skipped, "No skipped modules recorded"));
    timeline.appendChild(routeBox);

    const steps = Array.isArray(trace.steps) ? trace.steps : [];
    if (!steps.length) {
      timeline.appendChild(el("p", "timeline-note", "No module steps were recorded for this turn."));
      return;
    }
    const list = el("div", "trace-steps");
    for (const step of steps) {
      const card = el("div", `step-card${step.ok === false ? " is-failed" : ""}`);
      const stepHead = el("div", "step-head");
      stepHead.appendChild(el("strong", "", step.module || "step"));
      if (step.verification) {
        const stepInfo = verificationInfo({ verification: step.verification });
        stepHead.appendChild(badge(stepInfo.label, stepInfo.tone));
      }
      if (step.ok === false) stepHead.appendChild(badge("Step error", "bad"));
      stepHead.appendChild(el("span", "ms", formatMs(step.ms)));
      card.appendChild(stepHead);
      if (step.note) card.appendChild(el("p", "step-note", step.note));
      if (step.input || step.output) {
        const details = el("details", "step-io");
        details.appendChild(el("summary", "", "Input and output"));
        details.appendChild(el("pre", "", `Input\n${step.input || "(empty)"}\n\nOutput\n${step.output || "(empty)"}`));
        card.appendChild(details);
      }
      list.appendChild(card);
    }
    timeline.appendChild(list);
  }

  function emptyTimeline() {
    const box = el("div", "timeline-empty");
    box.appendChild(icon("execution", "icon"));
    box.appendChild(el("h2", "", "No operation selected"));
    box.appendChild(el("p", "", state.execution.sessionId
      ? "Select a traced answer from Operations to inspect its module steps and evidence."
      : "Choose a stored session with at least one completed answer."));
    return box;
  }

  function rawRecord(message) {
    return JSON.stringify({
      session_id: state.execution.sessionId,
      message_id: message.id,
      ts: message.ts,
      role: message.role,
      content: message.content,
      meta: message.meta,
    }, null, 2);
  }

  function renderEvidence() {
    if (!evidenceBody) return;
    evidenceBody.replaceChildren();
    const message = selectedMessage();
    if (!message) {
      evidenceBody.appendChild(el("p", "evidence-empty", "Select an operation to see its recorded evidence."));
      return;
    }
    const info = verificationInfo(message.meta);
    const admission = admissionInfo(message.meta.admission);

    const verdict = el("div", "evidence-block");
    verdict.appendChild(el("h3", "", "Verification"));
    const verdictBox = el("div", `verdict ${info.tone === "ok" ? "ok" : info.tone === "bad" ? "bad" : "warn"}`);
    verdictBox.appendChild(el("strong", "", info.label));
    verdictBox.appendChild(el("p", "", info.note));
    verdict.appendChild(verdictBox);
    evidenceBody.appendChild(verdict);

    const record = el("div", "evidence-block");
    record.appendChild(el("h3", "", "Record"));
    const kv = el("dl", "kv");
    const rows = [
      ["Message ID", message.id || "Not persisted"],
      ["Session ID", state.execution.sessionId || "Not available"],
      ["Timestamp", formatTimestamp(message.ts)],
      ["Model", message.meta.model || "Not reported"],
      ["Admission", admission ? admission.raw : "No admission record"],
      ["Total time", message.meta.trace ? formatMs(message.meta.trace.total_ms) : "No trace record"],
    ];
    for (const [key, value] of rows) {
      const row = el("div", "kv-row");
      row.appendChild(el("dt", "", key));
      row.appendChild(el("dd", "", value));
      kv.appendChild(row);
    }
    record.appendChild(kv);
    evidenceBody.appendChild(record);

    const actionsRow = el("div", "evidence-block");
    actionsRow.appendChild(el("h3", "", "Actions"));
    const buttons = el("div", "inline-actions");
    const open = el("button", "button small");
    open.type = "button";
    open.appendChild(icon("command", "icon icon-sm"));
    open.appendChild(el("span", "", "Open this turn"));
    open.addEventListener("click", () => actions.openCommandTurn(state.execution.sessionId, message.id));
    buttons.appendChild(open);
    const copy = el("button", "button small");
    copy.type = "button";
    copy.appendChild(icon("copy", "icon icon-sm"));
    copy.appendChild(el("span", "", "Copy record"));
    copy.addEventListener("click", () => copyText(rawRecord(message)));
    buttons.appendChild(copy);
    actionsRow.appendChild(buttons);
    evidenceBody.appendChild(actionsRow);

    const raw = el("div", "evidence-block");
    raw.appendChild(el("h3", "", "Raw record"));
    const toggle = el("button", "raw-toggle");
    toggle.type = "button";
    toggle.textContent = "Show JSON";
    toggle.setAttribute("aria-expanded", "false");
    const pre = el("pre", "raw-record");
    pre.textContent = rawRecord(message);
    pre.hidden = true;
    toggle.addEventListener("click", () => {
      pre.hidden = !pre.hidden;
      toggle.textContent = pre.hidden ? "Show JSON" : "Hide JSON";
      toggle.setAttribute("aria-expanded", pre.hidden ? "false" : "true");
    });
    raw.append(toggle, pre);
    evidenceBody.appendChild(raw);
  }

  function selectOperation(id) {
    state.execution.selectedId = id;
    renderOperations();
    renderTimeline();
    renderEvidence();
    if (window.matchMedia("(max-width: 860px)").matches) {
      document.body.classList.remove("operations-open");
      actions.syncScrim();
    }
    announce("Operation selected.");
  }

  async function loadSession(sessionId) {
    if (!sessionId) {
      state.execution.sessionId = null;
      loadedSessionId = null;
      state.execution.messages = [];
      state.execution.selectedId = null;
      renderOperations();
      renderTimeline();
      renderEvidence();
      return;
    }
    state.execution.sessionId = sessionId;
    state.execution.loading = true;
    state.execution.error = null;
    renderOperations();
    try {
      const data = await api.session(sessionId, { limit: 200 });
      loadedSessionId = sessionId;
      state.execution.messages = Array.isArray(data.messages) ? data.messages : [];
      hasMore = Boolean(data.has_more);
      total = Number.isFinite(Number(data.total)) ? Number(data.total) : state.execution.messages.length;
      const valid = state.execution.messages.some((message) =>
        String(message.id) === String(state.execution.selectedId) && message.meta && message.meta.trace);
      if (!valid) {
        const traced = [...state.execution.messages].reverse().find((message) =>
          message.role === "assistant" && message.meta && message.meta.trace);
        state.execution.selectedId = traced ? traced.id : null;
      }
      state.execution.loading = false;
      renderOperations();
      renderTimeline();
      renderEvidence();
    } catch (error) {
      state.execution.loading = false;
      loadedSessionId = null;
      state.execution.messages = [];
      state.execution.selectedId = null;
      state.execution.error = error.status === 404
        ? "That session no longer exists."
        : (error.message || "Could not load the session.");
      renderOperations();
      renderTimeline();
      renderEvidence();
      if (error.status === 401) actions.onAuthRequired();
    }
  }

  function chooseInitialSession() {
    if (state.execution.sessionId && state.sessions.some((session) => session.id === state.execution.sessionId)) {
      return state.execution.sessionId;
    }
    if (state.currentSessionId && state.sessions.some((session) => session.id === state.currentSessionId)) {
      return state.currentSessionId;
    }
    return state.sessions.length ? state.sessions[0].id : null;
  }

  async function activate() {
    renderLive();
    renderSessionOptions();
    if (!state.authenticated) {
      renderOperations();
      renderTimeline();
      renderEvidence();
      return;
    }
    const sessionId = chooseInitialSession();
    if (sessionId !== loadedSessionId) {
      await loadSession(sessionId);
    } else if (!state.execution.messages.length && sessionId) {
      await loadSession(sessionId);
    } else {
      renderOperations();
      renderTimeline();
      renderEvidence();
    }
  }

  function openOperations() {
    document.body.classList.remove("evidence-open", "sessions-open", "inspector-open");
    document.body.classList.add("operations-open");
    if (operationsToggle) operationsToggle.setAttribute("aria-expanded", "true");
    actions.syncScrim();
  }

  function closeOperations() {
    document.body.classList.remove("operations-open");
    if (operationsToggle) operationsToggle.setAttribute("aria-expanded", "false");
    actions.syncScrim();
  }

  function openEvidence() {
    document.body.classList.remove("operations-open", "sessions-open", "inspector-open");
    document.body.classList.add("evidence-open");
    if (evidenceToggle) evidenceToggle.setAttribute("aria-expanded", "true");
    actions.syncScrim();
  }

  function closeEvidence() {
    document.body.classList.remove("evidence-open");
    if (evidenceToggle) evidenceToggle.setAttribute("aria-expanded", "false");
    actions.syncScrim();
  }

  function syncResponsive() {
    if (window.matchMedia("(min-width: 1181px)").matches) {
      document.body.classList.remove("evidence-open");
      if (evidenceToggle) evidenceToggle.setAttribute("aria-expanded", "false");
    }
    if (window.matchMedia("(min-width: 861px)").matches) {
      document.body.classList.remove("operations-open");
      if (operationsToggle) operationsToggle.setAttribute("aria-expanded", "false");
    }
  }

  if (sessionSelect) {
    sessionSelect.addEventListener("change", () => {
      if (sessionSelect.value) loadSession(sessionSelect.value);
    });
  }
  if (refresh) {
    refresh.addEventListener("click", async () => {
      await actions.refreshStatus({ quiet: true });
      renderLive();
      if (state.execution.sessionId) await loadSession(state.execution.sessionId);
      toast("Execution data refreshed");
    });
  }
  if (operationsToggle) {
    operationsToggle.addEventListener("click", () => {
      if (document.body.classList.contains("operations-open")) closeOperations();
      else openOperations();
    });
  }
  if (operationsClose) operationsClose.addEventListener("click", closeOperations);
  if (evidenceToggle) {
    evidenceToggle.addEventListener("click", () => {
      if (document.body.classList.contains("evidence-open")) closeEvidence();
      else openEvidence();
    });
  }
  if (evidenceClose) evidenceClose.addEventListener("click", closeEvidence);

  renderLive();

  return {
    activate,
    updateLive(status) {
      if (status !== undefined) renderLive();
    },
    renderSessions() {
      renderSessionOptions();
      if (state.execution.sessionId && !state.sessions.some((session) => session.id === state.execution.sessionId)) {
        loadSession(chooseInitialSession());
      }
    },
    syncResponsive,
    renderAll() {
      renderLive();
      renderOperations();
      renderTimeline();
      renderEvidence();
    },
    reset() {
      state.execution.sessionId = null;
      state.execution.messages = [];
      state.execution.selectedId = null;
      state.execution.loading = false;
      state.execution.error = null;
      loadedSessionId = null;
      hasMore = false;
      total = null;
      renderLive();
      renderSessionOptions();
      renderOperations();
      renderTimeline();
      renderEvidence();
    },
  };
}
