# ASHURA Workbench — Phases 2–5 Implementation Plan

Status: **proposal, gated on Phase 1 approval**. No implementation work has started.

This plan preserves every existing endpoint, security restriction and persistence
guarantee. Backend changes are additive and read-only unless a section explicitly says
otherwise. The current console remains production until the new shell passes the same
auth, streaming, cancellation, persistence and export tests.

---

## 1. Phase overview

| Phase | Scope | Exit criteria |
| --- | --- | --- |
| **2** | Design foundation, shell, Command Center, themes, logout, Command palette | Current chat parity plus the new shell; 315 existing tests plus new pagination/web tests green; manual desktop/mobile smoke; no security regression. |
| **3** | Execution Studio, Knowledge Studio, additive evidence APIs | Trace/evidence views use only real fields; memory detail/conflicts/admission are real; no fabricated operations; API tests green. |
| **4** | System Monitor, Settings & Security, measured status fields, optional model probe | Health vs readiness is explicit; absent metrics render "not available"; logout and privacy statements are accurate; API tests green. |
| **5** | Playwright browser CI, screenshot regression, accessibility, long-conversation hardening, docs | Browser suite green in the pinned CI container at 320/375/430/768/1024/1440/1920; axe has no serious/critical findings; docs and test counts updated. |

Each phase ends with a reviewable commit (or small commit series) and an updated
`research/EXP-021_local_ui.md` entry. No phase starts before the previous exit criteria
are met.

---

## 2. Phase 2 — Foundation and Command Center

### 2.1 Frontend structure

Replace the single `style.css` and `app.js` with native ES modules and component CSS.
No framework, no CDN, no build step.

| File | Action | Responsibility |
| --- | --- | --- |
| `app/static/index.html` | Rewrite | Shell, five workspace sections, dialogs, rail, topbar, statusbar, skip link. |
| `app/static/css/tokens.css` | Add | Copy of the approved token set (`design/mockups/tokens.css`). |
| `app/static/css/base.css` | Add | Reset, typography, focus, selection, utilities, buttons, chips, fields, panels. |
| `app/static/css/shell.css` | Add | App grid, rail, topbar, statusbar, workspace host, drawers, badges. |
| `app/static/css/command.css` | Add | Sessions, conversation, turns, composer, turn inspector. |
| `app/static/js/theme-boot.js` | Add | Tiny classic script in `<head>`: apply stored/system theme before first paint to avoid a flash. |
| `app/static/js/api.js` | Add | Fetch wrapper, CSRF, auth errors, SSE reader, abort support, request timeout. |
| `app/static/js/store.js` | Add | One state store: status, sessions, current session, messages, selections, filters, theme, capabilities. |
| `app/static/js/format.js` | Add | Time/duration/bytes formatting, escape, safe Markdown renderer, verification/operation state helpers. |
| `app/static/js/components.js` | Add | Chips, badges, dialogs, toast, empty states, code block, copy button, meter. |
| `app/static/js/views/command.js` | Add | Sessions, conversation, composer, turn inspector rendering/events. |
| `app/static/js/app.js` | Rewrite | Boot, hash routing, rail, workspace switching, topbar, statusbar, palette, shortcuts, global events. |
| `app/static/style.css` | Delete after cutover | Replaced by the CSS modules. Git history preserves it. |
| `app/static/app.js` | Delete after cutover | Replaced by the JS modules. Git history preserves it. |
| `app/static/favicon.svg` | Keep | No change. |

`theme-boot.js` must be a classic script loaded synchronously before the stylesheet
(or immediately after it) because ES modules are deferred. It reads
`localStorage["ashura-theme"]`, resolves `system` with `matchMedia`, and sets
`document.documentElement.dataset.theme`. It must not write anything else.

### 2.2 Command Center behavior

Port and refine the current behavior:

- Session list with filter, new task, rename, delete, export (Markdown and JSON).
- Session detail with a "showing latest N" notice when the transcript is capped.
- Send with SSE streaming; Stop with `AbortController`; retry as a new turn.
- OCR upload with client-side type/size checks, progress state and a non-cancellable
  explanation; server limits remain the authority.
