# ASHURA UI Audit — Phase 1

- **Scope:** the current local console (`app/static/index.html`, `app/static/style.css`,
  `app/static/app.js`) and the backend surfaces it renders (`app/web.py`,
  `app/sessions.py`, `app/worker.py`, `brain/controller.py`, `learning/ama.py`,
  `memory/schema.sql`, `config/ashura.ollama.toml`).
- **Method:** source-level audit, live browser smoke against the current console with a
  seeded demo database, API/capability mapping, and contrast checks of the proposed
  palette. No UI code has been changed.
- **Verdict:** the current console is a competent operator console. It is not yet the
  final ASHURA interface: it is chat-first, hides system state, conflates several
  epistemic states, and makes four claims the implementation does not support.

---

## 1. What the current interface is

| Area | Current implementation |
| --- | --- |
| Shell | 286 px session sidebar, central chat, 390 px right inspector; conventional top bar and composer. |
| Navigation | One view. Sessions are switched in the left sidebar; no workspaces or deep links. |
| Header | Model name, connection dot, chat title, Export, theme toggle, Inspector toggle. |
| Inspector | Trace / Memory / Status tabs. Trace is per message; Memory and Status are global tools in the same panel. |
| Conversation | User bubbles and assistant bubbles, inline trace summary, retry/copy per turn. |
| Sessions | New, filter, rename, export (Markdown only in the UI), delete. |
| Composer | Streaming send, Stop, OCR image upload. |
| Dialogs | Native `<dialog>` elements for unlock, rename, delete, shortcuts. |
| Themes | Dark and light only; system preference is read on first load, then the toggle stores `ashura-theme` in `localStorage`. |
| Security UX | Unlock-token dialog, but no logout control, session explanation or security workspace. |

Evidence: `app/static/index.html:1-237`, `app/static/style.css:1-707`,
`app/static/app.js:1-1609`.

### What should be preserved

- The authenticated, loopback-only server and all of its security restrictions.
- Persistent sessions, SSE token streaming, cooperative cancellation, retry,
  OCR, export, memory/status inspection and the single-writer `ControllerWorker`.
- The three verification states in the backend (`verified`, `failed`, `unavailable`).
- The existing restrained dark palette as a starting point; the redesign keeps the
  same calm intent but replaces blue/gradient chrome with a neutral graphite surface
  and one teal accent.
- The no-framework, no-CDN, stdlib-first delivery model. The redesign uses native
  ES modules and CSS, not a framework or a new runtime dependency.

---

## 2. Backend capability matrix

This is the authoritative boundary for the redesign. A UI surface is only allowed to
show a value if the row below says it is available.

