# ASHURA Workbench — Revised Architecture and Design Specification

Status: **proposal for approval**. This document defines the target interface. It
does not claim that every target-state control is implemented today; §3 marks the
items that require an approved additive read-only API.

---

## 1. Design intent

ASHURA is an intelligent engineering workbench, not a chat app with an inspector.
The interface answers five questions, one per workspace:

1. **Command Center** — what am I working on, and what did the last turn produce?
2. **Execution Studio** — what did the system actually execute, in what order, with
   which evidence and which verification result?
3. **Knowledge Studio** — what does ASHURA remember, where did it come from, how
   strong is the evidence, and what conflicts or admission decisions exist?
4. **System Monitor** — is the local runtime healthy and ready, and what are the real
   resource and storage measurements?
5. **Settings & Security** — what can I change, what is stored, how do I sign out,
   and what does this build explicitly not support?

The visual language is calm and technical: graphite/neutral surfaces, one restrained
teal accent, clear type hierarchy, subtle depth, no decorative gradients, no
glassmorphism, no fake "AI thinking" animation and no invented metrics.

---

## 2. Information architecture

| Workspace | Primary question | Default layout | Primary real data |
| --- | --- | --- | --- |
| Command Center | What am I working on? | Sessions · conversation · turn inspector | `/api/sessions`, `/api/sessions/<id>`, SSE chat, message `meta` |
| Execution Studio | What actually ran? | Live strip · operations · module timeline · evidence | message `meta.trace`, `meta.verification`, `meta.admission`, worker stats |
| Knowledge Studio | What is known, and how well? | Summary · memory list · memory detail | `/api/memory`, counts, and (Phase 3) memory detail/conflicts/facts |
| System Monitor | Is it healthy and ready? | Health strip · resources · worker · model · storage | `/api/status` and (Phase 3/4) measured system fields |
| Settings & Security | What are my controls and boundaries? | Appearance · session/security · runtime · privacy · limits | `/api/status`, `/api/logout`, configuration; no new write API |

Navigation is a persistent 76 px icon rail on desktop, with text labels and
`aria-current="page"`. On mobile it becomes a modal drawer. Workspace order:
**Command · Execute · Knowledge · System · Settings**.

### 2.1 Client routes

Use hash routes so reloads and browser history preserve context without adding server
routes:

- `#/command` and `#/command/<session-id>`
- `#/execution/<message-id>`
- `#/knowledge/<experience-id>`
- `#/system`
- `#/settings`

Validate every id against the loaded data. An unknown id renders the workspace's
empty state with a short explanation; it never fabricates a record.

### 2.2 Keyboard model

| Shortcut | Action |
| --- | --- |
| `Alt+1…5` | Switch workspace (avoid `Ctrl+1…5`, which browsers reserve for tabs). |
| `Ctrl+K` | Open the command palette: workspace commands and the loaded session list only. |
| `Ctrl+O` | New task in Command Center. |
| `/` | Focus the active search field when focus is not in a text control. |
| `Esc` | Close the palette/drawer/dialog and restore focus. |
| `Enter` / `Shift+Enter` | Send / newline in the composer. |
| `?` | Open the shortcuts dialog when focus is not in a text control. |

All shortcuts are discoverable in Settings → Keyboard and in the shortcuts dialog.
Single-character shortcuts never fire while the user is typing.

---

## 3. Application shell

```
┌──────┬───────────────────────────────────────────────────────────────┐
│ rail │ topbar: workspace / context · search · runtime · theme · menu │
│      ├───────────────────────────────────────────────────────────────┤
│      │ workspace                                                     │
│      │                                                               │
│      ├───────────────────────────────────────────────────────────────┤
│      │ statusbar: health · endpoint · model · worker · last · version│
└──────┴───────────────────────────────────────────────────────────────┘
```

- **Rail:** brand mark, five workspace buttons, loopback lock indicator, version.
  The lock is labeled "UI bound to loopback"; it is not an encryption claim.
- **Topbar:** breadcrumb (`Workspace / context`), command-palette trigger, runtime
  chip (health dot + model + worker queue), theme control, account/settings entry.
  The chip must not use a green dot to imply model readiness; see §9.