- Markdown rendering with fenced code blocks and copy; sanitize/escape all model text.
  Do not enable raw HTML.
- Per-turn inspector with Summary/Trace/Memory tabs; Memory links to Knowledge Studio
  until the Phase 3 detail API exists.
- Theme selector (system/dark/light) in the topbar menu and Settings.
- Logout action calling `POST /api/logout` with CSRF, aborting the stream, clearing
  state and showing the unlock dialog.
- Command palette (`Ctrl K`): workspace commands + loaded sessions only. It does not
  query memory or invent results.
- Status polling: every 5 s while visible, pause on `document.hidden`, refresh on
  visibility change; no polling storms after errors.
- Empty/loading/error states for every panel.

### 2.3 Additive session pagination

Current behavior returns the latest 200 messages (`app/sessions.py:115`). Keep that
default and add optional pagination so long conversations are reachable.

**API:** `GET /api/sessions/<id>?limit=200&before=<message-id>`

- `limit`: integer 1–1000, default 200.
- `before`: optional message id; return messages with `id < before` (older), ordered
  ascending.
- Response keeps `session` and `messages`, adds:
  - `has_more`: whether older messages exist;
  - `total`: total message count for the session (or `null` if the count fails).
- Invalid id/limit → 400. Unknown session → 404. No schema change; the existing
  `(session_id, id)` index supports it.

**Files:** `app/sessions.py` (`messages(..., before=None)`, `count_messages`),
`app/web.py` (`get_session` query parsing), `tests/test_sessions.py` (new),
`tests/test_web.py` (route/auth/clamp tests).

**UI:** show the latest page, a "Load earlier messages" button at the top when
`has_more`, and a notice "Showing the latest 200 of N messages. Export includes the
full transcript." Export remains `limit=None`.

### 2.4 Static delivery and packaging

- `static_file` already resolves nested paths under `app/static`; add a test for
  `/static/css/tokens.css` and `/static/js/app.js`.
- Update `pyproject.toml` package data:
  `app = ["static/*", "static/css/*", "static/js/*", "static/favicon.svg"]`.
  Without this, `pip install` omits the new directories.
- Keep CSP unchanged: no inline scripts, no inline event handlers, no inline
  `style=""` attributes in HTML. Dynamic visual values use CSSOM (`el.style.width`)
  or data attributes, which the current app already does for the textarea.
- Add `Cache-Control: no-store` for HTML and API responses if not already present;
  static assets may use a short cache with a content hash or no cache. Do not add a
  service worker.

### 2.5 Phase 2 tests

- All 315 existing tests.
- New session pagination tests: default, lower/upper clamp, `before`, `has_more`,
  `total`, unknown session, invalid parameters.
- Web auth/CSRF tests for the new query path.
- Static path tests for nested assets.
- A test asserting the production HTML contains no forbidden claims:
  `encrypted at rest`, `Nothing leaves this machine`, `local · online`.
- Manual smoke: unlock, send/stream/stop/retry, reload persistence, OCR, rename,
  delete, exports, theme, palette, logout, 320/390/768/1024/1440 widths.

**Phase 2 exit:** visual review of the real shell against the mockup, all tests green,
no console errors, no horizontal overflow at the required widths.

---

## 3. Phase 3 — Execution Studio and Knowledge Studio

### 3.1 Additive read-only APIs

All routes require the same authentication as `/api/status`; all DB reads run inside
`ControllerWorker`; all limits are clamped; all errors are JSON with the existing
codes. No writes, no schema changes.

