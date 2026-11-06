/* HTTP client. Same-origin only; CSRF header on every mutating request. */

let csrfToken = null;

export class ApiError extends Error {
  constructor(message, status, requestId) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.requestId = requestId;
  }
}

export function setCsrfToken(value) {
  csrfToken = typeof value === "string" && value ? value : null;
}

export function getCsrfToken() {
  return csrfToken;
}

function headersFor(method, extra) {
  const headers = { Accept: "application/json", ...(extra || {}) };
  const safe = String(method || "GET").toUpperCase();
  if (csrfToken && safe !== "GET" && safe !== "HEAD" && safe !== "OPTIONS") {
    headers["X-CSRF-Token"] = csrfToken;
  }
  return headers;
}

export async function request(path, options = {}) {
  const method = options.method || "GET";
  const headers = headersFor(method, options.headers);
  const init = {
    method,
    credentials: "same-origin",
    headers,
    cache: "no-store",
  };
  if (options.signal) init.signal = options.signal;
  if (options.body !== undefined) {
    if (typeof options.body === "string") {
      init.body = options.body;
    } else {
      init.body = JSON.stringify(options.body);
      headers["Content-Type"] = "application/json";
    }
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error && error.name === "AbortError") throw error;
    throw new ApiError("Could not reach the local server.", 0);
  }
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let requestId;
    try {
      const data = await response.json();
      if (data && data.error) message = data.error;
      if (data && data.request_id) requestId = data.request_id;
    } catch (error) {
      // Keep the status fallback.
    }
    throw new ApiError(message, response.status, requestId);
  }
  return response;
}

export async function json(path, options = {}) {
  const response = await request(path, options);
  if (response.status === 204) return {};
  return response.json();
}

export const api = {
  login(token) {
    return json("/api/login", { method: "POST", body: { token } });
  },
  logout() {
    return json("/api/logout", { method: "POST", body: {} });
  },
  status() {
    return json("/api/status");
  },
  models() {
    return json("/api/models");
  },
  selectModel(model) {
    return json("/api/model", { method: "POST", body: { model } });
  },
  sessions(limit = 100) {
    return json(`/api/sessions?limit=${encodeURIComponent(limit)}`);
  },
  session(sessionId, options = {}) {
    const params = new URLSearchParams();
    if (options.limit) params.set("limit", String(options.limit));
    if (options.before) params.set("before", String(options.before));
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return json(`/api/sessions/${encodeURIComponent(sessionId)}${suffix}`);
  },
  createSession(title = "New chat") {
    return json("/api/sessions", { method: "POST", body: { title } });
  },
  renameSession(sessionId, title) {
    return json(`/api/sessions/${encodeURIComponent(sessionId)}`, {
      method: "PATCH",
      body: { title },
    });
  },
  deleteSession(sessionId) {
    return json(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  },
  memory(query = "", limit = 50) {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    return json(`/api/memory?${params.toString()}`);
  },
  webFacts(limit = 50, status = "") {
    const params = new URLSearchParams({ limit: String(limit) });
    if (status) params.set("status", status);
    return json(`/api/web/facts?${params.toString()}`);
  },
  reviewWebFact(id, status, note = "") {
    return json("/api/web/review", { method: "POST", body: { id, status, note } });
  },
  webExportUrl(includeRejected = false) {
    return `/api/web/export?include_rejected=${includeRejected ? "1" : "0"}`;
  },
  ocr(filename, data, sessionId, prompt) {
    return json("/api/ocr", {
      method: "POST",
      body: { filename, data, session_id: sessionId, prompt },
    });
  },
  stream(message, sessionId, signal, webSearch = false) {
    return request("/api/chat/stream", {
      method: "POST",
      body: { message, session_id: sessionId, web_search: webSearch },
      signal,
    });
  },
  exportUrl(sessionId, format = "md") {
    return `/api/sessions/${encodeURIComponent(sessionId)}/export?format=${encodeURIComponent(format)}`;
  },
};
