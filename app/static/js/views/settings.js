/* Settings & Security: appearance, session boundary, runtime and honest limits. */

import { state } from "../store.js";
import { api } from "../api.js";
import { $, $$, el, icon, openDialog, toast } from "../components.js";
import { formatCount, formatDuration, formatTimestamp, orUnavailable } from "../format.js";

function dataCell(key, value, note = "") {
  const cell = el("div", "data-cell");
  cell.appendChild(el("span", "k", key));
  const text = el("span", "v");
  if (value instanceof Node) text.appendChild(value);
  else text.textContent = value === null || value === undefined || value === "" ? "Not available" : String(value);
  if (note) text.title = note;
  cell.appendChild(text);
  return cell;
}

function truthItem(iconName, title, text) {
  const item = el("li");
  item.appendChild(icon(iconName, "icon"));
  const body = el("span");
  body.appendChild(el("strong", "", title));
  body.appendChild(document.createTextNode(` ${text}`));
  item.appendChild(body);
  return item;
}

export function createSettingsView(actions) {
  const radios = $$('input[name="theme"]');
  const sessionStatus = $("#settings-session-status");
  const logoutButton = $("#logout-button");
  const modelBody = $("#settings-model-body");
  const webBody = $("#settings-web-body");
  const runtimeBody = $("#settings-runtime-body");
  const privacyBody = $("#settings-privacy-body");
  const shortcuts = $("#shortcuts-button");
  let modelChoice = null;
  let modelSwitching = false;
  let webData = null;
  let webLoading = false;
  let webError = null;
  let webFilter = "";

  function renderTheme() {
    for (const radio of radios) {
      radio.checked = radio.value === state.themePreference;
    }
  }

  function renderSession() {
    if (!sessionStatus) return;
    if (!state.authChecked) sessionStatus.textContent = "Checking session…";
    else if (state.authenticated) sessionStatus.textContent = "Unlocked via launch token";
    else sessionStatus.textContent = "Locked — enter the launch token";
    if (logoutButton) logoutButton.disabled = !state.authenticated;
  }

  function formatModelSize(bytes) {
    const value = Number(bytes);
    if (!Number.isFinite(value) || value <= 0) return "size not reported";
    return `${(value / (1024 ** 3)).toFixed(1)} GB`;
  }

  function renderModelDetail(container, item) {
    container.replaceChildren();
    if (!item) return;
    container.appendChild(el("p", "model-role", item.role || "No documented role in this build."));
    if (item.note) container.appendChild(el("p", "model-note", item.note));
    const meta = [formatModelSize(item.size)];
    if (item.digest) meta.push(`digest ${String(item.digest).slice(0, 12)}`);
    if (item.documented && item.matches_catalog === false) {
      meta.push("installed digest does not match config/models.toml");
    }
    container.appendChild(el("p", "model-meta", meta.join(" · ")));
    container.appendChild(el("p", "model-meta", item.active
      ? "Active for subsequent turns."
      : "Selecting this changes new turns only."));
  }

  function retryButton(label, onClick) {
    const button = el("button", "button ghost small", label);
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function renderModel() {
    if (!modelBody) return;
    modelBody.replaceChildren();
    if (!state.authenticated) {
      modelBody.appendChild(el("p", "settings-note", "Unlock to read the models installed in Ollama."));
      return;
    }
    const data = state.models;
    if (data.error) {
      const callout = el("div", "callout bad");
      callout.appendChild(el("strong", "", "Model list unavailable"));
      callout.appendChild(el("span", "", data.error));
      modelBody.appendChild(callout);
      modelBody.appendChild(retryButton("Try again", () => loadModels({ force: true })));
      return;
    }
    if (data.loading && !data.loaded) {
      modelBody.appendChild(el("p", "settings-note", "Reading installed models from the configured Ollama endpoint…"));
      return;
    }
    if (!data.available) {
      const callout = el("div", "callout warn");
      callout.appendChild(el("strong", "", "Model switching is unavailable"));
      callout.appendChild(el("span", "", data.reason || "The local model list could not be read."));
      modelBody.appendChild(callout);
      modelBody.appendChild(el("p", "settings-note",
        `Current model reported by /api/status: ${state.status && state.status.model ? state.status.model : "not reported"}.`));
      modelBody.appendChild(retryButton("Check again", () => loadModels({ force: true })));
      return;
    }
    const items = data.items || [];
    if (!items.length) {
      const callout = el("div", "callout warn");
      callout.appendChild(el("strong", "", "No installed models were returned"));
      callout.appendChild(el("span", "", "Ollama answered, but its model list is empty. Install a model with Ollama first; this screen never downloads one."));
      modelBody.appendChild(callout);
      return;
    }
    const selectedName = items.some((item) => item.name === modelChoice) ? modelChoice : data.active;
    const selected = items.find((item) => item.name === selectedName) || items[0];
    const controls = el("div", "model-controls");
    const select = el("select", "model-select");
    select.id = "model-select";
    select.setAttribute("aria-label", "Installed Ollama model");
    for (const item of items) {
      const option = el("option", "", `${item.name} — ${item.role || "No documented role"}`);
      option.value = item.name;
      option.selected = item.name === selectedName;
      select.appendChild(option);
    }
    const apply = el("button", "button small", modelSwitching ? "Switching…" : "Use this model");
    apply.type = "button";
    apply.disabled = modelSwitching || selectedName === data.active;
    const detail = el("div", "model-detail");
    renderModelDetail(detail, selected);
    select.addEventListener("change", () => {
      modelChoice = select.value;
      const item = items.find((entry) => entry.name === select.value) || items[0];
      renderModelDetail(detail, item);
      apply.disabled = modelSwitching || select.value === data.active;
    });
    apply.addEventListener("click", () => applyModel(select.value));
    controls.append(select, apply);
    modelBody.appendChild(controls);
    modelBody.appendChild(detail);
    if (data.warning) {
      const warning = el("div", "callout warn");
      warning.appendChild(el("strong", "", "The switch completed with a warning"));
      warning.appendChild(el("span", "", data.warning));
      modelBody.appendChild(warning);
    }
    const note = el("p", "settings-note",
      "Only models already installed in Ollama are listed. Switching is process-local, does not download or train anything, and does not rewrite the launch configuration.");
    if (data.host) note.textContent += ` Endpoint: ${data.host}.`;
    if (data.notes && data.notes.length) note.textContent += ` ${data.notes.join(" ")}`;
    modelBody.appendChild(note);
  }

  async function loadModels({ force = false, quiet = false } = {}) {
    if (state.models.loading) return;
    if (!state.authenticated) {
      renderModel();
      return;
    }
    if (state.models.loaded && !force && !state.models.error) {
      renderModel();
      return;
    }
    state.models.loading = true;
    state.models.error = null;
    renderModel();
    try {
      const data = await api.models();
      state.models = {
        ...state.models,
        ...data,
        items: Array.isArray(data.models) ? data.models : [],
        notes: Array.isArray(data.notes) ? data.notes : [],
        loading: false,
        loaded: true,
        error: null,
        warning: null,
      };
      if (!state.models.items.some((item) => item.name === modelChoice)) {
        modelChoice = state.models.active;
      }
    } catch (error) {
      state.models.loading = false;
      state.models.loaded = true;
      state.models.error = error.message || "Could not read the installed models.";
      if (!quiet || error.status === 401) actions.handleError(error, "Could not read the installed models.");
    } finally {
      renderModel();
    }
  }

  async function applyModel(name) {
    if (!name || modelSwitching) return;
    modelSwitching = true;
    state.models.error = null;
    state.models.warning = null;
    renderModel();
    let result = null;
    try {
      result = await api.selectModel(name);
      modelChoice = result.active || name;
      await loadModels({ force: true, quiet: true });
      if (result.warning) state.models.warning = result.warning;
      toast(result.warning || result.message ||
        `Model switched to ${modelChoice}. New turns use it.`, result.warning ? "bad" : "ok");
      await actions.refreshStatus({ quiet: true });
    } catch (error) {
      state.models.error = error.message || "Could not switch the model.";
      actions.handleError(error, "Could not switch the model.");
    } finally {
      modelSwitching = false;
      renderModel();
    }
  }

  function webStatusLabel(status) {
    if (status === "verified") return { label: "Review accepted", tone: "ok" };
    if (status === "rejected") return { label: "Rejected", tone: "bad" };
    return { label: "Candidate", tone: "warn" };
  }

  function renderWebFact(fact) {
    const card = el("article", "web-fact");
    const head = el("div", "web-fact-head");
    head.appendChild(el("strong", "", fact.question || "Untitled question"));
    const status = webStatusLabel(fact.status);
    head.appendChild(badge(status.label, status.tone,
      "Review status only; it is not independent fact verification."));
    card.appendChild(head);
    card.appendChild(el("p", "web-fact-answer", fact.answer || ""));
    const meta = [];
    if (fact.provider) meta.push(`provider ${fact.provider}`);
    if (fact.model) meta.push(fact.model);
    if (fact.ts) meta.push(formatTimestamp(fact.ts));
    if (meta.length) card.appendChild(el("p", "web-fact-meta", meta.join(" · ")));
    let sources = [];
    try {
      sources = Array.isArray(fact.sources) ? fact.sources : JSON.parse(fact.sources || "[]");
    } catch (error) {
      sources = [];
    }
    if (sources.length) {
      const details = el("details", "web-fact-sources");
      details.appendChild(el("summary", "", `${sources.length} source${sources.length === 1 ? "" : "s"}`));
      const list = el("ul", "source-list");
      for (const source of sources) {
        const item = el("li");
        const link = el("a", "source-link", source.title || source.url || "Source");
        const url = String(source.url || "");
        if (/^https?:\/\//i.test(url)) {
          link.href = url;
          link.target = "_blank";
          link.rel = "noopener noreferrer";
        }
        item.appendChild(link);
        list.appendChild(item);
      }
      details.appendChild(list);
      card.appendChild(details);
    }
    const actionsRow = el("div", "web-fact-actions");
    if (fact.status !== "verified") {
      const accept = el("button", "button ghost small", "Accept review");
      accept.type = "button";
      accept.disabled = webReviewing !== null;
      accept.addEventListener("click", () => reviewFact(fact.id, "verified"));
      actionsRow.appendChild(accept);
    }
    if (fact.status !== "candidate") {
      const reset = el("button", "button ghost small", "Reset to candidate");
      reset.type = "button";
      reset.disabled = webReviewing !== null;
      reset.addEventListener("click", () => reviewFact(fact.id, "candidate"));
      actionsRow.appendChild(reset);
    }
    if (fact.status !== "rejected") {
      const reject = el("button", "button ghost small", "Reject");
      reject.type = "button";
      reject.disabled = webReviewing !== null;
      reject.addEventListener("click", () => reviewFact(fact.id, "rejected"));
      actionsRow.appendChild(reject);
    }
    card.appendChild(actionsRow);
    return card;
  }

  function renderWeb() {
    if (!webBody) return;
    webBody.replaceChildren();
    if (!state.authenticated) {
      webBody.appendChild(el("p", "settings-note", "Unlock to read web research settings and candidate facts."));
      return;
    }
    if (webError) {
      const callout = el("div", "callout bad");
      callout.appendChild(el("strong", "", "Web research status unavailable"));
      callout.appendChild(el("span", "", webError));
      webBody.appendChild(callout);
      webBody.appendChild(retryButton("Try again", () => loadWeb({ force: true })));
      return;
    }
    if (webLoading && !webData) {
      webBody.appendChild(el("p", "settings-note", "Reading web research state…"));
      return;
    }
    const data = webData;
    if (!data) {
      webBody.appendChild(el("p", "settings-note", "No web research payload has been read yet."));
      return;
    }
    if (!data.enabled) {
      const callout = el("div", "callout warn");
      callout.appendChild(el("strong", "", "Web research is disabled"));
      callout.appendChild(el("span", "", data.reason ||
        "Enable [web] in the launch configuration to search the public web. The privacy profile keeps it off."));
      webBody.appendChild(callout);
      webBody.appendChild(el("p", "settings-note",
        "No search request is made while disabled. The browser CSP remains connect-src 'self'."));
      return;
    }
    const stats = data.stats || {};
    const grid = el("div", "data-grid");
    grid.appendChild(dataCell("Provider", data.provider || "not reported"));
    grid.appendChild(dataCell("Candidate facts", formatCount(stats.candidates)));
    grid.appendChild(dataCell("Review accepted", formatCount(stats.verified),
      "Review status recorded by the operator. This is not independent verification of the claim."));
    grid.appendChild(dataCell("Unresolved gaps", formatCount(stats.open_gaps)));
    grid.appendChild(dataCell("Total gaps", formatCount(stats.gaps)));
    grid.appendChild(dataCell("Dataset directory", data.dataset_dir || "not reported"));
    webBody.appendChild(grid);

    const controls = el("div", "model-controls");
    const filters = el("select", "model-select");
    filters.setAttribute("aria-label", "Filter candidate facts by review status");
    for (const [value, label] of [["", "All review states"], ["candidate", "Candidates"],
      ["verified", "Review accepted"], ["rejected", "Rejected"]]) {
      const option = el("option", "", label);
      option.value = value;
      option.selected = value === webFilter;
      filters.appendChild(option);
    }
    filters.addEventListener("change", () => {
      webFilter = filters.value;
      loadWeb({ force: true });
    });
    controls.appendChild(filters);
    controls.appendChild(retryButton("Refresh", () => loadWeb({ force: true })));
    const exportLink = el("a", "button ghost small", "Export JSONL");
    exportLink.href = api.webExportUrl(false);
    exportLink.download = "";
    exportLink.title = "Write data/web_training/web_training.jsonl and download it; every row is marked training_ready=false.";
    controls.appendChild(exportLink);
    webBody.appendChild(controls);
    if (data.warning) {
      const warning = el("div", "callout warn");
      warning.appendChild(el("strong", "", "Review is required"));
      warning.appendChild(el("span", "", data.warning));
      webBody.appendChild(warning);
    }

    const facts = Array.isArray(data.facts) ? data.facts : [];
    const heading = el("div", "settings-subhead");
    heading.appendChild(el("h3", "", `Candidate facts · ${facts.length}`));
    heading.appendChild(el("p", "settings-note",
      "Web answers are stored as observations. Accepting review does not make them verified facts, and the export stays training_ready=false."));
    webBody.appendChild(heading);
    if (!facts.length) {
      webBody.appendChild(el("p", "settings-note", "No candidate facts have been stored yet."));
    } else {
      for (const fact of facts) webBody.appendChild(renderWebFact(fact));
    }

    const gaps = Array.isArray(data.gaps) ? data.gaps : [];
    webBody.appendChild(el("h3", "settings-subhead", `Unresolved gaps · ${gaps.length}`));
    if (!gaps.length) {
      webBody.appendChild(el("p", "settings-note", "No unresolved gaps are stored."));
    } else {
      for (const gap of gaps) {
        const card = el("article", "web-fact web-gap");
        const head = el("div", "web-fact-head");
        head.appendChild(el("strong", "", gap.question || "Untitled question"));
        head.appendChild(badge("Open", "warn"));
        card.appendChild(head);
        if (gap.model_answer) card.appendChild(el("p", "web-fact-answer", gap.model_answer));
        const meta = [];
        if (gap.reason) meta.push(gap.reason);
        if (gap.ts) meta.push(formatTimestamp(gap.ts));
        if (meta.length) card.appendChild(el("p", "web-fact-meta", meta.join(" · ")));
        webBody.appendChild(card);
      }
    }
    if (Array.isArray(data.notes)) {
      webBody.appendChild(el("p", "settings-note", data.notes.join(" ")));
    }
  }

  let webReviewing = null;

  async function reviewFact(id, status) {
    if (webReviewing !== null) return;
    webReviewing = id;
    renderWeb();
    try {
      const result = await api.reviewWebFact(id, status);
      toast(result.note || "Review status recorded.");
      await loadWeb({ force: true, quiet: true });
    } catch (error) {
      actions.handleError(error, "Could not record the review status.");
    } finally {
      webReviewing = null;
      renderWeb();
    }
  }

  async function loadWeb({ force = false, quiet = false } = {}) {
    if (webLoading) return;
    if (!state.authenticated) {
      renderWeb();
      return;
    }
    if (webData && !force) {
      renderWeb();
      return;
    }
    webLoading = true;
    webError = null;
    renderWeb();
    try {
      webData = await api.webFacts(50, webFilter);
    } catch (error) {
      webError = error.message || "Could not read web research state.";
      if (!quiet || error.status === 401) actions.handleError(error, "Could not read web research state.");
    } finally {
      webLoading = false;
      renderWeb();
    }
  }

  function renderRuntime() {
    if (!runtimeBody) return;
    runtimeBody.replaceChildren();
    const status = state.status;
    const worker = status && status.worker ? status.worker : null;
    const grid = el("div", "data-grid");
    grid.appendChild(dataCell("Version", status ? orUnavailable(status.version) : null));
    grid.appendChild(dataCell("Configured model", status ? orUnavailable(status.model) : null,
      "Model readiness and backend host are not exposed."));
    grid.appendChild(dataCell("Server uptime", status ? formatDuration(status.uptime_s) : null));
    grid.appendChild(dataCell("Sessions stored", status ? formatCount(status.sessions) : null));
    grid.appendChild(dataCell("Worker", worker
      ? `${worker.alive ? "alive" : "not running"} · queue ${worker.queue_depth}/${worker.max_queue}`
      : null));
    grid.appendChild(dataCell("Worker completed", worker ? formatCount(worker.completed) : null,
      "Since process start."));
    grid.appendChild(dataCell("Configuration file", status ? orUnavailable(status.config) : null));
    grid.appendChild(dataCell("Memory database", status ? orUnavailable(status.database) : null));
    grid.appendChild(dataCell("Session database", status ? orUnavailable(status.sessions_db) : null));
    const web = status && status.web ? status.web : null;
    grid.appendChild(dataCell("Web research", web
      ? (web.enabled ? `enabled · ${web.provider || "provider not reported"}` : "disabled")
      : "not reported",
      web && web.stats ? `${formatCount(web.stats.candidates)} candidate facts · ${formatCount(web.stats.open_gaps)} open gaps` : ""));
    const capabilities = status && status.capabilities ? status.capabilities : null;
    grid.appendChild(dataCell("Local tools", capabilities
      ? (capabilities.tools ? "enabled for this model" : "unavailable for this model")
      : null,
      "Agent tools require a backend with native tool calls. The privacy profile keeps web off."));
    runtimeBody.appendChild(grid);
    const note = el("p", "settings-note");
    note.textContent = state.statusUpdatedAt
      ? `Read from /api/status at ${formatTimestamp(state.statusUpdatedAt / 1000)}. Model changes are process-local; other runtime changes require editing the configuration and restarting the server.`
      : "No status payload has been read yet. Values will appear after the server answers /api/status.";
    runtimeBody.appendChild(note);
  }

  function renderPrivacy() {
    if (!privacyBody) return;
    privacyBody.replaceChildren();
    const list = el("ul", "truth-list");
    list.appendChild(truthItem("shield", "Browser requests stay on this origin.",
      "The client loads its own files and calls this server only. It makes no third-party font, script, analytics or image requests."));
    list.appendChild(truthItem("info", "The model endpoint is not independently verified.",
      "The model name and installed list come from the configured Ollama endpoint. This screen can show that endpoint but cannot prove what backs it; treat locality as a deployment property to verify outside this screen."));
    list.appendChild(truthItem("alert", "Databases are plaintext SQLite.",
      "ASHURA does not encrypt the memory or session databases at rest. Filesystem permissions and operating-system disk encryption are outside this application."));
    list.appendChild(truthItem("lock", "HTTP on loopback, with no TLS.",
      "The server refuses non-loopback bind addresses. It speaks plain HTTP, so anything able to reach the loopback port and hold the token can use the interface."));
    list.appendChild(truthItem("shield", "One launch token, cookie and CSRF.",
      "The access cookie is HttpOnly and SameSite=Strict with a 7-day Max-Age. Mutating requests also require a per-process CSRF token. There are no accounts or roles."));
    list.appendChild(truthItem("alert", "Logout is local to this browser.",
      "Logging out clears this browser's cookie. The launch token is not rotated and other browsers holding it are not revoked."));
    list.appendChild(truthItem("database", "Only completed turns are persisted.",
      "The session store keeps completed user and assistant turns with trace metadata. Failed and cancelled generations are shown in the current browser only. Export includes the full transcript; the conversation view pages the latest 200 messages."));
    list.appendChild(truthItem("image", "Uploaded files are temporary.",
      "Images, PDFs, Office/OpenDocument files and text files are written to a temporary file for local extraction and deleted afterward. The session stores the filename and extracted text, not the original bytes."));
    list.appendChild(truthItem("info", "Web research leaves this machine when enabled.",
      "The search query is sent to the configured provider (DuckDuckGo, Wikipedia or your SearXNG instance), and fetched pages are requested by this server. The browser makes no third-party request. Web answers are stored as unverified candidates and the privacy profile disables web research."));
    list.appendChild(truthItem("lock", "The launch token is persisted by default.",
      "It is stored under data/ and excluded from version control. On POSIX the file is created 0600; Windows inherits the directory ACL rather than a POSIX mode. Anyone who can read that file or the process memory can use this operator console."));
    privacyBody.appendChild(list);
  }

  function render() {
    renderTheme();
    renderSession();
    renderModel();
    renderWeb();
    renderRuntime();
    renderPrivacy();
  }

  radios.forEach((radio) => {
    radio.addEventListener("change", () => {
      if (radio.checked) actions.setThemePreference(radio.value);
    });
  });
  if (logoutButton) {
    logoutButton.addEventListener("click", () => actions.logout());
  }
  if (shortcuts) {
    shortcuts.addEventListener("click", () => openDialog("shortcuts-dialog"));
  }

  render();

  return {
    activate() {
      render();
      if (state.authenticated && !state.models.loading) {
        loadModels({ force: state.models.loaded });
      }
      if (state.authenticated) loadWeb({ force: false });
    },
    render,
    renderTheme,
    renderSession,
  };
}