| Endpoint | Response | Notes |
| --- | --- | --- |
| `GET /api/memory/<id>` | `item` (full experience incl. `source`, `related_ids`, `outcome`, `repeat_count`, `content_hash`), `admission` (latest `admission_log` row or `null`), `conflicts` (rows involving the id), `related` (summaries of related ids) | 32-hex id; 404 for unknown; limit related/conflicts to 20 each. |
| `GET /api/conflicts?open_only=1&limit=50` | `items` from `AMA.conflicts`, joined with new/old claim text, statuses, reliabilities, policy, resolution, timestamps | `open_only` default 1; limit 1–200. |
| `GET /api/facts?limit=50` | `items` from `facts`: `text`, `source_exp_id`, `reliability`, `verification_method`, `provenance` (parsed JSON), `derivation`, `ts` | Optional; only if a Facts tab is approved. |
| `GET /api/operations?limit=50` | Process-lifetime worker journal: id, kind, state, submitted/started/finished, wait/run ms, sanitized error, optional session/message ids | Optional; in-memory only, bounded, no prompts unless approved. |

**Implementation notes**

- `app/web.py`: add `_memory_detail()` and `_conflicts()` handlers; dispatch under the
  existing authenticated API branch; use `self.server.app.worker.submit(...)` exactly
  like `_memory`.
- `app/worker.py`: for the optional journal, add a `deque(maxlen=50)` and record
  submit/start/finish/cancel/fail. Extend `Job`/`submit` with optional metadata
  (`session_id`, `message_id`, `question` truncated to 200 chars) only if the owner
  approves showing operation questions. Default to no prompt text.
- `learning/ama.py`: no new writes. Use `AMA.conflicts()`, direct SELECTs on
  `experiences`, `admission_log`, `facts`, `conflicts`. Parse `features` JSON safely;
  on malformed JSON return `features: null`, not a crash.
- Never let a new endpoint bypass the worker's single SQLite connection.
- Rate-limit new reads (e.g. 120/min) and return 429 consistently.
- The model/prompt text is already local; still avoid returning more than the UI needs.

### 3.2 Execution Studio UI

- `app/static/css/execution.css`
- `app/static/js/views/execution.js`
- Update `index.html` workspace section, `components.js` for step cards/evidence,
  `store.js` for selected operation/evidence tab, `app.js` for routing.

Behavior:

- Derive completed operations from persisted assistant messages with a trace.
- Show live operations from the current stream and, if approved, the worker journal.
  Label in-memory history "since server start".
- Render verification from `step.verification`; never from `step.ok`.
- Evidence drawer on < 1180; operations drawer on < 760 via a real button.
- Copy trace as JSON (client-side).
- Empty state when no traced turn exists.

### 3.3 Knowledge Studio UI

- `app/static/css/knowledge.css`
- `app/static/js/views/knowledge.js`
- Update shell/route/store.

Behavior:

- Summary from `/api/status.counts`; `null` → "not available".
- Experiences tab from `/api/memory`; search with a 250 ms debounce and request
  cancellation; always show provenance labels.
- Detail from `/api/memory/<id>` when available; fall back to the list item fields
  with a note "detail fields not available in this build" if the endpoint is not
  approved.
- Conflicts tab from `/api/conflicts`; show new/old claims, statuses, scores, policy,
  resolution. No resolve button; show the CLI command.
- Admissions tab from the latest admission rows returned by the detail/list API. If
  there is no list endpoint for admission log, only show admission for a selected
  record; do not fabricate a feed.
- Facts tab only if `/api/facts` is approved; otherwise keep the count in the summary
  and omit the tab.
- Reliability copy is mandatory: "The stored evidence class, not a probability that
  the claim is true."

### 3.4 Phase 3 tests

- API: auth required; 404/400 paths; id validation; limit clamps; malformed conflict
  features; empty DB; worker queue full; no SQLite access from the HTTP thread (test
  with a thread check or by asserting the worker job path).
- UI browser/unit helpers: verified/failed/unavailable rendering; admission string
  preserved; conflict badge vs detail; no "confidence %"; `null` counts.
- Manual: select a persisted trace, inspect step I/O; open a conflict; verify the
  command shown matches `python -m learning.review resolve`.
- `research/EXP-021_local_ui.md` records the new evidence views and their limits.