- **Statusbar:** compact, real values: server health, bind endpoint, configured model,
  worker state/queue, last job duration, version. Hidden below 760 px; the same
  values remain in System Monitor and Settings.
- **Main:** one active workspace; hidden workspaces stay mounted only if their state
  must survive (filters, scroll, selection). Do not re-fetch everything on every tab
  switch.
- **Scrim:** one shared modal scrim for all mobile drawers.
- **Toast:** one polite live region for save/export/logout confirmations; errors also
  appear inline and are not toast-only.

### 3.1 Target-state controls requiring additive API

The prototype shows these as the intended design. They must not ship until the
read-only API in the implementation plan is approved and tested:

- system CPU/RAM/disk/RSS/storage-size metrics;
- configured model backend/host/context/digest and last-inference stats;
- model readiness probe;
- memory detail (`source`, `related_ids`, admission log);
- conflict records and conflict detail;
- fact-level provenance (if a Facts view is added);
- persistent or in-memory operation history for failed/cancelled jobs.

Everything else uses fields that exist today.

---

## 4. Command Center

Three panes on desktop:

- **Sessions (272 px):** new task, filter, grouped list (Today / Earlier), per-row
  title, message count and relative time; footer shows the session store name and the
  available export formats. Rename/delete remain in a row menu.
- **Conversation (fluid, max 840 px):** a session header (title, message count,
  started time, model), then turns.
- **Turn inspector (344 px):** selected-turn evidence. Tabs: **Summary · Trace ·
  Memory**. On widths below 1180 px it becomes a drawer with a visible close button.

### 4.1 A turn