| UI need | Current source | Available now? | Notes |
| --- | --- | --- | --- |
| Server liveness | `GET /api/health` (unauthenticated) | Yes | 200 means the HTTP process answers. It does **not** prove model readiness. |
| Version, uptime, model name | `/api/status` | Yes | `version`, `uptime_s`, `model`. |
| Config and database paths | `/api/status` | Yes | `config`, `database`, `sessions_db`. |
| Aggregate counts | `/api/status.counts` | Yes | `experiences`, `facts`, `conflicts_open`, `fts_rows`; cached on the worker. |
| Session count | `/api/status.sessions` | Yes | May be `null` if the read fails. |
| Worker state | `/api/status.worker` | Yes | Queue depth/max, active kind/id, submitted/completed/failed/cancelled/rejected, average wait/run, last job, `alive`. |
| CSRF token | `/api/status.csrf` | Yes | Used by cookie-authenticated mutating requests. |
| Capability flags | `/api/status.capabilities` | Yes | `streaming`, `sessions`, `ocr`, `memory`, `export`. |
| Session list/detail | `GET /api/sessions`, `GET /api/sessions/<id>` | Yes | Detail returns at most the latest **200** messages by default. |
| Full transcript | export endpoint | Yes | Export uses `limit=None`; the interactive transcript does not. |
| Chat (non-stream) | `POST /api/chat` | Yes | Waits for the worker job. |
| Chat (stream) | `POST /api/chat/stream` | Yes | SSE events: `meta`, `token`, `done`, `error`, `cancelled`. `meta` includes `session_id`, `job_id`, `model`, `queue_depth`. |
| Cancellation | `AbortController` + server cancel event | Yes | A cancelled turn persists the user message only. |
| Retry | client resends the last user text | Yes | No dedicated endpoint; the UI controls it. |
| OCR | `POST /api/ocr` | Yes | Synchronous JSON; max 16 MB request, 12 MB image; cannot be cancelled after submission. |
| Trace | message `meta.trace` | Yes | Persisted after the turn completes. Routing, routing/total ms, steps (module, input ≤300 chars, output ≤800 chars, ms, ok, note, verification). |
| Verification | message `meta.verified`, `meta.verification` | Yes | Tri-state value is stored; the current UI collapses it (see §4). |
| Admission decision | message `meta.admission` | Yes | Exact string from AMA, including combinations such as `"ADMITTED / MERGED"`. |
| Attribution / correction | message metadata | Yes | Present when the controller produces them. |
| Memory search/list | `GET /api/memory?q=&limit=` | Yes | Item fields: `id`, `input`, `output`, `category`, `status`, `method`, `reliability`, `label`, `conflict`, `ts`. |
| Memory provenance detail | DB has `source`, `related_ids`, `outcome`, `repeat_count`, `content_hash` | **No API** | `source` and `related_ids` are not returned by the list/search endpoint. |
| Conflict records | `AMA.conflicts()` exists; `conflicts` table has question, new/old ids, statuses, reliabilities, policy, resolution | **No API** | The UI only receives a boolean `conflict`. |
| Admission log | `admission_log` table (decision, score, features JSON, reason) | **No API** | `AMA.admit` writes it; no read endpoint. |
| Semantic facts | `facts` table with provenance, source_exp_id, derivation | **Count only** | No fact list/detail endpoint. |
| System CPU/RAM/disk | `psutil` is a project dependency; `brain/router.py` has real helpers | **Not wired** | No fields in `/api/status`. |
| Process RSS / thread counts | `psutil.Process()` | **Not wired** | No fields in `/api/status`. |
| Storage file sizes | `Path.stat()` on configured DBs; `AMA.storage_report()` for payload bytes | **Not exposed** | Paths are exposed, sizes are not. |
| Model backend/host/context/digest | `ModelConfig` and `OllamaModel.cfg` | **Not exposed** | `model` is only the display name. |
| Last inference stats | `OllamaModel.last_stats` (`eval_count`, durations) | **Not exposed** | Real values exist after a generation. |
| Model readiness probe | `foundation.ollama_model.list_models()` / `running_models()` | **No API / no UI** | A probe is not the same as `/api/status` success. |
| GPU memory | none | **No** | Do not display a value. |
| Logout | `POST /api/logout` | Yes | Clears the cookie; does not rotate the launch token. |
| Server-side session revocation | none | **No** | Logging out one browser does not revoke other copies of the token. |
| Multi-user accounts/roles | none | **No** | Single launch token. |
| Encryption at rest | none | **No** | SQLite files are plaintext. |
| External tool calls / agent loop | none | **No** | Trace steps are cognitive modules, not tool invocations. |

---

## 3. Unsupported or misleading claims in the current UI