---

## 4. Phase 4 — System Monitor and Settings & Security

### 4.1 Additive status fields

Extend `GET /api/status` with measured values. Existing fields are unchanged.

```jsonc
{
  "system": {
    "sampled_at": 1760000000.0,
    "cpu_percent": 18.2,          // null if unavailable
    "cpu_basis": "since previous sample",
    "memory": {"total": 16800000000, "available": 6800000000,
               "used": 10000000000, "percent": 59.4},
    "process": {"pid": 1234, "rss": 1820000000, "threads": 12},
    "disk": {"path": "C:\\...\\data", "total": 500000000000,
             "free": 108000000000}
  },
  "storage": {
    "memory_db": {"path": "data/ashura.db", "bytes": 147456},
    "sessions_db": {"path": "data/ui_sessions.db", "bytes": 212992},
    "payload": {"pages": {...}, "total_bytes": 120000, "rows": {...}}
  },
  "runtime": {
    "backend": "ollama",
    "host": "http://127.0.0.1:11434",
    "host_loopback": true,
    "context": 4096,
    "digest": "2a86766287cf",
    "last_stats": {"eval_count": 42, "eval_duration_ns": 123, "total_duration_ns": 456}
  },
  "capabilities": {"system_metrics": true, "storage_metrics": true, "model_probe": true}
}
```

**Implementation notes**

- `system`, `process`, `disk`: computed on the HTTP thread with `psutil`; no DB access.
  `cpu_percent(interval=None)` measures since the previous call; label it. The first
  sample may be `0.0`; include a timestamp and let the UI say "first sample".
- `storage`: `Path.stat()` on the configured paths. `payload` uses
  `AMA.storage_report()` inside the worker; cache it for ~30 s to avoid queueing on
  every poll. If the worker is busy, return the cached value and its timestamp.
- `runtime`: duck-type `controller.model.cfg`; expose only non-secret fields. Redact
  userinfo from the host URL. Do not expose tokens/keys.
- `host_loopback`: reuse `is_loopback()`; handle IPv6 and hostnames.
- All new values are `null` rather than `0` when unavailable.
- `pyproject.toml` already has `psutil`; no new runtime dependency.

### 4.2 Optional model probe

`POST /api/model/probe` (CSRF + auth + rate limit 6/min):

- Refuse with 409 when `worker.stats()["active"]` is not `null` ("worker busy").
- Only for `OllamaModel`; otherwise `{"supported": false}`.
- Call `list_models(host, timeout=2.0)` and `running_models(host, timeout=2.0)`
  (add optional `timeout` parameters in `foundation/ollama_model.py`).
- Return configured/installed/running, digest match (`true`/`false`/`null`), latency,
  `checked_at`, and a sanitized error. Never generate tokens.
- Do not cache a probe as a permanent status; the UI shows the last probe time.
- If the endpoint is non-loopback, the probe result and the UI both flag that the
  model is remote.

**Alternative if the owner rejects a probe:** omit the button and keep readiness
"not probed"; the System Monitor is still useful from the status fields.

### 4.3 Settings & Security UI

- `app/static/css/system.css`, `app/static/css/settings.css`
- `app/static/js/views/system.js`, `app/static/js/views/settings.js`
- Theme selector with system/dark/light and live OS following.
- Logout with CSRF; clear state; unlock dialog. Copy states that the launch token is
  not rotated and other browsers are not revoked.
- Read-only runtime values; no model download/edit.
- Privacy copy driven by `runtime.host_loopback`; if `false`, show a clear warning that
  prompts are sent to that endpoint.
- Storage sizes from real bytes; plaintext SQLite statement.
- Security posture list and "not claimed" list; no encryption/TLS/multi-user claims.
- Keyboard reference.

### 4.4 Phase 4 tests

- Status shape and nulls; CPU/memory/disk present on the test host; storage sizes
  match `Path.stat()`; runtime redaction; non-loopback flag.
