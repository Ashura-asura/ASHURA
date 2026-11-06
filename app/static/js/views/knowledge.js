/* Knowledge Studio: real stored experiences, provenance and conflict flags. */

import { api } from "../api.js";
import { state } from "../store.js";
import {
  $, el, icon, badge, toast, announce, copyText,
} from "../components.js";
import {
  formatCount, formatTimestamp, relativeTime, truncate, experienceStatus,
} from "../format.js";

function summaryValue(node, value) {
  if (!node) return;
  node.textContent = formatCount(value);
  node.title = value === null || value === undefined ? "Not available in this build" : "";
}

export function createKnowledgeView(actions) {
  const experiences = $("#k-experiences");
  const facts = $("#k-facts");
  const conflicts = $("#k-conflicts");
  const fts = $("#k-fts");
  const form = $("#memory-form");
  const queryInput = $("#memory-query");
  const memoryList = $("#memory-list");
  const memoryNote = $("#memory-note");
  const memoryDetail = $("#memory-detail");
  const refresh = $("#knowledge-refresh");
  const memoryToggle = $("#memory-toggle");
  const memoryClose = $("#memory-close");
  const tabs = Array.from(document.querySelectorAll("[data-ktab]"));

  let selected = null;

  function updateSummary() {
    const counts = state.status && state.status.counts ? state.status.counts : null;
    summaryValue(experiences, counts ? counts.experiences : null);
    summaryValue(facts, counts ? counts.facts : null);
    summaryValue(conflicts, counts ? counts.conflicts_open : null);
    summaryValue(fts, counts ? counts.fts_rows : null);
  }

  function filtered() {
    if (state.memory.tab === "conflicts") return state.memory.items.filter((item) => item.conflict);
    return state.memory.items;
  }

  function renderList() {
    if (!memoryList) return;
    memoryList.replaceChildren();
    if (state.memory.loading) {
      memoryList.appendChild(el("p", "memory-empty", "Loading stored experiences…"));
      return;
    }
    if (state.memory.error) {
      memoryList.appendChild(el("p", "memory-empty", state.memory.error));
      return;
    }
    const items = filtered();
    if (!items.length) {
      memoryList.appendChild(el("p", "memory-empty",
        state.memory.tab === "conflicts"
          ? "No conflict flags among the loaded records."
          : state.memory.query
            ? "No stored experience matched that search."
            : "No stored experiences were returned. Records enter this store through the controller's admission policy."));
      return;
    }
    for (const item of items) {
      const status = experienceStatus(item.status);
      const row = el("button", `memory-row${item.id === state.memory.selectedId ? " is-active" : ""}`);
      row.type = "button";
      row.dataset.memoryId = item.id;
      row.setAttribute("role", "listitem");
      row.appendChild(el("span", "q", truncate(item.input || "(no input)", 140)));
      row.appendChild(el("span", "a", truncate(item.output || "(no output)", 140)));
      const meta = el("span", "meta");
      meta.appendChild(badge(status.label, status.tone));
      if (item.category) meta.appendChild(el("span", "", item.category));
      if (item.reliability !== null && item.reliability !== undefined) {
        meta.appendChild(el("span", "", `reliability ${Number(item.reliability).toFixed(2)}`));
      }
      if (item.conflict) meta.appendChild(badge("Conflict flag", "bad"));
      meta.appendChild(el("span", "", relativeTime(item.ts)));
      row.appendChild(meta);
      row.addEventListener("click", () => select(item.id));
      memoryList.appendChild(row);
    }
  }

  function renderNote() {
    if (!memoryNote) return;
    const items = filtered();
    if (state.memory.tab === "conflicts") {
      memoryNote.textContent = `${formatCount(items.length)} flagged experience${items.length === 1 ? "" : "s"} among ${formatCount(state.memory.items.length)} loaded records. The full conflict registry is not exposed by this build.`;
    } else if (state.memory.query) {
      memoryNote.textContent = `${formatCount(items.length)} result${items.length === 1 ? "" : "s"} for “${state.memory.query}”.`;
    } else {
      memoryNote.textContent = "Recent stored experiences, newest first. Only records returned by the memory API are shown.";
    }
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

  function renderDetail() {
    if (!memoryDetail) return;
    memoryDetail.replaceChildren();
    const item = selected || state.memory.items.find((entry) => entry.id === state.memory.selectedId);
    if (!item) {
      const empty = el("div", "detail-empty");
      empty.appendChild(icon("knowledge", "icon"));
      empty.appendChild(el("h2", "", "Select a memory"));
      empty.appendChild(el("p", "", "Stored input, output, verification status, method, evidence score and conflict flag are shown here."));
      memoryDetail.appendChild(empty);
      return;
    }
    const status = experienceStatus(item.status);
    const inner = el("div", "detail-inner");

    const head = el("div", "detail-head");
    head.appendChild(el("h2", "", "Stored experience"));
    head.appendChild(badge(status.label, status.tone));
    if (item.conflict) head.appendChild(badge("Conflict flag", "bad"));
    inner.appendChild(head);

    if (item.conflict) {
      const banner = el("div", "conflict-banner");
      banner.appendChild(el("strong", "", "Conflicting evidence is on record."));
      banner.appendChild(el("span", "",
        "This build reports the flag but does not expose the conflict record, linked IDs or its resolution history. Resolution requires independent verification and explicit review."));
      inner.appendChild(banner);
    }

    const question = el("div", "detail-block");
    question.appendChild(el("h3", "", "Stored input"));
    question.appendChild(el("div", "detail-text", item.input || "No input recorded."));
    inner.appendChild(question);

    const answer = el("div", "detail-block");
    answer.appendChild(el("h3", "", "Stored output"));
    answer.appendChild(el("div", "detail-text answer", item.output || "No output recorded."));
    inner.appendChild(answer);

    const reliability = el("div", "detail-block");
    reliability.appendChild(el("h3", "", "Evidence score"));
    const row = el("div", "reliability-row");
    const value = item.reliability;
    const numeric = Number(value);
    if (value === null || value === undefined || !Number.isFinite(numeric)) {
      row.appendChild(el("span", "score", "Not available"));
    } else {
      row.appendChild(el("span", "score", numeric.toFixed(2)));
      const meter = document.createElement("progress");
      meter.className = "reliability-meter";
      meter.max = 1;
      meter.min = 0;
      meter.value = Math.max(0, Math.min(1, numeric));
      meter.setAttribute("aria-label", `Stored evidence score ${numeric.toFixed(2)} of 1`);
      row.appendChild(meter);
    }
    row.appendChild(el("span", "explain",
      "This is the score recorded by the admission policy. It is an evidence class, not a probability that the statement is true."));
    reliability.appendChild(row);
    inner.appendChild(reliability);

    const provenance = el("div", "detail-block");
    provenance.appendChild(el("h3", "", "Provenance"));
    const grid = el("div", "fact-grid");
    grid.appendChild(factCell("Record ID", item.id || "Not recorded"));
    grid.appendChild(factCell("Timestamp", formatTimestamp(item.ts)));
    grid.appendChild(factCell("Verification", status.label));
    grid.appendChild(factCell("Method", item.method || "Not recorded"));
    grid.appendChild(factCell("Category", item.category || "Not recorded"));
    grid.appendChild(factCell("Provenance label", item.label || status.label));
    grid.appendChild(factCell("Conflict flag", item.conflict ? "Set" : "Not set"));
    grid.appendChild(factCell("Source", "Experience store (admission policy)"));
    provenance.appendChild(grid);
    provenance.appendChild(el("p", "provenance-note",
      "Facts, admission-log entries and the full conflict index are not exposed by this build. This view never invents or recomputes those values."));
    inner.appendChild(provenance);

    const actionsRow = el("div", "detail-actions");
    const use = el("button", "button primary small");
    use.type = "button";
    use.appendChild(icon("send", "icon icon-sm"));
    use.appendChild(el("span", "", "Use input as prompt"));
    use.addEventListener("click", () => {
      actions.usePrompt(item.input || "");
      toast("Input loaded into the composer.");
    });
    actionsRow.appendChild(use);
    const copy = el("button", "button small");
    copy.type = "button";
    copy.appendChild(icon("copy", "icon icon-sm"));
    copy.appendChild(el("span", "", "Copy record"));
    copy.addEventListener("click", () => copyText(JSON.stringify(item, null, 2)));
    actionsRow.appendChild(copy);
    inner.appendChild(actionsRow);

    memoryDetail.appendChild(inner);
  }

  function render() {
    updateSummary();
    renderNote();
    renderList();
    renderDetail();
    tabs.forEach((tab) => {
      const active = tab.dataset.ktab === state.memory.tab;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function select(id) {
    state.memory.selectedId = id;
    selected = state.memory.items.find((item) => item.id === id) || null;
    renderList();
    renderDetail();
  }

  async function load(query = state.memory.query) {
    if (state.memory.loading) return;
    state.memory.query = String(query || "").trim();
    state.memory.loading = true;
    state.memory.error = null;
    if (memoryNote) memoryNote.textContent = state.memory.query
      ? `Searching for “${state.memory.query}”…`
      : "Loading recent experiences…";
    renderList();
    try {
      const data = await api.memory(state.memory.query, 50);
      state.memory.items = Array.isArray(data.items) ? data.items : [];
      state.memory.loaded = true;
      if (!state.memory.items.some((item) => item.id === state.memory.selectedId)) {
        state.memory.selectedId = null;
        selected = null;
      } else {
        selected = state.memory.items.find((item) => item.id === state.memory.selectedId) || null;
      }
      state.memory.loading = false;
      render();
      announce(`${state.memory.items.length} stored experiences loaded.`);
    } catch (error) {
      state.memory.loading = false;
      state.memory.error = error.status === 404
        ? "Memory inspection is not available for this controller."
        : (error.message || "Could not load stored experiences.");
      render();
      if (error.status === 401) actions.onAuthRequired();
    }
  }

  function activate() {
    updateSummary();
    if (!state.authenticated) {
      renderNote();
      renderList();
      renderDetail();
      return;
    }
    if (!state.memory.loaded && !state.memory.loading) load("");
    else render();
  }

  function openDrawer() {
    document.body.classList.add("memory-open");
    if (memoryToggle) memoryToggle.setAttribute("aria-expanded", "true");
    actions.syncScrim();
    if (queryInput) queryInput.focus();
  }

  function closeDrawer() {
    document.body.classList.remove("memory-open");
    if (memoryToggle) memoryToggle.setAttribute("aria-expanded", "false");
    actions.syncScrim();
  }

  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      load(queryInput ? queryInput.value : "");
    });
  }
  if (refresh) {
    refresh.addEventListener("click", async () => {
      await actions.refreshStatus({ quiet: true });
      updateSummary();
      await load(state.memory.query);
      toast("Knowledge data refreshed");
    });
  }
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      state.memory.tab = tab.dataset.ktab === "conflicts" ? "conflicts" : "experiences";
      render();
    });
  });
  if (memoryToggle) {
    memoryToggle.addEventListener("click", () => {
      if (document.body.classList.contains("memory-open")) closeDrawer();
      else openDrawer();
    });
  }
  if (memoryClose) memoryClose.addEventListener("click", closeDrawer);

  render();

  return {
    activate,
    updateSummary,
    syncResponsive() {
      if (window.matchMedia("(min-width: 901px)").matches) {
        document.body.classList.remove("memory-open");
        if (memoryToggle) memoryToggle.setAttribute("aria-expanded", "false");
      }
    },
    reset() {
      state.memory = {
        items: [],
        query: "",
        tab: "experiences",
        selectedId: null,
        loaded: false,
        loading: false,
        error: null,
      };
      selected = null;
      if (queryInput) queryInput.value = "";
      render();
    },
  };
}
