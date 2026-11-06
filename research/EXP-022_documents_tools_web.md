# EXP-022 - Documents, agent tools, web research and persistent token

Date: 2026-11-06. Status: **engineering verification; no learning-capability claim and no
document-accuracy claim.**

## Scope

D-064 extends the local workbench (D-062/D-063) without adding a framework, CDN, external LLM API
or network dependency in the browser. Four paths are new:

1. document intake for PDF, DOCX/PPTX/ODT/ODP/ODS, HTML and common text/code formats;
2. bounded local agent tools executed through Ollama native tool calls;
3. optional server-side web search/fetch that records review candidates and gaps;
4. a launch token persisted across server restarts, with task-aware answer budgets and continuation.

The privacy profile keeps web research disabled. The browser CSP remains
`script-src 'self'; style-src 'self'; connect-src 'self'`.

## Implementation

### Documents

`skills/perception/documents.py` routes an upload by extension and validates magic bytes before
parsing. PDF text layers use optional `pypdf`; scanned PDF pages are rendered with optional
PyMuPDF and sent through the existing local Tesseract path. DOCX/PPTX/ODT/ODP/ODS are read with
the standard library's ZIP and XML parsers; HTML and text/code files use the standard library.
Archive member count/expansion and extracted characters are bounded (`MAX_EXTRACT_CHARS = 80_000`).
Every result carries the engine, page count, truncation flag and an explicit failure reason.
The ODF path was found to return empty text on a standard writer file and fixed by collecting text
directly inside `text:p`/`text:span`/`text:h`/`text:a`.

Uploads are routed in `app/web.py`: images keep `kind="ocr"`; documents use the
`documents` capability/path; unsupported suffixes return HTTP 400; the upload cap is 16 MB. A
forced upload that fails extraction returns the extractor's error instead of letting the model
invent content.

### Agent tools

`brain/tools.py` registers bounded, read-only workspace tools (`list_files`, `read_text_file`,
`search_text`, `file_info`, `calculate`, `current_time`, `text_stats`, `system_info`) plus a
sandboxed `write_note`. Paths are resolved under the workspace, binary files and oversized reads are
refused, and there is no shell execution. `Controller` uses non-streaming Ollama `/api/chat` for
tool rounds, executes each returned call, records the observation in the trace and response
metadata, then emits the final answer in chunks. A tool-protocol failure falls back to ordinary
generation; malformed arguments are recorded as a tool failure rather than replaced with fabricated
data. NFD enables the `tools` route only when a tool registry and a `chat`-capable model exist.

### Web research

`skills/web/__init__.py` implements an optional keyless DuckDuckGo Lite -> Wikipedia chain, or a
configured SearXNG instance. Fetches are text-only, bounded, and reject non-HTTP(S), loopback and
private targets, including after redirects. The browser still makes no external request. When a
model reports uncertainty and `[web].auto_on_uncertainty` is enabled, the controller retrieves once
and adds a visible "Web check" section in streaming mode; non-streaming calls may replace the
uncertain answer. Unresolved uncertainty is stored as a gap, and grounded web answers are stored as
candidate observations with `training_ready: false`.

`WebFactStore` stores gaps, candidate facts, operator review statuses and stats in SQLite. The
Settings panel exposes status, review and export. Export writes `web_training.jsonl` and
`web_training_manifest.json` under the configured dataset directory; every record and manifest
carries `training_ready: false` and `review_required: true`. A review status is an operator
decision, not independent fact verification, and no model is trained on these rows.

### Persistent token and generation budgets

`app/token_store.py` loads a valid token or creates a 256-bit token with an atomic write. On POSIX
the directory is `0700` and the file `0600`; symlinks are refused. Windows has no POSIX mode here,
so the file inherits the profile directory ACL. `--token` and `--no-persist-token` bypass
persistence; `--token-file` overrides the path. Auth, CSRF and loopback binding are unchanged.

Generation chooses a task-aware budget (`max_answer_tokens` or `long_answer_tokens`), bounded by the
remaining context window. Length-truncated answers are continued up to `max_continuations` with a
continuation prompt that excludes the repeated prefix. If the model is still at its limit, the
response carries `truncated: true`; the UI shows that warning instead of silently presenting a cut
answer as complete.

## Verification

### Automated tests

```
python -m pytest -q                                      # 367 passed, 2 skipped
python -m pytest -q tests/test_web.py                    # 40 passed
python -m pytest -q tests/test_documents_tools.py \
                    tests/test_web_research.py \
                    tests/test_token_store.py            # 31 passed, 2 skipped
```

The two skips are platform-specific: one POSIX permission assertion and one Windows symlink test
that needs elevated privileges. Coverage added by this pass includes document magic-byte validation,
Office/OpenDocument/HTML/text extraction, extraction failure states, path traversal and binary
reads, symlinked-file exclusion from search/list tools, bounded file-info hashing, tool execution
and observation metadata, web query/fetch/SSRF/redirect handling, compressed-response limits,
candidate fact storage/review/export, web API auth/CSRF/disabled states, token
creation/loading/rotation, document upload routing and the controller's tool/web/continuation paths.