- Probe: unsupported backend, worker busy, successful fake, timeout, rate limit,
  auth/CSRF, no prompt generation.
- UI: metrics render "not available" when null; health vs readiness wording; logout
  clears cookie and shows unlock; theme system follows a mocked `matchMedia`; privacy
  copy switches on loopback.
- Manual: measure CPU/RAM against Task Manager; verify storage sizes; stop Ollama and
  confirm the UI shows unreachable/not probed without breaking the page.

---

## 5. Phase 5 — Browser CI, accessibility and hardening

### 5.1 Test layout

```
tests/browser/
  __init__.py
  conftest.py              # app/server fixture, scripted model, browser, page
  test_auth.py             # login, invalid token, logout, cookie, CSRF
  test_command.py          # send, stream, stop, retry, persistence, OCR, export
  test_sessions.py         # rename, delete, long conversation, load earlier
  test_execution.py        # traces, verified/failed/unavailable, evidence
  test_knowledge.py        # provenance, reliability, conflicts, admissions
  test_system.py           # health/readiness, metrics, nulls, probe states
  test_settings.py         # themes, logout, privacy, shortcuts
  test_responsive.py       # 320/375/430/768/1024/1440/1920
  test_accessibility.py    # axe, skip link, focus, tabs, live regions
  test_recovery.py         # stream error, reload, server restart persistence
  test_visual.py           # screenshot baselines, dark/light, key widths
  assets/axe.min.js        # pinned local copy, no CDN
  snapshots/               # baselines generated in the pinned container
```

Use plain `pytest` + `sync_playwright()` fixtures; `pytest-playwright` is not required.
The server fixture starts `AppHTTPServer(("127.0.0.1", 0), app)` in a thread with a
fixed token/CSRF, temp DBs, and a scripted model that can:

- emit tokens with deterministic delays for streaming/cancel tests;
- return a verified arithmetic response;
- return `verification: "unavailable"` for a prose answer;
- return `verification: "failed"` for a controlled case;
- fail mid-stream for recovery tests;
- handle OCR without the real Tesseract stack.

Reuse the fake patterns already in `tests/test_web.py`; do not weaken those tests.

### 5.2 Required scenarios

| Requirement | Test |
| --- | --- |
| Login/logout | token bootstrap, cookie set, logout clears cookie, unlock dialog returns, CSRF required. |
| Persistence | send, reload, session and message still present; server restart with the same DB. |
| Streaming | incremental token text appears; status region announces start/end; no full-transcript `aria-live`. |
| Cancellation | Stop → cancelled state; user turn remains; no assistant answer persisted. |
| Retry | retry creates a new turn and a new response; original remains. |
| Recovery | mid-stream error shows inline error + retry; reload after error is stable; queue-full 429 path covered by API tests. |
| Uploads | file chooser / drag-drop, type/size validation, OCR result rendered, temp file not exposed. |
| Long conversations | seed 250 messages; latest 200 shown; load earlier reaches all; export includes 250. |
| Code rendering | fenced block, copy button, no raw HTML execution (XSS payload stays text). |
| Inspectors | turn inspector, execution evidence, memory detail; unknown id empty states. |
| Themes | system/dark/light, persistence across reload, live system change, no flash. |
| Responsive | all seven widths; no horizontal page overflow; drawers accessible; composer visible. |
| Keyboard | skip link, `Ctrl K`, `Alt 1–5`, tab order, `Esc` closes drawers/dialogs, focus returns. |
| Accessibility | axe no serious/critical; landmarks; contrast; target sizes; reduced motion. |
| Visual | key workspaces dark/light; masked dynamic values; baseline compare. |

### 5.3 Screenshot regression

- Run only in the pinned Playwright container
  `mcr.microsoft.com/playwright/python:v1.61.0-noble` so fonts/browser are stable.
- `device_scale_factor=1`, `locale=en-US`, `timezone_id=UTC`, color scheme per test,
  `reduced_motion="reduce"` for screenshots.
