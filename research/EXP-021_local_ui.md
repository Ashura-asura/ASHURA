# EXP-021 - Local web UI / workbench production pass

Date: 2026-11-06. Status: **engineering verification; no learning-capability claim.**

This report records the D-062/D-063 pass. D-064 later adds document intake, bounded agent tools,
optional server-side web research, a persistent token and task-aware continuation; those are
verified separately in `research/EXP-022_documents_tools_web.md`. The counts and limitations below
describe the state at this pass unless explicitly noted.

## Scope

The original UI (D-061) was a dependency-free MVP: one request at a time, no auth, no persistent
sessions and no streaming. D-062 turned it into a single-user local operator console without
adding a framework, CDN, external API or a second copy of the controller. This pass completes the
five-workspace workbench and adds local math/table rendering plus a runtime-only Ollama model
selector.

Architecture:

- `ThreadingHTTPServer` serves static files and JSON/SSE concurrently.
- One `ControllerWorker` thread owns every controller, model and SQLite access; its queue is
  bounded at 8 jobs by default and rejects overflow with 429.
- Chat sessions live in a separate SQLite file (`app/sessions.py`); history is injected into the
  same prompt path used by the CLI. A paginated session read (`limit`/`before`) keeps long
  transcripts bounded in the browser.
- Streaming uses SSE with cooperative cancellation. A cancelled answer persists only the user turn.
- Auth is a startup token (HttpOnly, SameSite=Strict cookie, or `X-ASHURA-Token`/Bearer for scripts),
  with CSRF, Host/Origin checks, a strict CSP, security headers, rate limits, request IDs and JSON
  access logs. Binding remains loopback-only.
- The frontend has five connected workspaces (Command Center, Execution Studio, Knowledge Studio,
  System Monitor, Settings & Security), session search, trace/memory/status inspection, OCR upload,
  theme switch, mobile drawers, a command palette and keyboard shortcuts.

## Math and rich text

- `app/static/vendor/katex/` contains KaTeX 0.16.22 (MIT), the licence and a version/provenance
  note. It is served from the same origin; there is no CDN request.
- `app/static/js/math.js` calls `renderToString(..., {output: "mathml"})`. MathML needs no KaTeX CSS
  or font files and emits no layout styles.
- The renderer requests `throwOnError: true`, `trust: false`, bounded `maxExpand`/`maxSize` and
  rejects any result containing a `style` attribute. Such an expression, or a parse error, falls
  back to visible TeX source instead of being rendered badly or weakening the CSP.
- `app/static/js/components.js` extracts inline `$...$`, `\(...\)`, display `$$...$$` and
  `\[...\]`, then renders Markdown tables with per-column alignment. Code blocks and inline code
  are extracted first, so math-like text inside them is not transformed.
- The CSP remains `script-src 'self'; style-src 'self'`; there are no inline scripts, styles, CDN
  origins, fonts or `unsafe-*` tokens.

## Verification

### Automated tests

```
python -m pytest -q tests/test_web.py   # 32 passed at this pass; 40 after EXP-022
python -m pytest -q                     # 328 passed at this pass; 367 passed, 2 skipped after EXP-022
```

The web tests cover worker serialization and queue bounds, session persistence/reopen and
pagination, history injection, SSE events, cancellation without persisting an assistant message,
session CRUD/export, OCR, auth/CSRF/Origin/Host rejection, security headers, token bootstrap,
logout/keep-alive, model listing, model switching, uninstalled tags and the non-Ollama rejection
path.

### Browser smoke (Echo stub)

Chromium 1248 headless against an isolated in-memory controller and session store:

- token unlock, logout, Escape-locked gate and session persistence across logout;
- SSE answer, trace inspector and all five workspaces;
- inline/display LaTeX to MathML, aligned Markdown tables, unsupported-math fallback and a
  no-injection check;