| # | Claim / behavior | Location | Reality | Severity | Required action |
| --- | --- | --- | --- | --- | --- |
| 1 | "local model · encrypted at rest by your OS" | `index.html:30` | ASHURA writes plaintext SQLite. OS disk encryption may or may not be enabled; the app cannot assert it. | High | Remove "encrypted". Settings states "plaintext SQLite; OS permissions/disk encryption are outside this application". |
| 2 | "localhost only · no external API" | `index.html:58` | The web server refuses a non-loopback bind (`app/web.py:1075`), so the UI is loopback-only. But the Ollama `host` is configurable and is not validated as loopback (`foundation/model_config.py:25`). "No external API" is true only in the sense that ASHURA does not call third-party LLM APIs. | Medium | Keep "UI bound to loopback"; show the configured model endpoint and whether it is loopback. Say "no third-party LLM API", not "no network". |
| 3 | "Nothing leaves this machine" | `index.html:85` | True only when the configured model endpoint is loopback. A remote Ollama host would receive prompts. | High | Replace with conditional copy driven by the configured host. |
| 4 | "local · online" | `app.js:234,272` | Set when `/api/status` succeeds. Status success proves the web process answered, not that Ollama is reachable or that the model is loaded. | High | Separate **server health**, **worker readiness** and **model readiness**. Show "not probed" until a real probe runs. |
| 5 | Every non-verified response is labelled "unverified" | `app.js:691-693` | `verified === false` can mean the verifier ran and **failed**, or that no verifier applied (`unavailable`). The backend stores the distinction. | Medium | Render three states with different labels, tones and explanations. |
| 6 | Trace summary shows "unverified" for both failure and unavailability | `app.js:1113` | Same conflation as #5. | Medium | Use `payload.verification` first; `verified` alone is not enough. |
| 7 | A verification step with `ok: true` can render as a green success | trace rendering | `brain/controller.py:227` sets `ok = verification is not FAILED`, so an **unavailable** verifier step is `ok: true`. | Medium | The verification badge must be derived from `step.verification`, not `step.ok`. "Unavailable" is neutral, not success. |
| 8 | The right inspector mixes a per-turn trace with global Memory and Status tools | current inspector tabs | Trace is message-scoped; Memory search and Status are application-scoped. The shared panel implies they describe the selected turn. | Medium | Command Center inspector is turn-scoped. Memory moves to Knowledge Studio; status moves to System Monitor. |
| 9 | Trace appears to be a live per-step feed | conversation trace summary | The SSE protocol has no step events. The trace is stored in the final `done` payload. | Low | Say "Trace recorded after completion". Do not animate module steps as if they were live. |
| 10 | "Markdown · JSON" export | prototype footer; current UI only Markdown | The API supports both formats; the current UI exposes only Markdown. | Low | Implement both formats or show only Markdown until the control exists. |
| 11 | "Inspector" implies evidence for the selected answer | top bar button | The current panel is always available and has global tabs; it is not tied to selection. | Low | Make the turn inspector explicitly selected-turn scoped, with an empty state when no turn is selected. |
| 12 | "Streaming local answers with a measured trace" | chat subtitle | The trace is measured and persisted, but it is not streamed. "Local" is conditional on the model endpoint. | Low | Keep "measured trace"; make "local" conditional on the endpoint. |

---

## 4. Semantic defects to fix in the redesign

### 4.1 Verification

The backend exposes a strict three-state value (`brain/verification.py:12-15`):
`verified`, `failed`, `unavailable`. `verified` is only true when the response text is
the exact arithmetic result, an arithmetic value exists, the language module did not
write the answer, and the text equals the exact value.

The UI must render:

| Backend state | Label | Tone | Explanation |
| --- | --- | --- | --- |
| `verified` | Verified | success | An independent check ran and agreed. |
| `failed` | Verification failed | danger | A check ran and disagreed. This is not the same as "unverified". |
| `unavailable` | No independent verifier | warning/neutral | No applicable verifier ran. Model-written text remains an assertion. |
| missing on a legacy record | Unverified (legacy record) | neutral | The record predates the tri-state field; do not infer success. |

Never derive verification from `step.ok`. The verification step can be `ok: true`
while the verifier is unavailable.

### 4.2 Operations

The backend distinguishes requested, running, completed, failed and cancelled at the
worker/SSE level. Persisted transcripts only contain completed assistant turns; a
failed or cancelled turn normally leaves only the user message. The redesign must not
backfill a fake operation history. Options:

- show live operations in Execution Studio while they exist in this browser process;
- show persisted completed turns as recorded traces;
- if persistent failed/cancelled history is required, add an **in-memory bounded
  operation journal** in `ControllerWorker` (process lifetime only) or a separate
  approved journal table. Do not claim durability for the in-memory variant.

### 4.3 Memory and knowledge

- `reliability` is an evidence class in `[0,1]`, not a probability that a claim is
  true. The UI may show `0.60` with the label "evidence score", never "60% confident".
- `verification_method` is the recorded explanation. Show it verbatim.
- `conflict` is currently a boolean. A conflict badge is honest; a conflict narrative
  is not until `/api/conflicts` and `/api/memory/<id>` exist.
- `admission` is an exact string (`ADMITTED`, `MERGED`, `DISCARDED`,
  `REVIEW_REQUIRED`, possibly combined). Show the exact value and, once exposed, the
  decision score/features/reason from `admission_log`.
- The semantic fact count is real, but fact-level provenance is not exposed. Do not
  render a fake fact table.

### 4.4 System state