### Browser smoke

`python tests/browser/smoke.py` passed against the real HTTP server with an Echo stub:

- document upload through the file picker (`smoke-notes.txt`) produced a document evidence card
  labelled as locally extracted and not independently verified;
- seeded document/tool/source/truncation evidence rendered, with web sources labelled untrusted;
- the Settings web panel reported the disabled state and `connect-src 'self'`;
- all five workspaces, themes, drawers, palette and 320-1920 px layouts passed;
- 19 screenshot baselines compared. Eighteen matched exactly; `execution-mobile-375` differed by
  0.0236%, below the 0.2% threshold. No console, page or request errors remained.

### Live web check

Two keyless providers were exercised outside the unit tests on 2026-11-06:

- DuckDuckGo Lite returned 3 results for "Python programming language"; fetching
  `https://www.python.org/` returned the expected title and 600 characters of bounded text.
- Wikipedia returned 3 results; fetching the Python article returned the expected title and 600
  characters.
- The SSRF test that redirects a permitted host to a private address was refused.

These checks show the transport and parsing path works on this machine. They are not a search-quality
benchmark.

### Live agent-tool check

A temporary copy of the Ollama profile (temporary memory database, web disabled) ran one real
`tony:7b-gpa3` turn through the production `Controller`:

- routing selected `tools` and `language`;
- the model requested `list_files` with `{"path": "."}`;
- the real `ToolRegistry` executed it in 17.8 ms and returned 21 directories and 20 files;
- the model's final answer used that observation;
- `tool_calls` metadata marked the call `ok: true`, and the trace contained `tool:list_files`;
- the whole turn, including model load, took 58.3 s.

This is one live turn, not a tool-selection benchmark. It verifies the native `chat` -> tool
execution -> observation -> final-answer path; the unit test separately covers failure and
fallback paths with a scripted model.

### Live web-fact export check

One live `tony:7b-gpa3` turn asked for the latest Python release with web research enabled in a
temporary profile and database. The controller selected the `web` route, returned five keyless
search sources, generated an answer and stored one candidate fact. `export_dataset` wrote one
JSONL row and a manifest:

```
records: 1
verification_status: "unverified_web_source"
review_status: "candidate"
training_ready: false
review_required: true
manifest.training_ready: false
```

The answer named a version and release date, but this check did not independently verify that
claim; the search snippets alone do not establish it. That is exactly why the row is a review
candidate and not a training label. The check verifies the research -> fact-store -> export path,
not the fact.

### Live token restart check

A temporary Echo-config server was started twice on a free loopback port with a temporary
`--token-file` and `--sessions-db`:

```
token_unchanged: true
token_length: 43
bootstrap_status: 200
cookie_names: ["ashura_auth"]
authenticated_before_restart: true
authenticated_after_restart_with_same_cookie: true
anonymous_after_restart: 401
```

The same browser cookie authenticated after the process restart, the token file was not rewritten,
and an unauthenticated request still returned 401. Temporary files were removed afterwards.

## Limitations

- **No document accuracy measurement.** The formats and failure states are implemented and tested,
  but no labelled target-document corpus was used and no CER/WER was computed (F-016/P55-P60 stays
  open). Scanned PDFs depend on optional PyMuPDF and a local Tesseract installation.
- **Tool-loop coverage is narrow.** The controller unit test uses a fake `chat` model to drive real
  tool execution, and one live `tony:7b-gpa3` turn called `list_files` successfully. That is not a
  tool-selection-quality benchmark, and the live turn did not exercise web tools or failure recovery.
  EXP-020 measured native tool selection separately on a synthetic suite.
- **Web answers are not verified.** Search results and fetched pages are untrusted observations.
  Operator review does not independently establish a fact, and the exported dataset is explicitly
  not training-ready.
- **Web transport is not exhaustive.** DuckDuckGo Lite/Wikipedia/SearXNG can change markup, rate-limit
  or block automated clients; there is no retry/backoff guarantee or search-quality benchmark.
- **Token persistence is not encryption.** Anyone who can read the file or process memory can use
  the console as the operator. Windows relies on the directory ACL.
- **Continuation was tested with a scripted model.** It proves the controller stitches a
  length-truncated answer and flags an unfinished one; it does not establish long-derivation
  quality for any real model.
- **No learning claim.** D-064 adds bounded tools and intake, not language-model training or a
  verified natural-language verifier (F-042/F-043 remain open).

## Decision

Adopt D-064. Keep the local-only, strict-CSP, single-user model; describe web facts as review
candidates and document extraction as unmeasured on a target corpus.