- Mask timestamps, uptime, queue depth, CPU/RAM, storage sizes, session titles with
  generated counts, and any random ids. Add `data-visual-mask` attributes rather than
  masking entire panels.
- Compare with Pillow: fail if more than 0.1% of pixels differ by more than a small
  per-channel threshold; write a diff image on failure.
- `UPDATE_SNAPSHOTS=1` regenerates baselines; review every changed baseline manually.
- Baselines: Command (320/375/430/768/1024/1440/1920), Execution (1440), Knowledge
  (1440), System (1440), Settings (1440), dark and light for Command (1440) and
  Settings (1440).

### 5.4 CI

Keep the existing 8 jobs. Add:

```yaml
browser:
  runs-on: ubuntu-latest
  container:
    image: mcr.microsoft.com/playwright/python:v1.61.0-noble
  steps:
    - uses: actions/checkout@v4
    - run: pip install -e ".[dev,browser]"
    - run: python -m pytest tests/browser -q
    - uses: actions/upload-artifact@v4
      if: failure()
      with:
        name: browser-failure
        path: test-results/
```

- `[browser]` extra: `playwright==1.61.0`, `Pillow>=10`.
- Do not add Playwright to runtime dependencies.
- Browser tests use the fake model and never call Ollama, so the job is deterministic
  and offline.
- If the container approach proves impractical, fall back to `ubuntu-latest` with
  `python -m playwright install --with-deps chromium` and accept a slightly higher
  screenshot threshold; document the change.

### 5.5 Accessibility verification

- Inject `tests/browser/assets/axe.min.js` (pinned) and run `axe.run()` per workspace;
  fail on `serious`/`critical`.
- Manual checklist: keyboard-only pass, NVDA on Windows for streaming and drawers,
  200% zoom, 320 px reflow, forced colors/high contrast.
- Record results in `research/EXP-021_local_ui.md`; list any exceptions explicitly.

### 5.6 Documentation and test counts

- `README.md`: new UI description, screenshots, `ashura-web` usage, API additions,
  corrected security/privacy statements, Playwright instructions.
- `research/decisions.md`: add the design-approval decision (next D-number after the
  current sequence) with the five-workspace and honest-state rationale.
- `research/experiment_log.md`: log Phase 1 audit and each implementation phase.
- `research/EXP-021_local_ui.md`: append the redesign verification record, browser
  matrix, axe results and residual limits.
- `open_problem.md`: update F-043/F-044/F-042/F-016 status only if the work changes
  them; the UI redesign does not close those research gaps. Add UI limitations
  (no encryption, no revocation, no GPU metrics, no tool traces, no persistent
  cancelled/failed history without a journal).
- Update the test count everywhere it is stated. Do not claim "all green" until the
  full suite and browser suite have run in CI.

---

## 6. File-by-file manifest

### Phase 2

| File | Change |
| --- | --- |
| `app/static/index.html` | Rewrite shell and Command Center markup; five workspace containers; dialogs. |
| `app/static/css/tokens.css` | Add (approved tokens). |
| `app/static/css/base.css` | Add. |
| `app/static/css/shell.css` | Add. |
| `app/static/css/command.css` | Add. |
| `app/static/js/theme-boot.js` | Add. |
| `app/static/js/api.js` | Add. |
| `app/static/js/store.js` | Add. |
| `app/static/js/format.js` | Add. |
| `app/static/js/components.js` | Add. |
| `app/static/js/views/command.js` | Add. |
| `app/static/js/app.js` | Rewrite. |
| `app/static/style.css` | Delete after cutover. |
| `app/static/app.js` | Delete after cutover. |
| `app/sessions.py` | Add optional `before`, `count_messages`; keep default 200. |
| `app/web.py` | Parse `limit`/`before`; keep old behavior without params. |
| `pyproject.toml` | Extend package data for `static/css/*`, `static/js/*`. |
| `tests/test_sessions.py` | Add pagination tests. |
| `tests/test_web.py` | Add route/auth/pagination/static/forbidden-copy tests. |

### Phase 3

