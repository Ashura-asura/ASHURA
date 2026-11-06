/* Formatting and honest state labels. */

export function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatMs(ms) {
  const value = Number(ms);
  if (!Number.isFinite(value)) return "—";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(value / 1000).toFixed(value < 10000 ? 2 : 1)} s`;
}

export function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`;
  return `${Math.floor(value / 3600)}h ${Math.floor((value % 3600) / 60)}m`;
}

export function relativeTime(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) return "unknown";
  const seconds = Math.max(0, Date.now() / 1000 - value);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 86400 * 7) return `${Math.floor(seconds / 86400)}d ago`;
  return new Date(value * 1000).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export function formatTime(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) return "";
  return new Date(value * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function formatTimestamp(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) return "Not recorded";
  return new Date(value * 1000).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function formatCount(value) {
  if (value === null || value === undefined) return "—";
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString() : "—";
}

export function isUnavailable(value) {
  return value === null || value === undefined || value === "";
}

export function orUnavailable(value, fallback = "Not available") {
  return isUnavailable(value) ? fallback : String(value);
}

const VERIFICATION = {
  verified: {
    state: "verified",
    label: "Verified",
    tone: "ok",
    note: "An independent verifier checked this answer and confirmed it.",
  },
  failed: {
    state: "failed",
    label: "Verification failed",
    tone: "bad",
    note: "An independent verifier checked this answer and rejected it.",
  },
  unavailable: {
    state: "unavailable",
    label: "Not verified",
    tone: "warn",
    note: "No verifier was available for this answer. This is not a pass and not a failure.",
  },
  unknown: {
    state: "unknown",
    label: "No verification record",
    tone: "",
    note: "This record has no three-state verification field. Its status cannot be reconstructed.",
  },
};

export function verificationInfo(meta) {
  const source = meta || {};
  const raw = source.verification;
  if (raw === "verified" || raw === "failed" || raw === "unavailable") {
    return { ...VERIFICATION[raw], raw };
  }
  // Backward compatibility for records written before the three-state field.
  if (source.verified === true) {
    return { ...VERIFICATION.verified, raw: "verified", legacy: true };
  }
  if (source.verified === false) {
    return { ...VERIFICATION.failed, raw: "failed", legacy: true };
  }
  return { ...VERIFICATION.unknown, raw: null };
}

const ADMISSION = {
  ADMITTED: { label: "Admitted to memory", tone: "ok" },
  MERGED: { label: "Merged with earlier record", tone: "info" },
  REVIEW_REQUIRED: { label: "Review required", tone: "warn" },
  DISCARDED: { label: "Discarded by policy", tone: "" },
  CONFLICT_RESOLVED: { label: "Conflict resolved", tone: "ok" },
};

export function admissionInfo(value) {
  if (!value) return null;
  const key = String(value).split(" / ")[0].trim();
  const known = ADMISSION[key];
  return {
    label: known ? known.label : String(value),
    tone: known ? known.tone : "",
    raw: String(value),
  };
}

const EXPERIENCE_STATUS = {
  verified: { label: "Verified record", tone: "ok" },
  user_provided: { label: "User-provided", tone: "warn" },
  unverified: { label: "Unverified record", tone: "warn" },
  failed: { label: "Verification failed", tone: "bad" },
  superseded: { label: "Superseded", tone: "" },
  pending: { label: "Pending verification", tone: "info" },
};

export function experienceStatus(value) {
  const key = String(value || "").toLowerCase();
  const known = EXPERIENCE_STATUS[key];
  return known ? { ...known, raw: value } : {
    label: value ? String(value) : "No status record",
    tone: "",
    raw: value,
  };
}

export function sessionGroup(timestamp) {
  const value = Number(timestamp);
  if (!Number.isFinite(value) || value <= 0) return "Older";
  const age = Date.now() / 1000 - value;
  if (age < 86400) return "Today";
  if (age < 86400 * 2) return "Yesterday";
  if (age < 86400 * 7) return "Previous 7 days";
  return "Older";
}

export function truncate(value, length = 90) {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  if (text.length <= length) return text;
  return `${text.slice(0, Math.max(0, length - 1)).trimEnd()}…`;
}
