/* ASHURA workbench shell: routing, auth, theme, status polling, palette and global events. */

import { api, setCsrfToken } from "./api.js";
import { state } from "./store.js";
import {
  $, $$, el, icon, toast, announce, openDialog, closeDialog, wireSharedDialogs,
} from "./components.js";
import { formatCount, formatTime, truncate } from "./format.js";
import { createCommandView } from "./views/command.js";
import { createExecutionView } from "./views/execution.js";
import { createKnowledgeView } from "./views/knowledge.js";
import { createSystemView } from "./views/system.js";
import { createSettingsView } from "./views/settings.js";

const ROUTES = ["command", "execution", "knowledge", "system", "settings"];
const WORKSPACES = {
  command: { label: "Command Center", sub: "Session, evidence and execution" },
  execution: { label: "Execution Studio", sub: "Recorded operations, module steps and timing" },
  knowledge: { label: "Knowledge Studio", sub: "Provenance, evidence scores and conflict flags" },
  system: { label: "System Monitor", sub: "Health, readiness and measurement limits" },
  settings: { label: "Settings & Security", sub: "Appearance, session, runtime and limits" },
};

const main = $("#workspace-main");
const rail = $("#rail");
const scrim = $("#scrim");
const railToggle = $("#rail-toggle");
const railClose = $("#rail-close");
const themeToggle = $("#theme-toggle");
const themeIcon = $("#theme-icon");
const paletteDialog = $("#palette-dialog");
const paletteInput = $("#palette-input");
const paletteList = $("#palette-list");
const unlockDialog = $("#unlock-dialog");
const unlockForm = $("#unlock-form");
const unlockToken = $("#unlock-token");
const unlockError = $("#unlock-error");
const unlockSubmit = $("#unlock-submit");

let statusPromise = null;
let paletteItems = [];
let paletteActive = -1;
let initialRouteApplied = false;

/* ---- chrome ----------------------------------------------------------------------------- */

function setDot(node, tone) {
  if (!node) return;
  node.className = `dot${tone ? ` ${tone}` : ""}`;
}

function currentSession() {
  return state.sessions.find((session) => session.id === state.currentSessionId) || null;
}

function crumbContext(route) {
  if (route === "command") {
    const session = currentSession();
    return session ? (session.title || "New chat") : "";
  }
  if (route === "execution") {
    const id = state.execution.sessionId || state.currentSessionId;
    const session = state.sessions.find((item) => item.id === id);
    return session ? (session.title || "Untitled session") : "";
  }
  if (route === "knowledge") {
    const item = state.memory.items.find((entry) => entry.id === state.memory.selectedId);
    return item ? truncate(item.input, 48) : "";
  }
  if (route === "system") return "runtime readings";
  if (route === "settings") return "session and storage boundaries";
  return "";
}