| File | Change |
| --- | --- |
| `app/static/css/execution.css` | Add. |
| `app/static/css/knowledge.css` | Add. |
| `app/static/js/views/execution.js` | Add. |
| `app/static/js/views/knowledge.js` | Add. |
| `app/static/index.html` | Add workspace markup. |
| `app/static/js/store.js` | Add selection/cache state. |
| `app/static/js/app.js` | Add routes and workspace mount. |
| `app/static/js/components.js` | Add step/evidence/provenance components. |
| `app/web.py` | Add detail/conflicts/facts/operations handlers. |
| `app/worker.py` | Optional bounded journal + optional job metadata. |
| `learning/ama.py` | No writes; add helper SELECTs only if needed. |
| `tests/test_web.py` | New endpoint tests. |
| `tests/test_worker_durability.py` | Journal bounds/state tests (if approved). |

### Phase 4

| File | Change |
| --- | --- |
| `app/static/css/system.css` | Add. |
| `app/static/css/settings.css` | Add. |
| `app/static/js/views/system.js` | Add. |
| `app/static/js/views/settings.js` | Add. |
| `app/static/index.html` | Add workspace markup. |
| `app/static/js/app.js` | Add routes and probe/logout events. |
| `app/static/js/components.js` | Add meters/health/provenance rows. |
| `app/web.py` | Add status `system`/`storage`/`runtime`; probe handler. |
| `foundation/ollama_model.py` | Optional timeout params for `list_models`/`running_models`. |
| `tests/test_web.py` | Status/probe/auth/CSRF/rate tests. |
| `tests/test_ollama.py` | Timeout parameter tests. |

### Phase 5

| File | Change |
| --- | --- |
| `tests/browser/**` | Add fixture, scenario tests, axe asset, snapshots. |
| `.github/workflows/ci.yml` | Add the browser job. |
| `pyproject.toml` | Add `[browser]` extra. |
| `.gitignore` | Ignore `test-results/`, `playwright-report/`, diff artifacts. |
| `README.md` | Rewrite UI/API/test docs. |
| `research/decisions.md` | Add the design decision. |
| `research/experiment_log.md` | Add phase entries. |
| `research/EXP-021_local_ui.md` | Append verification results and limits. |
| `open_problem.md` | Update UI limitations and test evidence. |

---

## 7. Compatibility and constraints

- **API compatibility:** existing paths, methods, defaults, error codes and response
  fields stay valid. New fields/params are additive. `GET /api/sessions/<id>` without
  params still returns the latest 200 messages.
- **Security:** keep the loopback bind, Host/Origin checks, token/cookie auth, CSRF,
  rate limits, request IDs, strict CSP, `X-Frame-Options: DENY`, `nosniff`,
  `no-referrer`, body/upload/character limits, 300 s job timeout and 600 s stream
  deadline. No new write endpoints except logout (already exists) and the optional
  probe (POST, CSRF, no generation).
- **CSP:** no inline script/style attributes. External same-origin ES modules and
  stylesheets only. No CDN, no external font, no `unsafe-eval`, no `unsafe-inline`.
- **No new runtime dependencies.** `psutil` and `numpy` already exist; test-only
  Playwright/Pillow are in `[browser]`.
- **SQLite:** no schema migration for Phases 2–3. All controller/AMA access goes
  through `ControllerWorker`. Optional operation journal is in memory.
- **Model roles:** `tony:7b-gpa3` general/tool-use; `tony:7b` privacy;
  `tony:7b-agentic3` evaluated but unpromoted; `qwen3.5:2b` fallback only. The UI
  displays the configured model, it does not switch roles.
- **Platforms:** Python 3.11–3.13 on Windows and Ubuntu. No POSIX-only paths. Browser
  targets: current Edge/Chrome and Firefox; native `<dialog>`, ES modules and CSS
  grid are required. No IE.
- **Packaging:** `pip install -e .` and the installed `ashura-web` entry point must
  serve the new CSS/JS from `site-packages`. Update package data and test a wheel
  install if practical.
