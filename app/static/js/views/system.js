/* System Monitor: only measured values from /api/status; absent measurements are explicit. */

import { state } from "../store.js";
import { $, el, toast } from "../components.js";
import {
  formatCount, formatDuration, formatMs, formatTimestamp, orUnavailable,
} from "../format.js";

function healthCell(key, value, tone, note) {
  const cell = el("div", `health-cell ${tone || "neutral"}`);
  const head = el("span", "k");
  head.appendChild(el("span", `dot ${tone === "ok" ? "ok" : tone === "bad" ? "bad" : tone === "warn" ? "warn" : ""}`));
  head.appendChild(el("span", "", key));
  cell.appendChild(head);
  cell.appendChild(el("span", "v", value));
  cell.appendChild(el("span", "n", note));
  return cell;
}

function metricRow(name, value, note, { unavailable = false } = {}) {
  const row = el("div", "metric-row");
  row.appendChild(el("span", "name", name));
  row.appendChild(el("span", `value${unavailable ? " unavailable" : ""}`, value));
  row.appendChild(el("span", "note", note));
  return row;
}

function pathLine(key, value) {
  const line = el("div", "path-line");
  line.appendChild(el("span", "k", key));
  line.appendChild(el("span", "", orUnavailable(value, "Not available")));
  return line;
}

function panel(title, body, { note = "", actions = null } = {}) {
  const section = el("section", "panel");
  const head = el("div", "panel-head");
  head.appendChild(el("h2", "", title));
  if (actions) head.appendChild(actions);
  section.appendChild(head);
  if (note) section.appendChild(el("p", "panel-note", note));
  const content = el("div", "section-body");
  if (Array.isArray(body)) {
    for (const node of body) content.appendChild(node);
  } else {
    content.appendChild(body);
  }
  section.appendChild(content);
  return section;
}

