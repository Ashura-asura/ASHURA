/* DOM primitives, markdown, toasts, dialogs and clipboard helpers. */

import { escapeHtml } from "./format.js";
import { renderMath } from "./math.js";

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

export function el(tag, className = "", text = undefined) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function icon(name, className = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.appendChild(use);
  return svg;
}

export function badge(text, tone = "", title = "") {
  const node = el("span", `badge${tone ? ` ${tone}` : ""}`, text);
  if (title) node.title = title;
  return node;
}

export function iconButton(name, label, { className = "icon-btn", onClick, title } = {}) {
  const node = el("button", className);
  node.type = "button";
  node.setAttribute("aria-label", label);
  if (title) node.title = title;
  node.appendChild(icon(name, "icon icon-sm"));
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

export function button(label, {
  className = "button",
  iconName = "",
  title = "",
  type = "button",
  onClick,
} = {}) {
  const node = el("button", className);
  node.type = type;
  if (title) node.title = title;
  if (iconName) node.appendChild(icon(iconName, "icon icon-sm"));
  node.appendChild(el("span", "", label));
  if (onClick) node.addEventListener("click", onClick);
  return node;
}

export function clear(node) {
  if (node) node.replaceChildren();
}

/* ---- markdown --------------------------------------------------------------------------- */

function mathFallback(source, display, error) {
  const tex = String(source ?? "").trim();
  const marker = display ? "$$" : "$";
  const title = error ? ` title="${escapeHtml(error)}"` : "";
  return `<code class="math-unrendered"${title}>${escapeHtml(`${marker}${tex}${marker}`)}</code>`;
}

function mathMarkup(source, display, block = false) {
  const result = renderMath(source, display);
  if (result.html) {
    return block ? `<div class="math-display">${result.html}</div>` : `<span class="math-inline">${result.html}</span>`;
  }
  const fallback = mathFallback(source, display, result.error);
  return block ? `<div class="math-display">${fallback}</div>` : fallback;
}

function looksLikeInlineMath(source) {
  const tex = source.trim();
  if (!tex) return false;
  if (/[\^_=<>]|\\[A-Za-z]+/.test(tex)) return true;
  if (/^[A-Za-z][A-Za-z0-9]*$/.test(tex)) return true;
  return /[+\-*/]/.test(tex) && !/\b(?:and|or)\b/i.test(tex);
}

function extractMath(text, store) {
  const push = (tex, display) => {
    const index = store.length;
    store.push({ tex, display });
    return display ? `\u0003D${index}\u0003` : `\u0002M${index}\u0002`;
  };
  let working = String(text ?? "");
  working = working.replace(/\$\$([\s\S]+?)\$\$/g,
    (match, tex) => `\n${push(tex, true)}\n`);
  working = working.replace(/\\\[([\s\S]+?)\\\]/g,
    (match, tex) => `\n${push(tex, true)}\n`);
  working = working.replace(/\\\(([\s\S]+?)\\\)/g,
    (match, tex) => push(tex, false));
  working = working.replace(/(^|[^\\$])\$(?!\s)([^$\n]+?)(?<!\s)\$(?!\d)/g,
    (match, prefix, tex) => (looksLikeInlineMath(tex) ? `${prefix}${push(tex, false)}` : match));
  return working.replace(/\\\$/g, "$");
}

function splitTableRow(line) {
  let value = String(line ?? "").trim();
  if (value.startsWith("|")) value = value.slice(1);
  if (value.endsWith("|")) value = value.slice(0, -1);
  return value.split("|").map((cell) => cell.trim());
}

function isTableDelimiter(line) {
  const value = String(line ?? "").trim();
  if (!value.includes("|")) return false;
  const cells = splitTableRow(value);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function tableAlignment(cell) {
  if (cell.startsWith(":") && cell.endsWith(":")) return "center";
  if (cell.endsWith(":")) return "right";
  return "";
}

function renderCodeBlock(block) {
  const language = escapeHtml(String(block.lang || "code").replace(/[^A-Za-z0-9_+.-]/g, "")) || "code";
  const code = escapeHtml(String(block.code || "").replace(/\n$/, ""));
  return `<div class="code-block"><div class="code-head"><span>${language}</span>` +
    `<button type="button" class="copy-code" data-action="copy-code">Copy</button></div>` +
    `<pre><code>${code}</code></pre></div>`;
}

export function renderMarkdown(source) {
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
  const mathBlocks = [];
  working = extractMath(working, mathBlocks);

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
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex += 1) {
    const rawLine = lines[lineIndex];
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
    if ((match = trimmed.match(/^\u0003D(\d+)\u0003$/))) {
      closeList();
      const math = mathBlocks[Number(match[1])];
      output.push(math ? mathMarkup(math.tex, true, true) : "");
      continue;
    }
    if (trimmed.includes("|") && lineIndex + 1 < lines.length && isTableDelimiter(lines[lineIndex + 1])) {
      const headers = splitTableRow(trimmed);
      const alignments = splitTableRow(lines[lineIndex + 1]).map(tableAlignment);
      if (headers.length && alignments.length === headers.length) {
        closeList();
        const cellHtml = (tag, cell, index) => {
          const className = alignments[index] ? ` class="align-${alignments[index]}"` : "";
          return `<${tag}${className}>${cell || "&nbsp;"}</${tag}>`;
        };
        output.push('<div class="table-wrap"><table><thead><tr>' +
          headers.map((cell, index) => cellHtml("th", cell, index)).join("") +
          "</tr></thead><tbody>");
        let rowIndex = lineIndex + 2;
        while (rowIndex < lines.length) {
          const row = lines[rowIndex].trim();
          if (!row || !row.includes("|")) break;
          const cells = splitTableRow(row);
          if (cells.length !== headers.length) break;
          output.push("<tr>" +
            cells.map((cell, index) => cellHtml("td", cell, index)).join("") +
            "</tr>");
          rowIndex += 1;
        }
        output.push("</tbody></table></div>");
        lineIndex = rowIndex - 1;
        continue;
      }
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
  result = result.replace(/\u0002M(\d+)\u0002/g, (match, index) => {
    const math = mathBlocks[Number(index)];
    return math ? mathMarkup(math.tex, false, false) : "";
  });
  result = result.replace(/\u0003D(\d+)\u0003/g, (match, index) => {
    const math = mathBlocks[Number(index)];
    return math ? mathMarkup(math.tex, false, false) : "";
  });
  return result;
}

/* ---- clipboard -------------------------------------------------------------------------- */

export async function copyText(text) {
  const value = String(text ?? "");
  try {
    await navigator.clipboard.writeText(value);
    toast("Copied");
    return true;
  } catch (error) {
    const area = el("textarea", "clipboard-shim");
    area.value = value;
    area.setAttribute("readonly", "");
    area.setAttribute("aria-hidden", "true");
    document.body.appendChild(area);
    area.select();
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } catch (error) {
      copied = false;
    }
    area.remove();
    toast(copied ? "Copied" : "Could not copy", copied ? "" : "bad");
    return copied;
  }
}

/* ---- toast ------------------------------------------------------------------------------ */

let toastTimer = null;

export function toast(message, tone = "") {
  const node = document.getElementById("toast");
  if (!node) return;
  node.textContent = message;
  node.className = `toast${tone ? ` ${tone}` : ""}`;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    node.hidden = true;
  }, 3600);
}