- **No user data deletion.** Preserve `Goal.txt.txt`, BrainSim docs/results,
  `config/module_costs.json`, `results/` and `ASHURA_v3.zip`.
- **Test contract:** do not weaken `tests/test_web.py`; add tests. Update README test
  counts only after the full run.

---

## 8. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Backend scope creep turns a UI project into an API rewrite. | High | Schedule/quality | Gate each additive endpoint; keep Phases 2–3 to the listed reads; no writes. |
| New endpoints expose sensitive paths or prompt text. | Medium | Privacy/security | Auth + rate limits; fixed paths; redact host userinfo; no arbitrary file paths; journal excludes prompts by default. |
| A model probe disturbs generation or the 2 GB GPU. | Medium | Reliability | Probe only when the worker is idle; 2 s timeout; rate limit; no generation; non-loopback warning. |
| System metrics differ across platforms. | Medium | Misleading UI | `null` for unavailable; label sampling basis; test on Windows/Ubuntu; no GPU value. |
| Verification still gets collapsed in one component. | Medium | Epistemic | Central `verificationState()` helper; tests for all three states; no `step.ok` derivation. |
| Playwright tests are flaky. | High | CI noise | Scripted model, fixed delays, locator waits (no `wait_for_function` under CSP), pinned container, screenshot masks, retries only for infrastructure. |
| Screenshot baselines drift across OS/fonts. | High | False regressions | Pinned Playwright container; fixed locale/timezone/DPR; mask dynamic data; review updates. |
| 320 px layout overflows. | Medium | Accessibility | Reflow tests; code blocks scroll internally; drawers; no fixed widths below breakpoints. |
| Accessibility regressions from dense panels. | Medium | Compliance | axe, keyboard tests, focus management, 200% zoom, manual NVDA pass. |
| Long-conversation pagination breaks ordering. | Low | Data loss/confusion | `id < before` query with the existing index; ascending order; tests at 250+ messages; export unchanged. |
| Old message metadata lacks `verification`. | Medium | Wrong badge | Legacy fallback label; never infer verified/failed. |
| Theme flash / CSP violation. | Medium | Polish/security | `theme-boot.js` external classic script; no inline styles; screenshot before/after. |
| Module split breaks installed package. | Medium | Production startup | Update package data; test `pip install` + `ashura-web`; static nested path test. |
| Logout is mistaken for server-side revocation. | Medium | Security | Explicit copy; no "sign out everywhere"; link to launch-token limits. |
| Deletion of old CSS/JS loses work. | Low | Recovery | Delete only after the new shell passes tests; git history preserves the old files. |

---

## 9. Rollout and rollback

1. Implement Phase 2 on a branch/worktree; keep the current console on `main`.
2. Run `python -m pytest -q` (315+), the manual smoke and a real `tony:7b-gpa3` turn.
3. Review the shell screenshots against the approved mockups; merge only after review.
4. Ship additive backend endpoints before the UI that uses them, or in the same
   commit, so the UI never calls a missing endpoint.
5. Rollback is a revert of the UI commit; additive status fields and read endpoints
   are inert for the old UI. No database migration to undo.
6. Keep the old UI files in git history; do not keep two live shells.

---

## 10. Approval checklist

- [ ] Phase 1 audit and design package accepted.
- [ ] Five-workspace architecture accepted.
- [ ] Honest-state rules accepted (verified/failed/unavailable; health/readiness;
  measured/unavailable).
- [ ] Token set, type scale and responsive behavior accepted.
- [ ] Session pagination additive API accepted.
- [ ] Phase 3 read-only evidence APIs accepted (memory detail, conflicts; facts and
  operations journal optional).
- [ ] Phase 4 status metrics and optional model probe accepted.
- [ ] Playwright browser CI and screenshot baselines accepted.
- [ ] Scope, risks and rollback accepted.

After approval, begin with Phase 2 only. Do not start Phase 3 until Phase 2's tests and
visual review pass.