- `/api/status` success = the web process answered. It is **health**, not readiness.
- Worker `alive: true` = the single-writer thread is running. It says nothing about
  the model or the database being ready for a specific request.
- Model readiness must be "not probed" until a real probe (e.g. Ollama `/api/ps` or
  `/api/tags`) returns. A configured value is not a readiness result.
- CPU, RAM, disk, process RSS, storage sizes and last-inference statistics are not in
  the API today. Until approved additive fields exist, show "not available", not
  `0`, and never animate a synthetic meter.

---

## 5. Accessibility and responsive audit

### Confirmed issues

| Issue | Evidence | Impact |
| --- | --- | --- |
| The entire chat region is `aria-live="polite"` | `index.html:81` | Screen readers may announce every streamed token, making a response unusable. |
| No skip link | `index.html` | Keyboard users must traverse the sidebar and header on every load. |
| No workspace-level focus management | one-view app | After opening a drawer or switching context, focus can remain behind the overlay. |
| Global and turn-scoped tools share one inspector | `index.html` inspector | The relationship between the selected message and the evidence is unclear. |
| Dense 10–11 px metadata with low-contrast muted text | `style.css` | Some labels are hard to read at 100% and at 200% zoom. |
| Theme is dark/light only; system is first-load only | `app.js:1355-1363,1592-1593` | Users cannot follow the OS after the first choice. |
| Status relies on color in places | connection dot/pills | Color-blind users may miss state changes; text labels exist in some but not all places. |
| Mobile inspector/session drawers have no consistent focus trap or return focus | current CSS/JS | Keyboard and screen-reader users can tab into hidden content. |
| Current browser checks are manual smoke tests | no Playwright in CI | Regressions in layout, keyboard behavior and auth are not caught. |

### Responsive observations

- The current CSS switches the inspector to a drawer at 1180 px and the session
  sidebar at 860 px; the exact breakpoints are implemented in both CSS and JS
  (`app.js:108,112`), which risks drift.
- At 320–390 px the composer, top bar and long code blocks are the critical overflow
  risks. The current app has no automated width matrix.
- Long conversations are capped at 200 messages in the interactive API
  (`app/sessions.py:115`), while export returns all messages. There is no "load
  earlier" affordance or explanation.

---

## 6. Test coverage gaps

Current CI runs 6 ASHURA jobs (Ubuntu/Windows × Python 3.11/3.12/3.13) and 2 BrainSim
jobs. All 315 ASHURA tests pass locally. There are 24 web tests covering auth, CSRF,
SSE, cancellation, sessions, OCR, export and worker behavior, but:

- no real browser runs in CI;
- no visual regression baselines;
- no keyboard/focus/ARIA assertions;
- no responsive matrix at 320/375/430/768/1024/1440/1920;
- no end-to-end login/logout, streaming/cancel/retry, reload persistence, upload,
  long-conversation, code-rendering or theme tests;
- no test that the UI never labels an unavailable verifier as verified;
- no test that absent metrics render as unavailable rather than zero.

The Phase 5 plan adds a separate Playwright job without weakening `tests/test_web.py`.

---

## 7. Design implications

1. **Workbench first, chat second.** The five workspaces answer five different
   questions: what am I working on; what did the system actually execute; what does it
   know and how strongly; is the runtime healthy; what are the access and privacy
   boundaries.
2. **Evidence on demand.** The default Command Center shows the answer, a compact
   verification state and one trace link. Full routing, module I/O and identifiers
   live in the turn inspector and Execution Studio.
3. **One vocabulary for state.** The same verified/failed/unavailable and
   running/completed/failed/cancelled semantics appear in every workspace.
4. **No synthetic instrumentation.** Every meter, count and badge maps to a real field
   or shows "not available".
5. **The redesign is additive at the API boundary.** The existing endpoints and
   security model stay; new read-only fields/endpoints must be approved before they
   are used.
6. **The current console stays production until the design is approved and the new
   shell passes the same security, streaming and persistence tests.**

---

## 8. Phase 1 conclusion

The current console has a solid backend and a usable chat surface. The redesign is
justified by four gaps that cannot be fixed with cosmetic CSS: the missing system
state, the missing knowledge/evidence workspace, the collapsed verification
semantics, and the unsupported privacy/encryption claims. The revised workbench keeps
the proven backend and replaces the chat-first shell with a state-first shell.