export function announce(message) {
  const region = document.getElementById("live-region");
  if (!region) return;
  region.textContent = "";
  window.setTimeout(() => {
    region.textContent = message;
  }, 30);
}

/* ---- dialogs ---------------------------------------------------------------------------- */

export function openDialog(id) {
  const dialog = typeof id === "string" ? document.getElementById(id) : id;
  if (!dialog) return null;
  if (!dialog.open) dialog.showModal();
  return dialog;
}

export function closeDialog(id) {
  const dialog = typeof id === "string" ? document.getElementById(id) : id;
  if (dialog && dialog.open) dialog.close();
}

let confirmResolver = null;

export function confirmAction({ title = "Confirm", message = "", confirmLabel = "Delete", tone = "danger" } = {}) {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog) return Promise.resolve(false);
  const heading = dialog.querySelector("#confirm-title");
  const body = dialog.querySelector("#confirm-message");
  const yes = dialog.querySelector('[data-confirm="yes"]');
  const no = dialog.querySelector('[data-confirm="no"]');
  if (heading) heading.textContent = title;
  if (body) body.textContent = message;
  if (yes) {
    yes.textContent = confirmLabel;
    yes.className = `button ${tone === "danger" ? "danger" : "primary"}`;
  }
  if (no) no.textContent = "Cancel";
  if (confirmResolver) {
    const previous = confirmResolver;
    confirmResolver = null;
    previous(false);
  }
  dialog.showModal();
  return new Promise((resolve) => {
    confirmResolver = resolve;
  });
}

export function wireSharedDialogs() {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog) return;
  const settle = (value) => {
    if (confirmResolver) {
      const resolve = confirmResolver;
      confirmResolver = null;
      resolve(value);
    }
    closeDialog(dialog);
  };
  dialog.querySelectorAll("[data-confirm]").forEach((node) => {
    node.addEventListener("click", () => settle(node.dataset.confirm === "yes"));
  });
  dialog.addEventListener("cancel", (event) => {
    event.preventDefault();
    settle(false);
  });
  dialog.addEventListener("close", () => {
    if (confirmResolver) {
      const resolve = confirmResolver;
      confirmResolver = null;
      resolve(false);
    }
  });
  document.querySelectorAll("[data-close-dialog]").forEach((node) => {
    node.addEventListener("click", () => closeDialog(node.dataset.closeDialog));
  });
}

/* ---- raw data --------------------------------------------------------------------------- */

export function kvRow(key, value) {
  const row = el("div", "kv-row");
  row.appendChild(el("dt", "", key));
  const cell = el("dd", "");
  if (value instanceof Node) cell.appendChild(value);
  else cell.textContent = value === null || value === undefined || value === "" ? "Not available" : String(value);
  row.appendChild(cell);
  return row;
}