function updateChrome() {
  const route = state.route;
  const workspace = WORKSPACES[route] || WORKSPACES.command;
  const crumb = $("#crumb-workspace");
  const context = $("#crumb-context");
  const sub = $("#topbar-sub");
  if (crumb) crumb.textContent = workspace.label;
  if (context) context.textContent = crumbContext(route);
  if (sub) sub.textContent = workspace.sub;

  const session = currentSession();
  document.title = `${session ? `${session.title || "New chat"} · ` : ""}${workspace.label} · ASHURA`;

  const status = state.status;
  const worker = status && status.worker ? status.worker : null;
  const statusError = state.statusError;
  const locked = !state.authenticated && state.authChecked;
  const unreachable = Boolean(statusError) && statusError !== "Session locked";

  setDot($("#runtime-dot"), unreachable ? "bad" : locked ? "warn" : status ? (worker && worker.alive ? "ok" : "warn") : "");
  setDot($("#status-health-dot"), unreachable ? "bad" : locked ? "warn" : status ? (worker && worker.alive ? "ok" : "warn") : "");

  const health = $("#status-health");
  if (health) {
    if (unreachable) health.textContent = "Server: unreachable";
    else if (locked) health.textContent = "Server: locked";
    else if (status) health.textContent = worker && !worker.alive ? "Server: reached · worker not running" : "Server: reachable";
    else if (!state.authChecked) health.textContent = "Server: connecting";
    else health.textContent = "Server: waiting";
  }

  const endpoint = $("#status-endpoint");
  if (endpoint) {
    const host = window.location.host || "loopback";
    const loopback = ["127.0.0.1", "localhost", "[::1]", "::1"].includes(window.location.hostname);
    endpoint.textContent = loopback ? "UI: loopback" : `UI: ${window.location.hostname || "unknown"}`;
    endpoint.title = `Served from ${host}`;
  }

  const model = $("#runtime-model");
  const statusModel = $("#status-model");
  if (model) {
    model.textContent = status && status.model ? status.model : "model not reported";
    model.title = "Configured model name from /api/status. Readiness is not exposed.";
  }
  if (statusModel) {
    statusModel.textContent = status && status.model ? `Model: ${status.model}` : "Model: not reported";
    statusModel.title = "Configured model name. Model readiness is not exposed by this build.";
  }

  const workerChip = $("#runtime-worker");
  const statusWorker = $("#status-worker");
  if (workerChip) {
    workerChip.textContent = worker
      ? `${worker.active || "idle"} · q${worker.queue_depth}`
      : "worker —";
    workerChip.title = worker ? `Queue ${worker.queue_depth}/${worker.max_queue}. Thread ${worker.alive ? "alive" : "not running"}.` : "";
  }
  if (statusWorker) {
    statusWorker.textContent = worker
      ? `Worker: ${worker.alive ? (worker.active ? `busy (${worker.active})` : "idle") : "not running"} · q${worker.queue_depth}`
      : "Worker: —";
  }

  const last = $("#status-last");
  if (last) last.textContent = state.statusUpdatedAt ? `Last: ${formatTime(state.statusUpdatedAt / 1000)}` : "Last: —";
  const version = $("#status-version");
  if (version) version.textContent = status && status.version ? `v${status.version}` : "v?";
  const railVersion = $("#rail-version");
  if (railVersion) railVersion.textContent = status && status.version ? `v${status.version}` : "v?";
  const storeNote = $("#session-store-note");
  if (storeNote) {
    storeNote.textContent = status && status.sessions_db ? "Session store: SQLite" : "Session store: —";
    storeNote.title = status && status.sessions_db ? status.sessions_db : "";
  }

  for (const link of $$(".rail-link")) {
    const active = link.dataset.route === route;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
}

/* ---- status / sessions ------------------------------------------------------------------ */

async function refreshStatus({ quiet = true } = {}) {
  if (statusPromise) return statusPromise;
  statusPromise = (async () => {
    try {
      const data = await api.status();
      state.status = data;
      state.statusError = null;
      state.statusUpdatedAt = Date.now();
      state.csrf = data.csrf || state.csrf;
      setCsrfToken(state.csrf);
      if (!state.authenticated) setAuthenticated(true, { prompt: false });
    } catch (error) {
      if (error.status === 401) {
        state.status = null;
        state.statusUpdatedAt = null;
        state.statusError = "Session locked";
        setCsrfToken(null);
        state.csrf = null;
        setAuthenticated(false, { prompt: false });
        openUnlock();
      } else {
        state.status = null;
        state.statusError = error.message || "Could not read server status.";
        if (!quiet) toast(state.statusError, "bad");
      }
    } finally {
      statusPromise = null;
      updateChrome();
      refreshStatusViews();
    }
  })();
  return statusPromise;
}

function refreshStatusViews() {
  try {
    executionView.updateLive(state.status);
    commandView.updateWebControl(state.status);
    if (state.route === "command") commandView.updateHeading();
    if (state.route === "knowledge") knowledgeView.updateSummary();
    if (state.route === "system") systemView.render();
    if (state.route === "settings") settingsView.render();
  } catch (error) {
    console.error("[ashura] status view update failed", error);
  }
}

async function loadSessions({ quiet = false } = {}) {
  if (state.sessionsLoading) return;
  state.sessionsLoading = true;
  state.sessionsError = null;
  commandView.renderSessions();
  try {
    const data = await api.sessions(100);
    state.sessions = Array.isArray(data.sessions) ? data.sessions : [];
    if (state.currentSessionId && !state.sessions.some((session) => session.id === state.currentSessionId)) {
      const missing = state.currentSessionId;
      commandView.resetForLock();
      if (state.sessions.length) await commandView.selectSession(state.sessions[0].id, { quiet: true });
      if (!quiet) toast("The open session no longer exists.", "bad");
      if (missing) announce("The open session no longer exists.");
    }
  } catch (error) {
    if (error.status === 401) {
      onAuthRequired();
      state.sessionsError = "Session locked.";
    } else {
      state.sessionsError = error.message || "Could not load sessions.";
      if (!quiet) toast(state.sessionsError, "bad");
    }
  } finally {
    state.sessionsLoading = false;
    commandView.renderSessions();
    executionView.renderSessions();
    updateChrome();
  }
}

/* ---- auth ------------------------------------------------------------------------------- */

function openUnlock() {
  if (!unlockDialog) return;
  if (unlockDialog.open) {
    if (unlockToken) unlockToken.focus();
    return;
  }
  if (unlockError) unlockError.hidden = true;
  if (unlockToken) unlockToken.value = "";
  if (unlockSubmit) unlockSubmit.disabled = false;
  unlockDialog.showModal();
  window.setTimeout(() => {
    if (unlockToken) unlockToken.focus();
  }, 30);
}

function setAuthenticated(value, { prompt = true } = {}) {
  state.authenticated = Boolean(value);
  state.authChecked = true;
  document.body.classList.toggle("is-locked", !state.authenticated);
  settingsView.renderSession();
  commandView.updateHeading();
  if (!state.authenticated) {
    setCsrfToken(null);
    if (prompt) openUnlock();
  }
  updateChrome();
}

function onAuthRequired() {
  setAuthenticated(false, { prompt: false });
  openUnlock();
}

async function login(event) {
  event.preventDefault();
  if (!unlockToken || !unlockSubmit) return;
  const token = unlockToken.value.trim();
  if (!token) return;
  unlockSubmit.disabled = true;
  if (unlockError) unlockError.hidden = true;
  try {
    const data = await api.login(token);
    setCsrfToken(data.csrf || null);
    state.csrf = data.csrf || null;
    closeDialog(unlockDialog);
    setAuthenticated(true, { prompt: false });
    toast("Unlocked");
    await hydrate();
  } catch (error) {
    if (unlockError) {
      unlockError.textContent = error.message || "Could not unlock.";
      unlockError.hidden = false;
    }
    unlockSubmit.disabled = false;
  }
}

async function hydrate() {
  const status = await api.status();
  state.status = status;
  state.statusError = null;
  state.statusUpdatedAt = Date.now();
  state.csrf = status.csrf || state.csrf;
  setCsrfToken(state.csrf);
  commandView.updateWebControl(status);
  setAuthenticated(true, { prompt: false });
  await loadSessions({ quiet: true });
  await commandView.restore();
  state.booted = true;
  updateChrome();
  applyRoute(state.route, { initial: true });
}

async function bootstrap() {
  state.authChecked = false;
  try {
    await hydrate();
  } catch (error) {
    state.authChecked = true;
    if (error.status === 401) {
      setAuthenticated(false, { prompt: false });
      openUnlock();
    } else {
      state.statusError = error.message || "Could not reach the local server.";
      updateChrome();
      announce(state.statusError);
    }
  }
}

async function logout() {
  if (!state.authenticated) {
    openUnlock();
    return;
  }
  const button = $("#logout-button");
  if (button) button.disabled = true;
  try {
    await api.logout();
  } catch (error) {
    if (error.status !== 401) {
      toast(error.message || "Could not log out; the server may still hold this session.", "bad");
      settingsView.renderSession();
      return;
    }
  }
  setCsrfToken(null);
  state.csrf = null;
  state.authenticated = false;
  state.authChecked = true;
  state.status = null;
  state.statusError = null;
  state.statusUpdatedAt = null;
  state.sessions = [];
  state.sessionsLoading = false;
  state.sessionsError = null;
  state.currentSessionId = null;
  state.messages = [];
  state.transcript = { hasMore: false, total: null, loadingOlder: false };
  state.inspectPayload = null;
  state.inspectMessageIndex = null;
  commandView.resetForLock();
  executionView.reset();
  knowledgeView.reset();
  systemView.render();
  settingsView.render();
  document.body.classList.add("is-locked");
  updateChrome();
  toast("Logged out of this browser. The launch token was not rotated.");
  openUnlock();
}

function handleError(error, fallback) {
  if (!error) return false;
  if (error.status === 401) {
    onAuthRequired();
    return true;
  }
  if (error.name === "AbortError") return true;
  toast(error.message || fallback || "Request failed.", "bad");
  return true;
}

/* ---- routing ---------------------------------------------------------------------------- */

function routeFromHash() {
  const match = /^#\/([a-z]+)/.exec(window.location.hash || "");
  return match && ROUTES.includes(match[1]) ? match[1] : "command";
}

function applyRoute(route, { focus = false, initial = false } = {}) {
  const next = ROUTES.includes(route) ? route : "command";
  state.route = next;
  for (const section of $$(".view")) {
    section.classList.toggle("is-active", section.dataset.view === next);
  }
  closeDrawers();
  updateChrome();
  if (next === "command") commandView.activate();
  else if (next === "execution") executionView.activate();
  else if (next === "knowledge") knowledgeView.activate();
  else if (next === "system") systemView.activate();
  else if (next === "settings") settingsView.activate();
  if (focus && !initial && main) main.focus({ preventScroll: true });
}

function go(route) {
  const next = ROUTES.includes(route) ? route : "command";
  if (state.route === next) {
    applyRoute(next);
    return;
  }
  window.location.hash = `#/${next}`;
}

/* ---- theme ------------------------------------------------------------------------------ */

function updateThemeControl() {
  const effective = document.documentElement.getAttribute("data-theme") || "dark";
  if (themeIcon) {
    const use = themeIcon.querySelector("use");
    if (use) use.setAttribute("href", effective === "dark" ? "#i-sun" : "#i-moon");
  }
  if (themeToggle) {
    const label = effective === "dark" ? "Switch to light theme" : "Switch to dark theme";
    themeToggle.setAttribute("aria-label", label);
    themeToggle.title = label;
  }
  settingsView.renderTheme();
}

function setThemePreference(preference, { silent = false } = {}) {
  const next = preference === "light" || preference === "dark" || preference === "system" ? preference : "system";
  state.themePreference = next;
  if (window.ashuraTheme) window.ashuraTheme.set(next);
  else document.documentElement.setAttribute("data-theme", next === "light" ? "light" : "dark");
  updateThemeControl();
  if (!silent) announce(`Theme preference: ${next}.`);
}

function toggleTheme() {
  const effective = document.documentElement.getAttribute("data-theme") || "dark";
  setThemePreference(effective === "dark" ? "light" : "dark");
}

/* ---- drawers ---------------------------------------------------------------------------- */

function syncScrim() {
  if (!scrim) return;
  const open = document.body.classList.contains("rail-open") ||
    document.body.classList.contains("sessions-open") ||
    document.body.classList.contains("inspector-open") ||
    document.body.classList.contains("memory-open") ||
    document.body.classList.contains("operations-open") ||
    document.body.classList.contains("evidence-open");
  scrim.hidden = !open;
}

function closeDrawers() {
  for (const name of ["rail-open", "sessions-open", "inspector-open", "memory-open", "operations-open", "evidence-open"]) {
    document.body.classList.remove(name);
  }
  for (const id of ["rail-toggle", "sessions-toggle", "inspector-toggle", "memory-toggle", "operations-toggle", "evidence-toggle"]) {
    const node = document.getElementById(id);
    if (node) node.setAttribute("aria-expanded", "false");
  }
  syncScrim();
}

function openRail() {
  document.body.classList.remove("sessions-open", "inspector-open", "memory-open", "operations-open", "evidence-open");
  document.body.classList.add("rail-open");
  if (railToggle) railToggle.setAttribute("aria-expanded", "true");
  syncScrim();
  const first = rail ? rail.querySelector(".rail-link") : null;
  if (first) first.focus();
}

function closeRail() {
  document.body.classList.remove("rail-open");
  if (railToggle) railToggle.setAttribute("aria-expanded", "false");
  syncScrim();
}

/* ---- command palette -------------------------------------------------------------------- */

function commandItems() {
  const items = [
    { group: "Workspaces", label: "Command Center", iconName: "command", meta: "Alt+1", run: () => go("command") },
    { group: "Workspaces", label: "Execution Studio", iconName: "execution", meta: "Alt+2", run: () => go("execution") },
    { group: "Workspaces", label: "Knowledge Studio", iconName: "knowledge", meta: "Alt+3", run: () => go("knowledge") },
    { group: "Workspaces", label: "System Monitor", iconName: "system", meta: "Alt+4", run: () => go("system") },
    { group: "Workspaces", label: "Settings & Security", iconName: "settings", meta: "Alt+5", run: () => go("settings") },
    { group: "Actions", label: "New task", iconName: "plus", meta: "Ctrl+Shift+O", run: () => commandView.newChat() },
    { group: "Actions", label: "Toggle theme", iconName: "sun", meta: "", run: () => toggleTheme() },
    { group: "Actions", label: "Refresh runtime status", iconName: "refresh", meta: "", run: () => refreshStatus({ quiet: false }) },
    { group: "Actions", label: "Keyboard shortcuts", iconName: "info", meta: "?", run: () => openDialog("shortcuts-dialog") },
  ];
  if (state.authenticated) {
    items.push({ group: "Actions", label: "Log out", iconName: "lock", meta: "", run: () => logout() });
  } else {
    items.push({ group: "Actions", label: "Unlock ASHURA", iconName: "lock", meta: "", run: () => openUnlock() });
  }
  const seen = new Set();
  for (const session of state.sessions) {
    if (seen.has(session.id)) continue;
    seen.add(session.id);
    items.push({
      group: "Sessions",
      label: session.title || "New chat",
      iconName: "sessions",
      meta: `${formatCount(session.message_count)} messages`,
      run: async () => {
        go("command");
        await commandView.selectSession(session.id);
      },
    });
  }
  return items;
}

function renderPalette(query = "") {
  if (!paletteList) return;
  const needle = query.trim().toLowerCase();
  const all = commandItems();
  paletteItems = needle
    ? all.filter((item) => `${item.label} ${item.group}`.toLowerCase().includes(needle))
    : all;
  paletteActive = paletteItems.length ? 0 : -1;
  paletteList.replaceChildren();
  let group = null;
  paletteItems.forEach((item, index) => {
    if (item.group !== group) {
      group = item.group;
      paletteList.appendChild(el("p", "palette-group", group));
    }
    const button = el("button", `palette-item${index === paletteActive ? " is-active" : ""}`);
    button.type = "button";
    button.id = `palette-option-${index}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", index === paletteActive ? "true" : "false");
    button.dataset.paletteIndex = String(index);
    button.appendChild(icon(item.iconName, "icon icon-sm"));
    button.appendChild(el("span", "", item.label));
    if (item.meta) button.appendChild(el("span", "meta", item.meta));
    button.addEventListener("click", () => runPalette(index));
    button.addEventListener("mousemove", () => setPaletteActive(index, false));
    paletteList.appendChild(button);
  });
  if (!paletteItems.length) {
    paletteList.appendChild(el("p", "palette-empty", "No commands or sessions match."));
  }
  setPaletteActive(paletteActive, false);
}

function setPaletteActive(index, scroll = true) {
  if (!paletteItems.length) return;
  paletteActive = Math.max(0, Math.min(index, paletteItems.length - 1));
  for (const node of paletteList.querySelectorAll("[data-palette-index]")) {
    const active = Number(node.dataset.paletteIndex) === paletteActive;
    node.classList.toggle("is-active", active);
    node.setAttribute("aria-selected", active ? "true" : "false");
    if (active && scroll) node.scrollIntoView({ block: "nearest" });
  }
  if (paletteInput) {
    paletteInput.setAttribute("aria-activedescendant", `palette-option-${paletteActive}`);
    const node = document.getElementById(`palette-option-${paletteActive}`);
    if (node) node.scrollIntoView({ block: "nearest" });
  }
}

function runPalette(index) {
  const item = paletteItems[index];
  if (!item) return;
  closeDialog(paletteDialog);
  Promise.resolve(item.run()).catch((error) => handleError(error, "Command failed."));
}

function openPalette() {
  if (!paletteDialog) return;
  if (paletteDialog.open) {
    closeDialog(paletteDialog);
    return;
  }
  if (paletteInput) paletteInput.value = "";
  renderPalette("");
  paletteDialog.showModal();
  if (paletteInput) {
    paletteInput.focus();
    paletteInput.select();
  }
}

/* ---- local search focus ----------------------------------------------------------------- */

function focusActiveSearch() {
  if (state.route === "command") {
    commandView.focusSessionFilter();
    return;
  }
  if (state.route === "knowledge") {
    const input = $("#memory-query");
    if (input) input.focus();
    return;
  }
  if (state.route === "execution") {
    const select = $("#execution-session");
    if (select && !select.disabled) select.focus();
    return;
  }
  if (main) main.focus();
}

function isTyping(target) {
  return Boolean(target && (
    target.tagName === "INPUT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "SELECT" ||
    target.isContentEditable
  ));
}

/* ---- global events ---------------------------------------------------------------------- */

function onGlobalKeydown(event) {
  if (event.key === "Escape" && commandView.handleKeydown(event)) return;
  const open = document.querySelector("dialog[open]");
  if (open && open.id !== "palette-dialog") return;

  const modifier = event.ctrlKey || event.metaKey;
  const typing = isTyping(event.target);
  if (modifier && !event.shiftKey && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openPalette();
    return;
  }
  if (modifier && event.shiftKey && event.key.toLowerCase() === "o") {
    event.preventDefault();
    commandView.newChat();
    return;
  }
  if (event.altKey && !modifier && !event.shiftKey && /^[1-5]$/.test(event.key)) {
    event.preventDefault();
    go(ROUTES[Number(event.key) - 1]);
    return;
  }
  if (!typing && !modifier && !event.altKey && event.key === "/") {
    event.preventDefault();
    focusActiveSearch();
    return;
  }
  if (!typing && !modifier && !event.altKey && event.shiftKey && event.key === "?") {
    event.preventDefault();
    openDialog("shortcuts-dialog");
    return;
  }
  if (event.key === "Escape") {
    closeDrawers();
  }
}

function wireChrome() {
  if (railToggle) railToggle.addEventListener("click", () => {
    if (document.body.classList.contains("rail-open")) closeRail();
    else openRail();
  });
  if (railClose) railClose.addEventListener("click", closeRail);
  if (scrim) scrim.addEventListener("click", closeDrawers);
  if (themeToggle) themeToggle.addEventListener("click", toggleTheme);
  const trigger = $("#palette-trigger");
  if (trigger) trigger.addEventListener("click", openPalette);
  if (paletteInput) {
    paletteInput.addEventListener("input", () => renderPalette(paletteInput.value));
    paletteInput.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") {
        event.preventDefault();
        setPaletteActive(paletteActive + 1);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setPaletteActive(paletteActive - 1);
      } else if (event.key === "Home") {
        event.preventDefault();
        setPaletteActive(0);
      } else if (event.key === "End") {
        event.preventDefault();
        setPaletteActive(paletteItems.length - 1);
      } else if (event.key === "Enter") {
        event.preventDefault();
        runPalette(paletteActive);
      }
    });
  }
  if (paletteDialog) {
    paletteDialog.addEventListener("click", (event) => {
      if (event.target === paletteDialog) closeDialog(paletteDialog);
    });
    paletteDialog.addEventListener("close", () => {
      paletteItems = [];
      paletteActive = -1;
    });
  }
  document.addEventListener("keydown", onGlobalKeydown);
  window.addEventListener("hashchange", () => applyRoute(routeFromHash(), { focus: true }));
  window.addEventListener("resize", () => {
    commandView.syncResponsive();
    executionView.syncResponsive();
    knowledgeView.syncResponsive();
    if (window.matchMedia("(min-width: 861px)").matches) closeRail();
    syncScrim();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && state.authenticated) refreshStatus({ quiet: true });
  });
  window.addEventListener("online", () => refreshStatus({ quiet: true }));
  window.addEventListener("offline", () => {
    state.statusError = "Browser is offline.";
    updateChrome();
  });
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: light)") : null;
  if (media) {
    const onChange = () => {
      if (state.themePreference === "system") updateThemeControl();
    };
    if (media.addEventListener) media.addEventListener("change", onChange);
    else if (media.addListener) media.addListener(onChange);
  }
}

function wireAuth() {
  if (unlockForm) unlockForm.addEventListener("submit", login);
  if (unlockDialog) {
    // Locking is a gate: Escape must not dismiss the only way back in.
    unlockDialog.addEventListener("cancel", (event) => event.preventDefault());
  }
}

function wireDrag() {
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
    if (file) {
      go("command");
      commandView.handleOcrFile(file);
    } else {
      toast("Drop an image for OCR.", "bad");
    }
  });
  document.addEventListener("paste", (event) => {
    if (document.querySelector("dialog[open]")) return;
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) return;
    for (const item of items) {
      if (item.type && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) {
          event.preventDefault();
          go("command");
          commandView.handleOcrFile(file);
          return;
        }
      }
    }
  });
}

/* ---- view creation ---------------------------------------------------------------------- */

const actions = {
  go,
  syncScrim,
  refreshStatus,
  loadSessions,
  updateChrome,
  handleError,
  onAuthRequired,
  setThemePreference,
  logout,
  usePrompt(text) {
    commandView.setComposer(text);
  },
  async openCommandTurn(sessionId, messageId) {
    go("command");
    await commandView.selectTurn(sessionId, messageId);
  },
};

const commandView = createCommandView(actions);
const executionView = createExecutionView(actions);
const knowledgeView = createKnowledgeView(actions);
const systemView = createSystemView(actions);
const settingsView = createSettingsView(actions);

/* ---- init ------------------------------------------------------------------------------- */

function init() {
  wireSharedDialogs();
  wireChrome();
  wireAuth();
  wireDrag();

  const preference = document.documentElement.getAttribute("data-theme-preference") ||
    (window.ashuraTheme ? window.ashuraTheme.preference() : "system");
  state.themePreference = ["dark", "light", "system"].includes(preference) ? preference : "system";
  updateThemeControl();

  const route = routeFromHash();
  if (!window.location.hash) {
    try { history.replaceState(null, "", "#/command"); } catch (error) { /* ignore */ }
  }
  applyRoute(route, { initial: true });
  initialRouteApplied = true;
  updateChrome();
  syncScrim();
  bootstrap();
  window.setInterval(() => {
    if (state.authenticated) refreshStatus({ quiet: true });
  }, 15000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