- unavailable model switching is labelled honestly for the Echo backend;
- theme toggle and explicit light/dark preference;
- no overflow or missing composer at 320, 375, 430, 768, 1024, 1440 and 1920 px;
- mobile sessions/inspector/operations/evidence/memory drawers;
- command palette, keyboard route shortcuts and labelled unlock field;
- no console, page or request errors other than the expected pre-auth 401.

Screenshot runs freeze server time, UUIDs and motion and mask the ephemeral port. All **19**
baselines compare at 0.000%-0.019% difference on this Windows Chromium build. `--update` regenerates
them; CI runs `--no-snapshots` because font rasterization is platform-specific.

### Real model switch check

`design/EXP-021_model_switch_verification.json` records an HTTP-level run against the real local
Ollama endpoint (`config/ashura.ollama.toml`, `http://127.0.0.1:11434`, 2026-11-06T16:35:30Z),
using a temporary memory/session database. Every step used the same `/api/models`, `/api/model`,
`/api/status` and `/api/chat` routes as the Settings screen.

- `GET /api/models` returned all five installed tags: `tony:7b-gpa3`, `lfm3:latest`,
  `qwen3.5:2b`, `tony:7b`, `tony:7b-agentic3`; all five digests matched `config/models.toml` and
  every tag carried its documented role. The active tag was `tony:7b-gpa3`.
- Switch to `qwen3.5:2b`: `changed: true`, `previous: tony:7b-gpa3`,
  `previous_unloaded: true`; `/api/status` then reported `ollama:qwen3.5:2b`.
- One chat turn, `Reply with the single word OK.`, returned `OK` in 19.85 s with
  `verification: "unavailable"` (not verified). `ollama ps` then showed `qwen3.5:2b`.
- Switch back to `tony:7b-gpa3`: `previous_unloaded: true`; `/api/status` again reported
  `ollama:tony:7b-gpa3`; `ollama ps` was empty after the unload.
- The launch configuration was not rewritten. A server restart therefore returns to the
  configured model; this restart behaviour was not separately exercised in the check.
- The Settings panel was then driven in Chromium against the same real runtime and temporary
  databases. It listed all five options with their roles, switched to `qwen3.5:2b` (detail:
  `Fallback only`, 2.5 GB, digest `0689d44085e0`, `Active for subsequent turns.`), updated the
  runtime panel and header to `ollama:qwen3.5:2b`, and switched back to `tony:7b-gpa3`. Evidence:
  `design/EXP-021_model_switch_ui.json` and `design/EXP-021_model_switch_ui.png`.
- The second browser smoke still uses the Echo stub, so it verifies only the unavailable path.

### Earlier real-model check (D-062 pass)

One `tony:7b-gpa3` streaming turn through the same console returned the exact requested text;
trace total was 13.6 s including model load, and the model was unloaded afterwards.

## Limitations

- One browser, one Echo-stub session, one real model-switch sequence and one 2B turn. This is not
  a load, soak or endurance test.
- The switch check does not cover a switch while a response is streaming, two clients switching
  concurrently, or restart persistence. Switching is serialized by the single worker and affects
  only the process.
- Browser screenshot comparison is a manual verification and is not portable across operating
  systems; CI runs behavior checks without snapshots.
- At the time of this pass there was no syntax highlighting, diff editor, artifact/canvas workflow,
  web browsing, hosted file/code execution, image generation, general multimodal chat, voice mode,
  multi-user accounts, TLS or cross-process queue. EXP-022 later adds optional server-side web
  research and local document intake; hosted code execution, multimodal generation, voice, accounts,
  TLS and a cross-process queue remain absent.
- Math rendering does not improve model reasoning. `tony:7b-gpa3` remains a 7.6B Q4_K_M checkpoint
  with a 4k-token working context; exact arithmetic is the only independently verified math path.
- KaTeX is vendored source: version updates require review of the file and its licence. There is no
  SRI check because the asset is same-origin.
- No accessibility audit or session-database backup/restore test.

## Decision

Adopt the console architecture as D-062 (superseding D-061), and the math/model-selection rules as
D-063. Keep the local-only, single-user and non-parity limits explicit in the README.
