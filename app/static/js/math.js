/* Local LaTeX rendering through a vendored KaTeX build (MIT, see vendor/katex).
 *
 * Only MathML output is used: it needs no KaTeX CSS, fonts or CDN. The strict CSP
 * (style-src 'self') forbids inline style attributes, so any equation that would
 * emit one is rejected and shown as its source instead of being rendered badly.
 */
import katex from "../vendor/katex/katex.min.js";

const MAX_SOURCE = 4000;

export function renderMath(source, display = false) {
  const tex = String(source ?? "").trim();
  if (!tex) return { html: null, error: "empty expression" };
  if (tex.length > MAX_SOURCE) {
    return { html: null, error: `expression is longer than ${MAX_SOURCE} characters` };
  }
  try {
    const html = katex.renderToString(tex, {
      displayMode: Boolean(display),
      output: "mathml",
      throwOnError: true,
      strict: "ignore",
      trust: false,
      maxExpand: 1000,
      maxSize: 20,
    });
    // A generated style attribute would be blocked by the CSP and could hide content.
    if (/<[a-z][^>]*\sstyle\s*=/i.test(html)) {
      return { html: null, error: "this expression needs inline styling, which the CSP forbids" };
    }
    return { html, error: null };
  } catch (error) {
    return { html: null, error: error && error.message ? String(error.message) : "KaTeX could not parse this expression" };
  }
}
