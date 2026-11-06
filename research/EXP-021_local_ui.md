# EXP-021 - Local web UI production pass

Date: 2026-11-06. Status: **engineering verification; no learning-capability claim.**

## Scope

The original UI (D-061) was a dependency-free MVP: one request at a time, no auth, no persistent
sessions and no streaming. This pass turns it into a single-user local operator console without
adding a framework, CDN, external API or a second copy of the controller.

Architecture:

- `ThreadingHTTPServer` serves static files and JSON/SSE concurrently.
- One `ControllerWorker` thread owns every controller, model and SQLite access; its queue is
  bounded at 8 jobs by default and rejects overflow with 429.
- Chat sessions live in a separate SQLite file (`app/sessions.py`); history is injected into the
  same prompt path used by the CLI.
- Streaming uses SSE with cooperative cancellation. A cancelled answer persists only the user turn.
- Auth is a startup token (HttpOnly, SameSite=Strict cookie, or `X-ASHURA-Token`/Bearer for scripts),
  with CSRF, Host/Origin checks, a strict CSP, security headers, rate limits, request IDs and JSON
  access logs. Binding remains loopback-only.
- The frontend adds a session sidebar, SSE rendering, stop/retry, Markdown/code copy, trace/memory/
  status inspector, OCR upload via picker/drag/paste, theme switch, mobile drawers and shortcuts.

## Verification

### Automated tests

```
python -m pytest -q tests/test_web.py   # 24 passed
python -m pytest -q                     # 315 passed
```

The 24 web tests cover worker serialization and queue bounds, session persistence across reopen,
history injection, SSE token/done events, cancellation without persisting an assistant message,
session CRUD and export, OCR, auth/CSRF/Origin/Host rejection, security headers, token bootstrap,
logout and full-transcript export beyond the 200-message UI page.

### Browser smoke (Echo stub)

Chromium 1248 headless, isolated temporary memory database and session database:

- token unlock dialog and cookie login;
- first send removes the empty-state panel, title updates in the heading and sidebar immediately;
- SSE answer, trace badges/steps, memory search and status cards render;
- Stop marks the stream stopped; Retry sends the question again;
- OCR upload persists the `[image: ...]` user turn and an assistant turn;
- rename updates both heading and sidebar; export downloads Markdown; delete confirmation removes
  the session and creates a fresh chat;
- help dialog, theme switch and the 430 px mobile sidebar work;
- no page errors; the only console message was the expected 401 on `/api/status` before unlock.

### Real-model check

`tony:7b-gpa3` through `config/ashura.ollama.toml`, isolated memory/session databases, one prompt:
`Reply with exactly: local UI streaming works`.

- Answer: `local UI streaming works` (exact).
- Trace total: 13.6 s including model load.
- No page errors. The model was unloaded with `ollama stop` after the check.
- `ollama ps` was empty before and after the run.

## Limitations

- One browser, one Echo-stub session and one real-model turn; this is not a load, soak or
  endurance test.
- The browser smoke is a manual verification, not a CI job. It is not part of the 315-test suite.
- Stop/retry were exercised against the Echo stub, not the real model.
- No accessibility audit, session-database backup/restore test, TLS, multi-user account model,
  conflict-review screen or cross-process queue.
- The first-token timer in the smoke measured placeholder creation, not the first Ollama token;
  the reported 13.6 s is the whole turn.

## Decision

Adopt the console architecture as D-062 (superseding D-061). Keep the local-only, single-user
limits explicit in the README.