- User turn: author, timestamp, request card, copy action.
- Assistant turn: author, timestamp, verification chip, response body, metadata row
  (model, admission, step count, verification state), trace line ("Trace recorded ·
  routing · total"), and actions (Copy, Retry).
- Verification appears once as a chip beside the author and, when expanded, as a
  full explanation in the inspector. Do not repeat "unverified" in three places.
- The trace line is a link to Execution Studio with the message selected.
- Streaming: a single caret while tokens arrive; the transcript is `aria-busy` and a
  separate status region announces start/end. Do not put `aria-live` on the whole
  transcript.
- Cancelled turn: show a neutral inline row "Cancelled — no answer was stored". It is
  local state and disappears after reload, matching the persistence rule.
- Failed turn: show the error inline with a Retry action; the user turn remains.
- Retry creates a new turn (the backend has no replace endpoint). The action tooltip
  says "Retry as a new turn".

### 4.2 Composer

- Textarea, OCR image action, attach (only if a real attachment path exists; otherwise
  omit), send/stop.
- `Enter` sends, `Shift+Enter` inserts a newline; IME composition is respected.
- Character counter appears near the 16,000-character limit and the submit button
  disables with an inline explanation at the limit.
- Stop is available only for an active chat stream. OCR is synchronous and is not
  presented as cancellable.
- The model chip shows the configured model name and a neutral worker state; it does
  not claim readiness.
- Drag-and-drop image upload reuses the same OCR path and shows the same limits.

### 4.3 Turn inspector

- Empty state: "Select a turn to inspect its execution evidence."
- Summary: verification explanation, turn facts (state, total/routing time, model,
  admission), compact two-step execution preview, record ids, trace link.
- Trace: full routing selected/skipped, module steps, input/output disclosure, notes.
- Memory: records relevant to this turn **when the API exposes them**; until then,
  show a link to Knowledge Studio and no fabricated list.
- IDs: message id and session id are real; job id is available live from SSE `meta`
  and is not persisted in the transcript. Mark it "live only" or "not persisted".

---

## 5. Execution Studio

The workspace is an evidence reader, not a live debugger pretending to be one.

- **Page head:** title, short explanation, state legend, Refresh, and an Operations
  button on mobile.
- **Live strip (4 cells):** worker state (`idle`/`active kind`), queue `n / max`,
  last operation (kind · state · run time), error count since start. All from
  `worker.stats()`.
- **Operations list (292 px):** recorded turns with a trace (completed), plus live
  operations for this browser/process when available. A failed/cancelled row may only
  appear from the live journal; it must be labelled "since server start" or "this
  browser session". Do not imply durable history without an approved journal.
- **Module timeline:** operation header, summary cells (total, routing, model, message),
  selected/skipped routing chips, then one card per recorded step.
- **Evidence panel (344 px):** verdict (verified/failed/unavailable with explanation),
  verification method, response check, verifier-ran flag, memory admission (exact
  decision + score/features/reason when exposed), identifiers, raw record disclosure.
  Below 1180 px it becomes a drawer.
- **Trace note:** "Steps are persisted after the turn completes. This build does not
  stream per-step events. Trace steps are cognitive modules; there is no external
  tool-call layer."

Verification rendering inside a step:

| Step field | Badge | Tone |
| --- | --- | --- |
| `verification: "verified"` | verified | success |
| `verification: "failed"` | failed | danger |
| `verification: "unavailable"` | not run | neutral |
| absent | — | do not infer from `ok` |

The step's `ok` flag describes the module completing, not the truth of the answer.

---

## 6. Knowledge Studio

- **Summary strip (4 cells):** experiences, verified facts, open conflicts, FTS rows.
  These are the real `/api/status.counts` values. When a value is `null`, show "not
  available".
- **Toolbar:** FTS search (debounced), tabs **Experiences · Conflicts · Admissions**.
  The Conflicts tab count is the real open-conflict count.
- **List (370 px):** status badge, evidence score, question, answer excerpt, timestamp,
  conflict flag. The list displays `label`/`status`, `method`, `reliability` and `ts`
  exactly as returned. Below 760 px it is a drawer.
- **Detail:** stored answer; provenance grid (source, status, method, recorded time);
  reliability row with the exact score and the sentence "Reliability is the stored
  evidence class, not a probability that the claim is true."; admission decision
  (exact decision string; score/features/reason when exposed); open conflict (new/old
  claims, statuses, scores, policy, resolution); related record ids; copy id / use as
  prompt.
- A conflict is never "resolved" by reliability in the UI. Resolution remains an
  explicit CLI action (`learning.review resolve`) or a future approved human action.
  The UI may show the exact command, not a fake Resolve button.
- A verified fact is not shown as "true"; it is shown as independently verified with
  its method and source.
- Search results always show provenance labels, including unverified experiences.
  The backend intentionally retrieves with `min_reliability=0.0` and
  `include_unverified=True`.

### 6.1 Phase 3 additive reads

To make the detail view fully real, add:

- `GET /api/memory/<id>` — full experience (`source`, `related_ids`, `outcome`,
  `repeat_count`, `content_hash`), latest admission decision, linked conflict ids.
- `GET /api/conflicts?open_only=1&limit=50` — conflict rows from `AMA.conflicts()`.
- `GET /api/facts?limit=50` — optional fact list with `text`, `source_exp_id`,
  `reliability`, `verification_method`, `provenance`, `derivation`, `ts`.
- `GET /api/operations?limit=50` — optional in-memory worker journal, process lifetime
  only, no prompts by default (kind/id/state/timings/error/session/message ids).

All DB reads go through `ControllerWorker`; do not touch the controller's SQLite
connection from the HTTP thread.

---

## 7. System Monitor

- **Health strip (4 cells):** Health · server (the HTTP process answers), Readiness ·
  worker (thread alive), Readiness · model (probed / not probed / unreachable),
  Health · storage (configured files readable). Health and readiness are separate
  words on purpose.
- **Resources:** CPU (system-wide, sampled since the previous sample), memory used /
  total, process RSS, disk free on the memory-DB volume, GPU memory (only if a real
  source exists; otherwise "not exposed by this runtime"), last inference duration from
  real model stats.
- **Worker:** counters, queue, average wait/run, last job detail, thread liveness.
- **Model:** configured model, backend, endpoint, context, digest (truncated), residency
  (probed / not probed). A probe button only exists once a real probe endpoint exists.
  Until then the panel says "not probed" and "probe not implemented in this build".
- **Storage:** file paths, real file sizes, free disk. State plainly: "Both databases
  are plaintext SQLite. ASHURA does not encrypt them; file-system permissions and OS
  disk encryption are outside this application."
- **Runtime facts:** version, uptime, sessions, experiences, open conflicts.
- **Freshness:** every measured value carries a `sampled_at` or is described as a
  process-lifetime counter. A missing metric is `—` plus "not available", never `0`.
- **Endpoint visibility:** show whether the model endpoint is loopback. If it is not,
  display a warning that prompts are sent to that endpoint and that "nothing leaves
  this machine" would be false.

---

## 8. Settings & Security

Sections, in order:

1. **Appearance** — system / dark / light, stored only in this browser. The system
   option follows `prefers-color-scheme` live. Reduced motion follows the OS; no
   separate override unless one is implemented.
2. **Session & security** — signed-in state, cookie attributes (HttpOnly,
   SameSite=Strict, 7-day Max-Age), CSRF requirement, logout. Copy is explicit:
   "Logging out clears this browser's cookie. The launch token is not rotated and
   other browsers holding the token are not revoked."
3. **Runtime** — read-only model, backend, endpoint, context, digest, config file,
   worker queue limit; changes require editing the config and restarting. No model
   download or weight management in the UI.
4. **Privacy & storage** — local UI bind; conditional model-endpoint statement; no
   telemetry/CDN; access logs exclude message content; OCR temp-file lifecycle and
   limits; plaintext SQLite; no encryption claim.
5. **Security posture** — loopback bind, launch token, HttpOnly/Strict cookie, CSRF,
   plain HTTP, no multi-user, no server-side revocation, no TLS. Mark the gaps as
   gaps.
6. **Keyboard** — shortcut reference, including workspace shortcuts and the command
   palette.
7. **Known limits** — encryption at rest, server-side session revocation, multi-user
   accounts/roles, TLS termination, tool-call traces, GPU metrics, persistent
   failed/cancelled operation history unless the journal is approved.

Logout is a real action: `POST /api/logout` with CSRF, clear in-memory state, close
the SSE stream, then show the unlock dialog. It is not a fake "sign out" link.

---

## 9. State semantics

### 9.1 Verification

| State | Label | Tone | Meaning |
| --- | --- | --- | --- |
| `verified` | Verified | success | Independent check ran and agreed. |
| `failed` | Verification failed | danger | A check ran and disagreed. |
| `unavailable` | No independent verifier | warning/neutral | No applicable check ran. |
| missing (legacy) | Unverified (legacy record) | neutral | Do not infer success or failure. |

Computation order: use `meta.verification` when present; otherwise use
`meta.verified === true` for verified; otherwise legacy. Never use `step.ok` as the
verification state.

### 9.2 Operations

| State | Source | UI |
| --- | --- | --- |
| requested | client submit | neutral "Requested" |
| running | SSE `meta` received / first token | accent "Running" |
| completed | SSE `done` / persisted assistant turn | success "Completed" |
| failed | SSE `error` / live journal | danger "Failed" + inline error |
| cancelled | SSE `cancelled` / Stop / live journal | neutral "Cancelled" |
| verified / unverified | verification semantics above | separate from operation state |

Operation state and verification state are orthogonal. A completed operation can be
unverified; a failed operation is not "unverified" (it produced no verified answer).

### 9.3 Evidence and admission

- Show the exact `status`, `method` and `reliability` values.
- Label reliability as an evidence score, not confidence or probability.
- Show the exact admission string; append score/features/reason only if the API
  exposes `admission_log`.
- Show timestamps with date, time and timezone. Relative times are secondary.
- A conflict badge means "a conflict row references this record"; the narrative
  requires the conflict endpoint.
- Never color-code a record as "good" solely because it is verified; verified
  arithmetic is not a general truth claim.

### 9.4 Health and readiness

- **Health** = the process/file/thread answers.
- **Readiness** = the specific subsystem can accept the intended work now.
- `/api/status` success is health, not model readiness.
- `worker.alive` is worker readiness, not model readiness.
- Model readiness is `unknown` until a probe. A configured model is not ready by
  definition.
- Missing measurements are `null`/absent, rendered as "not available".

---

## 10. Component hierarchy

```
AppShell
├─ SkipLink
├─ WorkspaceRail
│  ├─ BrandMark
│  ├─ WorkspaceButton × 5
│  └─ LoopbackBadge / Version
├─ Topbar
│  ├─ Breadcrumb
│  ├─ CommandPaletteTrigger
│  ├─ RuntimeChip
│  ├─ ThemeControl
│  └─ AccountMenu
├─ WorkspaceHost
│  ├─ CommandCenter
│  │  ├─ SessionPane
│  │  │  ├─ NewTaskButton
│  │  │  ├─ SessionFilter
│  │  │  └─ SessionList → SessionRow
│  │  ├─ ConversationPane
│  │  │  ├─ ConversationHeader
│  │  │  ├─ TurnList
│  │  │  │  └─ Turn
│  │  │  │     ├─ RequestCard
│  │  │  │     ├─ ResponseBody → Markdown/CodeBlock
│  │  │  │     ├─ VerificationChip
│  │  │  │     ├─ TurnMeta
│  │  │  │     └─ TurnActions
│  │  │  └─ Composer
│  │  │     ├─ OcrAction
│  │  │     ├─ SendButton / StopButton
│  │  │     └─ ModelChip
│  │  └─ TurnInspector (dialog drawer < 1180)
│  │     ├─ VerdictCallout
│  │     ├─ TurnFacts
│  │     ├─ MiniTimeline
│  │     ├─ RecordIds
│  │     └─ TraceLink
│  ├─ ExecutionStudio
│  │  ├─ PageHead + StateLegend
│  │  ├─ LiveStrip
│  │  ├─ OperationList → OperationRow
│  │  ├─ TraceTimeline → StepCard
│  │  └─ EvidencePanel (dialog drawer < 1180)
│  ├─ KnowledgeStudio
│  │  ├─ PageHead
│  │  ├─ SummaryStrip
│  │  ├─ MemoryListPanel (dialog drawer < 760)
│  │  │  ├─ MemorySearch
│  │  │  ├─ KnowledgeTabs
│  │  │  └─ MemoryRow
│  │  └─ MemoryDetail
│  │     ├─ ProvenanceGrid
│  │     ├─ ReliabilityRow
│  │     ├─ AdmissionCard
│  │     └─ ConflictCard
│  ├─ SystemMonitor
│  │  ├─ HealthStrip
│  │  ├─ ResourcePanel
│  │  ├─ WorkerPanel
│  │  ├─ ModelPanel
│  │  └─ StoragePanel
│  └─ SettingsSecurity
│     ├─ AppearanceSection
│     ├─ SessionSecuritySection
│     ├─ RuntimeSection
│     ├─ PrivacyStorageSection
│     └─ LimitsSection
├─ CommandPalette (dialog)
├─ ShortcutsDialog
├─ ConfirmDialog
└─ StatusBar
```

Every component reads from one store; no component invents a value. A presentational
component receives a concrete value plus its provenance/state, not a boolean named
`ok`.

---

## 11. Design tokens

The source of truth is [`mockups/tokens.css`](mockups/tokens.css). The production
implementation copies these values into `app/static/css/tokens.css`; it does not link
the mockup file.

### 11.1 Color

| Token | Dark | Light | Use |
| --- | --- | --- | --- |
| `--canvas` | `#0a0c0f` | `#f3f4f1` | app background |
| `--surface-1` | `#0f1216` | `#ffffff` | panels, topbar, cards |
| `--surface-2` | `#13171c` | `#fafbf9` | inset controls, hover |
| `--surface-3` | `#191e24` | `#f0f2ef` | selected rows, strong fills |
| `--border` | `#252b33` | `#dce0db` | decorative separators |
| `--control-border` | `#596675` | `#8f978f` | form/control boundaries (3:1) |
| `--text` | `#e7eaed` | `#171b18` | primary text |
| `--text-secondary` | `#9ca5b0` | `#59625c` | body secondary |
| `--text-tertiary` | `#7c8796` | `#66706a` | metadata |
| `--accent` | `#74c7b8` | `#176b5e` | primary accent |
| `--accent-ink` | `#07110f` | `#ffffff` | text on accent |
| `--success` | `#7ad3a7` | `#1d7a57` | verified/completed |
| `--warning` | `#e0b86a` | `#8a5a00` | unavailable/review |
| `--danger` | `#f08a7e` | `#b53a32` | failed/cancelled? (cancelled is neutral) |
| `--info` | `#8fb5dc` | `#2c5f8a` | running/informational |

Contrast results against the primary surface:

| Pair | Ratio |
| --- | --- |
| dark primary / surface-1 | 15.6:1 |
| dark secondary / surface-1 | 7.5:1 |
| dark tertiary / surface-1 | 5.2:1 |
| dark accent / surface-1 | 9.5:1 |
| dark accent-ink / accent | 9.7:1 |
| light primary / white | 17.4:1 |
| light secondary / white | 6.3:1 |
| light tertiary / white | 5.1:1 |
| light accent / white | 6.4:1 |
| light white / accent | 6.4:1 |

Status text pairs are 5.3–10.5:1. Decorative borders are below 3:1 on purpose;
interactive boundaries use `--control-border` (3.0–3.2:1) and focus rings use
`--focus` (6.4–13.1:1). Color is never the only carrier of state; every state also
has a text label and, where useful, an icon.

### 11.2 Type

- UI: Segoe UI Variable Text / Segoe UI / system sans.
- Display: Segoe UI Variable Display / Segoe UI.
- Mono: Cascadia Code / Cascadia Mono / Consolas / ui-monospace.
- Scale: 11, 12, 13, 14, 16, 20, 24, 30 px.
- Body: 13 px / 1.55; conversation text 13 px; assistant prose max-width 840 px.
- UI labels: 11–12 px medium; uppercase micro-labels 9–10 px with 0.06–0.1em tracking.
  Micro-labels are secondary metadata; essential information is never only in a
  9 px label.
- Code: 11–12 px / 1.6 mono.
- Tabular numbers for timings, counters, scores and byte sizes.

### 11.3 Space, shape and motion

- 4 px spacing base; common steps 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- Radii: 3 (chips), 5 (controls), 7 (rows/inputs), 10 (panels), 13 (composer/dialog).
- Control heights: 32 px desktop, 38 px large, 44 px touch.
- Layout: rail 76, session 272, context 344, topbar 56, statusbar 30,
  conversation max 840.
- Motion: 120 ms fast, 180 ms base, 240 ms slow; ease-out for drawers, standard for
  state changes. No looping decorative animation. Streaming caret only.
- `prefers-reduced-motion: reduce` removes transitions/animations except the streaming
  caret's opacity change, which becomes static or hidden.

### 11.4 Elevation

- `--shadow-1`: subtle panel/menu lift; `--shadow-2`: drawer/dialog. In light mode the
  shadows are softer. Avoid glow, glass and large gradients.
- Depth also comes from surface contrast and 1 px borders, not from shadow alone.

---

## 12. Responsive behavior

Test widths: **320, 375, 430, 768, 1024, 1440, 1920**.

| Range | Shell | Command | Execution | Knowledge | System / Settings |
| --- | --- | --- | --- | --- | --- |
| ≥ 1440 | rail 76, statusbar | 272 / fluid / 344 | 292 / fluid / 344 | 370 / fluid | two columns, max 1240/1120 |
| 1180–1439 | rail 76 | 256 / fluid / 318 | 270 / fluid / 318 | 340 / fluid | two columns |
| 900–1179 | rail 72 | inspector drawer | evidence drawer | 340 / fluid | two columns → single |
| 760–899 | rail 64 | session 244, inspector drawer | operations + evidence drawers | list 310 + detail | single column |
| 320–759 | rail drawer, topbar 52, statusbar hidden | single conversation; sessions + inspector drawers | timeline + operations/evidence drawers | detail + memory-list drawer | single column |

Requirements:

- No horizontal page scroll at any width. Code blocks scroll within their own box.
- The composer stays visible above the safe area; the conversation scrolls behind it.
- Primary touch controls are ≥ 44×44 px on ≤ 760 px; compact desktop controls are
  ≥ 24×24 px (WCAG 2.2 target-size minimum) and usually 32 px.
- The statusbar hides below 760 px; no information is lost because System/Settings
  repeat it.
- Drawers are modal, close on `Esc`/scrim, trap focus and restore focus to the
  trigger.
- At 200% zoom the layout reflows to the same rules; no fixed-height text containers.

---

## 13. Accessibility contract (WCAG 2.2 AA target)

1. **Landmarks and headings:** one banner, one main, one navigation; one `h1` per
   workspace; sections in order. A skip link is the first focusable element.
2. **Focus:** visible 2 px focus ring with 2 px offset; 3:1 against adjacent colors.
   Focus moves to the workspace `h1` on route change, to the first field/dialog control
   on open, and back to the trigger on close. No focus traps except modal surfaces.
3. **Dialogs:** native `<dialog>`; `aria-labelledby`; `aria-modal` where appropriate;
   `Esc` closes; destructive actions default to the safe choice.
4. **Tabs:** roving tabindex, `ArrowLeft/ArrowRight`, `Home/End`, `aria-selected`,
   `role=tabpanel`; only the active panel is in the tab order.
5. **Live regions:** one polite status region for "Sending", "Responding",
   "Response complete", "Cancelled", "Error"; `aria-busy` on the transcript while
   streaming. Do not announce every token.
6. **Forms:** visible labels, `aria-describedby` for limits/errors, `aria-invalid`,
   inline error text, no placeholder-only labels.
7. **Color and state:** text label + icon/shape + color. Verified/failed/unavailable
   each have distinct words. Status dots are decorative and `aria-hidden`.
8. **Target size:** ≥ 24×24 CSS px for all pointer targets; ≥ 44×44 for touch on
   mobile; spacing between adjacent targets.
9. **Reflow:** 320 px width, 200% text resize, 400% zoom without loss of content or
   horizontal page scrolling (code blocks excepted, with their own scroll).
10. **Motion:** respect `prefers-reduced-motion`; no parallax, no auto-playing loops.
11. **Theme:** system/dark/light; system follows live OS changes; theme choice persists
    in `localStorage` only.
12. **Time and data:** timestamps include a timezone; durations use `ms`/`s`; byte sizes
    include units; numbers use tabular figures.
13. **Charts/meters:** every meter has an accessible text value; no color-only meter.
    A missing value is "not available", not an empty bar.
14. **Testing:** axe-core scan (no CDN; pinned local copy) plus manual keyboard and
    screen-reader checks for login, send/stop, retry, workspace switch, drawers,
    knowledge detail and settings.

---

## 14. Content rules

| Rule | Example |
| --- | --- |
| Verification is never claimed without a verifier result. | "No independent verifier" ≠ "Verified". |
| Health and readiness are different words. | "Server serving" / "Model not probed". |
| Local is conditional on the endpoint. | "UI bound to 127.0.0.1" + "Model endpoint: http://127.0.0.1:11434". |
| Storage is described as implemented. | "Plaintext SQLite. ASHURA does not encrypt these files." |
| Missing data is explicit. | "GPU memory: not exposed by this runtime." |
| Reliability is an evidence class. | "Evidence score 0.60", not "60% confident". |
| Exact backend strings are preserved. | `user_provided`, `ADMITTED / MERGED`, `REVIEW_REQUIRED`. |
| Timestamps are real and local. | `2026-11-06 20:14:06` with timezone. |
| No decorative fake activity. | No "thinking…" spinner that implies cognition; use "Responding". |
| Model roles are named accurately. | General/tool-use `tony:7b-gpa3`; privacy `tony:7b`; fallback `qwen3.5:2b`. |

---

## 15. Intentionally not shown

Until the corresponding capability exists, the workbench must not display:

- encryption-at-rest status or a lock icon implying encryption;
- server-side session revocation or multi-user roles;
- GPU memory or GPU utilization;
- external tool calls or an agent loop;
- live per-step trace streaming;
- a model manager, downloader or weight editor;
- fact-level knowledge rows without a real `/api/facts`;
- persistent failed/cancelled operation history without an approved journal;
- confidence percentages derived from reliability;
- "Nothing leaves this machine" as an unconditional statement.

---

## 16. Design acceptance checklist

- [ ] The five workspaces and their navigation model are accepted.
- [ ] Command Center keeps conversation as one workspace, not the whole app.
- [ ] Execution Studio uses module steps and does not claim tool calls or live steps.
- [ ] Knowledge Studio shows real provenance and does not invent scores/conflicts.
- [ ] System Monitor distinguishes health/readiness and measured/unavailable.
- [ ] Settings & Security states the real boundaries and supports logout.
- [ ] The token set, type scale and spacing are accepted.
- [ ] Responsive behavior at 320/375/430/768/1024/1440/1920 is accepted.
- [ ] The accessibility contract is accepted.
- [ ] The additive read-only API list in the implementation plan is accepted.