export function createSystemView(actions) {
  const body = $("#system-body");
  const refresh = $("#system-refresh");

  function render() {
    if (!body) return;
    const scroller = $(".system-view");
    const scrollTop = scroller ? scroller.scrollTop : 0;
    body.replaceChildren();
    const status = state.status;
    const worker = status && status.worker ? status.worker : null;
    const counts = status && status.counts ? status.counts : null;
    const reachable = Boolean(status);
    const updated = state.statusUpdatedAt ? formatTimestamp(state.statusUpdatedAt / 1000) : "Not checked";

    if (!status) {
      const callout = el("div", "callout warn");
      callout.appendChild(el("strong", "", state.statusError ? "Server status is unavailable" : "Checking server status"));
      callout.appendChild(el("span", "", state.statusError
        ? `${state.statusError} Values below are marked not available until /api/status answers.`
        : "Waiting for the first /api/status response. Values below are marked not available."));
      body.appendChild(callout);
    }

    const strip = el("div", "health-strip");
    strip.appendChild(healthCell(
      "Server health",
      reachable ? "Reachable" : state.statusError ? "Unreachable" : "Checking",
      reachable ? "ok" : state.statusError ? "bad" : "neutral",
      "This means /api/status answered. It is not model readiness."
    ));
    strip.appendChild(healthCell(
      "Controller worker",
      worker ? (worker.alive ? (worker.active ? `Busy · ${worker.active}` : "Running") : "Not running") : "Not available",
      worker ? (worker.alive ? "ok" : "bad") : "neutral",
      worker && worker.active_id ? `Active job ${worker.active_id}` : "Thread liveness only."
    ));
    strip.appendChild(healthCell(
      "Configured model",
      status && status.model ? status.model : "Not reported",
      "neutral",
      "The name is reported. Backend host and readiness are not exposed."
    ));
    strip.appendChild(healthCell(
      "Storage",
      status && (status.database || status.sessions_db) ? "SQLite configured" : "Not available",
      "neutral",
      "Plaintext SQLite. No encryption at rest. Sizes are not measured."
    ));
    body.appendChild(strip);

    const readiness = el("div", "callout info");
    readiness.appendChild(el("strong", "", "Health is not readiness."));
    readiness.appendChild(el("span", "",
      "The server can answer while the model backend is stopped, loading or unreachable. " +
      "This build does not probe generation readiness, so a configured model name must not be read as “online”."));
    body.appendChild(panel("Health and readiness", readiness, {
      note: `Status read at ${updated}.`,
    }));

    const runtimeRows = el("div", "metric-list");
    runtimeRows.appendChild(metricRow("Server uptime", status ? formatDuration(status.uptime_s) : "Not available",
      "Measured from process start.", { unavailable: !status }));
    runtimeRows.appendChild(metricRow("Version", status ? orUnavailable(status.version) : "Not available",
      "Reported by /api/status.", { unavailable: !status }));
    runtimeRows.appendChild(metricRow("Sessions stored", status ? formatCount(status.sessions) : "Not available",
      "Session store row count.", { unavailable: !status }));
    runtimeRows.appendChild(metricRow("Worker queue", worker ? `${formatCount(worker.queue_depth)} / ${formatCount(worker.max_queue)}` : "Not available",
      "Waiting jobs / maximum configured queue.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Average queue wait", worker ? formatMs(worker.avg_wait_ms) : "Not available",
      "Average over finished jobs since process start.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Average run time", worker ? formatMs(worker.avg_run_ms) : "Not available",
      "Average over finished jobs since process start.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Jobs completed", worker ? formatCount(worker.completed) : "Not available",
      "Since process start.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Jobs failed", worker ? formatCount(worker.failed) : "Not available",
      "Since process start. This is not a verification result.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Jobs cancelled", worker ? formatCount(worker.cancelled) : "Not available",
      "Since process start.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow("Jobs rejected", worker ? formatCount(worker.rejected) : "Not available",
      "Rejected because the bounded queue was full.", { unavailable: !worker }));
    runtimeRows.appendChild(metricRow(
      "Last job",
      worker && worker.last
        ? `${worker.last.kind || "job"} · ${worker.last.status || "unknown"} · ${formatMs(worker.last.run_ms)}`
        : "None since start",
      worker && worker.last
        ? `Wait ${formatMs(worker.last.wait_ms)} · run ${formatMs(worker.last.run_ms)}. ${worker.last.error ? worker.last.error : "No error recorded."} The worker does not expose when the job finished.`
        : "The worker has not finished a job in this process.",
      { unavailable: !worker }
    ));

    const countsRow = el("div", "counts-row");
    const countCells = [
      ["Experiences", counts ? counts.experiences : null, "Episodic records"],
      ["Facts", counts ? counts.facts : null, "Semantic records"],
      ["Open conflicts", counts ? counts.conflicts_open : null, "Unresolved index rows"],
      ["FTS rows", counts ? counts.fts_rows : null, "Searchable index"],
    ];
    for (const [key, value, note] of countCells) {
      const cell = el("div", "cell");
      cell.appendChild(el("span", "k", key));
      cell.appendChild(el("span", "v", formatCount(value)));
      cell.title = value === null || value === undefined ? "Not available in this build" : note;
      countsRow.appendChild(cell);
    }

    const grid = el("div", "grid-2");
    grid.appendChild(panel("Runtime metrics", runtimeRows, {
      note: "All values come from the status payload. No value is estimated.",
    }));
    grid.appendChild(panel("Recorded counts", countsRow, {
      note: "Counts are read from the memory database. A dash means the count was not returned, not zero.",
    }));
    body.appendChild(grid);

    const paths = el("div", "section-body");
    paths.appendChild(pathLine("Configuration", status ? status.config : null));
    paths.appendChild(pathLine("Memory database", status ? status.database : null));
    paths.appendChild(pathLine("Session database", status ? status.sessions_db : null));
    paths.appendChild(pathLine("Browser origin", window.location.origin));
    const storageNote = el("p", "storage-note");
    storageNote.appendChild(el("strong", "", "No encryption at rest."));
    storageNote.appendChild(document.createTextNode(
      " ASHURA stores both databases as plaintext SQLite. Filesystem permissions and OS disk encryption are outside this application. " +
      "The server refuses non-loopback bind addresses, but this screen cannot verify what else runs on the host."
    ));
    paths.appendChild(storageNote);
    body.appendChild(panel("Storage and paths", paths, {
      note: "Paths are reported by the server. Storage sizes are not available in this build.",
    }));

    const unavailableRows = el("div", "metric-list");
    const unavailable = [
      ["CPU utilisation", "No /api/status field and no sampler in this build."],
      ["System RAM", "No /api/status field. Total and available memory are not measured."],
      ["Disk free space", "No /api/status field. Database file sizes are not measured."],
      ["GPU utilisation and VRAM", "No /api/status field. This build does not query the MX350."],
      ["Model host and backend", "Not exposed. The configured name alone is not evidence of locality."],
      ["Model readiness", "Not exposed. No readiness probe exists in this build."],
      ["Model load state", "Not exposed. The UI cannot tell whether weights are resident."],
      ["Thermals and power", "Not measured by this build."],
    ];
    for (const [name, note] of unavailable) {
      unavailableRows.appendChild(metricRow(name, "Not available", note, { unavailable: true }));
    }
    body.appendChild(panel("Not measured by this build", unavailableRows, {
      note: "These are absent capabilities, not zeros and not healthy values.",
    }));

    if (scroller) scroller.scrollTop = scrollTop;
  }

  if (refresh) {
    refresh.addEventListener("click", async () => {
      await actions.refreshStatus({ quiet: false });
      render();
      toast("System status refreshed");
    });
  }

  render();

  return {
    activate: render,
    render,
  };
}
