# Checkpoint 1 — what changed and how to test

Scope chosen for one session: spec roadmap phases 3–6 (core tutor, tools, curriculum, assessment) on top of the existing slice,
plus the safe groundwork for phases 2, 7 and 11. Phase 2 (real model), 7 (document import/OCR), 9–10 are **not** started.

## Bugs fixed in the previous slice
- `LessonScreen`/`PracticeScreen` referenced `School`, `Assessment`, `ArrowBack` as bare names (compile errors) and used the deprecated `capitalize()`.
- `rememberSaveable` held a non-Parcelable `PracticeQuestion` (crash on rotation/process death). Rich state now lives in the ViewModel.
- Practice scoring was self-reported and mastery was always computed from `0.0` / interval `1`, so progress could never accumulate.
- `LessonPlannerTest` asserted a worked example that the planner never produced.
- Calculator only handled a single binary operation; concepts got a random id on every save.
- Task controller never called the model even when one was available.

## New
Evaluator + unit converter, curriculum pack (4 topics) with validated graph, deterministic answer checker with misconception tags,
hints/assistance-aware mastery, persisted spacing interval, attempts + misconceptions tables, FTS5 library search with fallback
(+ Devanagari-safe query builder), Progress screen, delete-all-data, resource policy, model manifest, injection-safe prompt builder, CI workflow.

## Verification status (honest)
- Pure-Kotlin logic: compiled with kotlinc 2.0.21 and 43 unit tests passed (JUnit API shimmed locally).
- NOT compiled here: Compose UI, Room (KSP), ViewModel/coroutines code, coroutine-based tests. There was no Android SDK/Gradle/Maven access.
  Expect to fix a few compile errors on first `./gradlew assembleDebug`; paste them and I will fix them.
- Room schema JSON (`app/schemas/3.json`) is generated on your first build; commit it, then add a migration test.

## Next checkpoint (suggested)
1. Fix whatever the first Gradle build reports; run on device.
2. Real runtime spike (llama.cpp JNI or MediaPipe LLM) behind `ModelRuntime`, with benchmark harness.
3. Library: SAF picker, TXT/PDF text import, provenance chunks into the FTS index.


---

# Checkpoint 2 — library import with provenance

Scope: text/Markdown import end to end (picker → validation → chunking → Room → FTS5 search → delete).

New: `TextChunker` (pure, 7 tests), Room v4 migration (`library_chunks` with cascade FK, chunk FTS5 + triggers, LIKE fallback),
`DocumentReader` (SAF, streaming 2 MB cap, strict UTF-8, binary rejection, no stored file path), `LibraryScreen`
(import, debounced passage search with source title and passage number, delete with confirmation).
Delete-all-data also clears chunks.

Verification: chunker logic compiled and tested on a JVM (7/7; 50/50 pure tests overall). Room v4 migration, SAF reader, ViewModel and
Compose code are NOT compiled here — same caveat as checkpoint 1. Migration SQL was written to match Room's expected schema
(columns, FK action, index name); the first build's exported `4.json` plus a migration test will confirm it.

Not done: tutor answers do not yet retrieve or cite library passages (next: pass top passages as `retrievedContext`, with citations
in the UI), PDF/Office/OCR, embeddings.

## Next checkpoint (suggested)
1. Fix the first Gradle build errors (send them to me).
2. Retrieval-grounded answers: top-k passages into `TutorRequest.retrievedContext`, citation chips, "not found in your notes" behaviour.
3. Model-runtime spike on a real device.


---

# Checkpoint 3 — answers grounded in your notes

New: question keyword extraction and OR/BM25 retrieval (`FtsQuery.forQuestion`), `GroundingPolicy` (top 4 passages, 3000 chars,
max 2 per note, near-duplicates dropped), extractive offline answers that quote your notes with [n] citations, an explicit
"I searched your notes and found nothing relevant" message, citations attached to model answers, citation-aware prompt, a
"Sources from your notes" list in the Tutor screen. Retrieval failure never blocks an answer. Deterministic tools (calculator) still win.

Verification: 59/59 pure tests on a JVM, including `TaskController` and `PromptBuilder` behaviour with fake runtimes.
Not compiled here: Room query changes, ViewModel/Compose edits.

Limits to know: keyword retrieval only (a paraphrase with no shared words will miss); with a real model, citations show which passages
were *provided*, not proof the answer used them; nothing yet verifies a generated answer against its sources.

## Next checkpoint (suggested)
1. Fix the first Gradle build errors (send them to me).
2. Real-device model runtime spike + benchmark harness behind `ModelRuntime`.
3. Quiz generation from your notes (self-assessed items with source passages) and PDF text import.

---

# UI review (after checkpoint 3)

Static review only (Compose cannot be compiled here): no missing imports found; no unbalanced braces.
Fixed: nested-Scaffold double top padding (`consumeWindowInsets`), light-only theme/status-bar mismatch (added dark theme,
`enableEdgeToEdge`, removed hard-coded bar colours, night resources), radio rows were tappable only on the dot (now whole row,
`Role.RadioButton`), keyboard Done submits an answer, feedback and import status announced to TalkBack (live regions),
long lesson titles ellipsize. Added Compose UI tests (`PracticeScreenTest`).
Known remaining UI debt: all strings are hard-coded English (no `strings.xml`, no Nepali yet); lists use `Column.forEach`
(switch to `LazyColumn` once libraries grow); no tablet/landscape layouts; no on-device accessibility audit or font-scale run.


---

# Final checkpoint — audit fixes and remaining features

Audit: see `docs/AUDIT.md` (1 high, 3 medium, 2 low fixed; open items listed with owners).
Added: note quizzes (deterministic cloze generation, hints, Next question), JSON data export to a user-chosen file,
Devanagari/Arabic-Indic digit input, model-file SHA-256 + storage-space verification, runtime contract tests,
`docs/RUNTIME_INTEGRATION.md`, backup/transfer exclusion rules.

Verification: 72/72 pure tests; fuzz/stress and real-SQLite migration checks as listed in the audit. Android/Compose/Room/SAF code is
still uncompiled here. That first build is the single most valuable next step.

Deliberately NOT done (cannot be done or verified honestly without a device/toolchain): real LLM runtime and benchmarks, PDF/Office/OCR
parsers, Nepali string localisation, release signing, on-device accessibility and performance audits.


---

# Checkpoint 4 — integrated local model (v0.3.0)

Scope: replace `UnavailableModelRuntime` with a real on-device runtime and make model installation usable end to end.

New:
- **LiteRT-LM 0.19.1** adapter (`LiteRtLmModelRuntime`): one mutex-guarded engine, streaming `sendMessageAsync`, cancellation via
  `cancelProcess`, timeout, CPU backend, rehash-on-load, safe unload during generation, honest health/errors.
- **Pinned catalog** (`ModelCatalog`): Qwen2.5-1.5B Q8 for 6 GB+ devices and Qwen3-0.6B INT4 for 4 GB+, with exact revision,
  byte size, SHA-256, HTTPS URL, licence and RAM-tier gating. Qwen3 thinking is disabled for direct tutor answers.
- **ModelManager**: HTTPS-only download with progress and cancel, SAF `.litertlm` import, size/checksum verification, `.part`
  temp file and atomic rename, 1 GB storage reserve, one installed model at a time, explicit load/unload/delete.
- **Settings UI**: device tier, catalog, recommended marker, size/quantisation/licence, download/import/load/unload/delete,
  progress, failure text, delete confirmation, privacy disclosure. Progress/state changes are announced to screen readers.
  Tutor shows the response mode and a no-model hint.
- **Memory pressure**: `Application.onTrimMemory` unloads the model when the process is critical or background-moderate;
  the user reloads it from Settings.
- **Build/toolchain**: Kotlin 2.4.0, AGP 8.13.2, Gradle 8.14.4, KSP 2.3.13, Room 2.8.5 (required by LiteRT-LM metadata),
  `arm64-v8a`/`x86_64` ABI filter, INTERNET/ACCESS_NETWORK_STATE, R8 keep rules.
- **Tests**: `ModelCatalogTest`, `PromptBuilderPartsTest`, `LiteRtLmRuntimeContractTest`; 115 JVM tests pass in total.
- **Artifact**: `dist/ASHURA_Tutor-v0.3.0-dev-debug.apk` (~65 MB), SHA-256
  `3c027947d9b40297dd1d5146b7fa7bacdcba6912620ab964485f80b4ec676855`.
- **Branding**: a short opening screen shows “Powered and built by Bishal Bhandari from Nepal” (English/Nepali), and the
  same credit appears at the bottom of Settings.

Verification: `:app:assembleDebug` and `:app:testDebugUnitTest` succeed. Static/written only: native load and generation,
download progress against the real hosts, cancellation timing, memory/latency/thermal behaviour, GPU backend. A physical
device or emulator is still required for those. The catalog hashes have not been re-downloaded in this environment.

Next: run the device checklist in `docs/RUNTIME_INTEGRATION.md`, then record results in a benchmark note before changing the
default model or backend.

---

# Checkpoint 5 — streaming, structured answers, learner profile (v0.4.0)

Scope: spec §1.3, §1.4, §6.2, §16.5 and roadmap step 4 — make the tutor feel like a tutor while the model writes, and make
runtime behaviour measurable instead of asserted.

New:
- **Real streaming**: `ModelRuntime.generateStream` (single `Complete` default), `LiteRtLmModelRuntime` native delta stream
  via `channelFlow`, `TaskController.executeStream`, `TutorEngine.answerStream`, ViewModel delta rendering. Deterministic
  tools still emit one exact event; a model failure falls back to the offline scaffold.
- **Structured answers**: prompt asks for `ANSWER` / `STEPS` / `CHECK`; `StructuredAnswer` parses tolerantly (bold markers,
  numbered/bulleted steps, Windows line endings) and keeps plain text when a small model ignores the format. Tutor UI renders
  sections with headings.
- **Direct vs Socratic**: `TutorStyle` in `TutorRequest`; Socratic prompts withhold the final answer and ask one guiding
  question. Tutor has a style toggle; the offline scaffold respects the same mode.
- **Learner profile**: `LearnerProfileStore` persists level (school/bachelor/master/not set), style and English/Nepali answer
  language in SharedPreferences; Settings exposes chips. No account or upload.
- **Runtime diagnostics**: measured load time, first-token latency, generation time, approximate tokens/s, Java heap and free
  storage in Settings. Token count is an explicit ~4-characters/token estimate because the engine API does not expose ids.
- **Tests**: `StructuredAnswerTest`, `StreamingTest`, `LearnerProfileStoreTest`, direct/Socratic prompt tests; **139 JVM tests
  pass**, `lintDebug` passes.
- **Artifact**: `dist/ASHURA_Tutor-v0.4.0-dev-debug.apk` (~65 MB), SHA-256
  `f3a85004fd507a4839015ea6c340b114b516695648fb7f0ff97231b70881db43`.

Verification: compile, unit tests and lint pass here. Static/written only: native streaming cadence, first-token timing,
cancellation latency, measured memory/thermal behaviour, and the final structured-answer replacement on a real screen.
Next: run the device checklist in `docs/RUNTIME_INTEGRATION.md` (including the new streaming/diagnostics items), then start
documents/OCR, source verification, research, speech and plotting phases.

---

# Checkpoint 6 — persistent model, chat tutor, document test sets, offline study packs (v0.5.0)

Scope: address the first physical-device feedback (model disappeared after 5–10 seconds, the tutor screen did not feel
like a chat, imported PDFs/Office files produced only four fill-in-the-blanks, and no subject content was bundled).

New:
- **Model stays loaded**: removed the `Application.onTrimMemory` auto-unload entirely. `ModelManager.autoLoadInstalled()`
  loads a verified model at app start, and only an explicit user action unloads it. The OS may still reclaim the process.
- **ChatGPT-style tutor**: the Tutor tab is now a full-height conversation with user/assistant bubbles, streaming deltas,
  a typing indicator, stop/cancel, mode and citation footnotes, a pinned composer, markdown-lite bold/code rendering and
  suggested topics on an empty transcript. The existing bottom navigation is unchanged.
- **Document intelligence**: `PdfTextExtractor` (PdfBox-Android embedded text), `DocumentOcr` (bundled ML Kit Latin and
  Devanagari), `PdfPageOcr` (PdfRenderer + OCR, 24-page cap), and `DocumentReader` now route PDF, PNG/JPEG/WebP, DOCX,
  XLSX, PPTX and text/Markdown into the same provenance-preserving pipeline. Caps: 25 MB PDF, 15 MB image, 2 MB text/Office.
- **Page/slide/sheet provenance**: extractors insert `[Page N]`, `[Slide N]`, `[Sheet: Name]` markers. `SectionLabel`
  recovers them for citations, and `TextChunker` now starts a new chunk at each marker so pages do not merge silently.
- **Richer test sets**: `QuizBuilder` builds up to 20 mixed questions per document — up to 12 machine-checked cloze items,
  up to 6 definitions, and explanation prompts — round-robin across pages/slides/sheets with deduplication and section-aware
  prompts. Self-assessed items reveal a model answer after the learner records a rating. Deterministic fallback works with
  no model loaded. `startNoteQuiz` reports the actual mix in the Library.
- **Offline study packs**: 200 Markdown notes (20 each for mathematics, general science, physics, chemistry, Python, C,
  Rust, electrical engineering, basic electronics and devices, and advanced calculus) fetched from Wikipedia introductions
  by `tools/fetch_study_sets.py`. `app/src/main/assets/study_sets/manifest.json` records source URL, CC BY-SA 4.0 licence,
  retrieval date, size and SHA-256 for every note. `StudyPackRepository` verifies the checksum before import; the Library
  shows subjects, individual sets, attribution and "add all". `LICENSE.md` and `README.md` ship with the pack.
- **Tests**: `DocumentQuizTest` (section labels, provenance-aware chunking, citation labels, quiz mix/caps/dedup),
  `PdfTextExtractorTest` (Robolectric PDF round-trip and page cap), `StudyPackRepositoryTest` (10 subjects × 20 sets, all
  200 checksums, tamper rejection), plus updated `TextChunkerTest` PDF/image detection and caps. **151 JVM tests pass**,
  `lintDebug` passes, `assembleDebug` succeeds.
- **Artifact**: `dist/ASHURA_Tutor-v0.5.0-dev-debug.apk` (~99 MB; the increase is the bundled OCR recognisers), SHA-256
  `3d50111f5079add9a02b0095b1e3eae872e9ab954f6012d69b084f1057030707`.

Verification: compile, JVM tests, lint and APK assembly pass in this environment. Static/written only: whether the model
actually stays resident on the phone, chat scrolling/IME behaviour, real OCR accuracy, PDF/PowerPoint extraction quality,
checksum-verified import of all 200 packs on-device, and memory/thermal behaviour with the larger APK.

Next: install `dist/ASHURA_Tutor-v0.5.0-dev-debug.apk` on the phone and verify (1) Settings → load model, wait 60 s, ask a
question; the model must remain loaded; (2) chat streaming/stop/scroll; (3) import a text PDF, a scanned PDF/photo, a PPTX
and a DOCX, then run Quiz me and confirm the mixed set and page/slide citations; (4) Library → add a subject and confirm
the study sets and their checksums import; (5) record actual timings and any OCR/extraction failures before the next change.

---

# Checkpoint 7 — chat surface rebuilt to match ChatGPT/Claude (v0.5.1)

The first v0.5.0 chat still looked like a form: tinted header, coloured assistant bubble, bordered
text field and an external send button. Rebuilt the Tutor tab as a conversation surface:

- **Neutral canvas** — white/near-black background with quiet grey surfaces; the indigo accent is now
  reserved for the avatar and send button. User messages are light-grey rounded bubbles; assistant
  turns are full-width prose with no bubble, matching ChatGPT/Claude.
- **Slim header** — avatar, product name, live model-status dot and text, compact Socratic/Direct
  toggle, and a New chat action. No toolbar divider or oversized title.
- **Composer** — one rounded, hairline-bordered capsule with an inline `BasicTextField` and a circular
  send/stop button inside it, plus a one-line "can make mistakes" disclaimer.
- **Transcript behaviour** — streaming caret, animated three-dot thinking state, auto-follow only when
  the learner is at the newest message, and a jump-to-latest button when they scroll back.
- **Message actions** — copy answer with a transient "Copied" confirmation; citations and mode labels
  remain as quiet metadata.
- **New chat** — clears the visible transcript and starts a fresh stored conversation without deleting
  the previous one.
- **Welcome state** — centred avatar and greeting with a 2×2 grid of suggestion cards instead of
  full-width outlined buttons.
- **Theme** — explicit light/dark neutral palette (background, surface, surfaceVariant, outline
  variants) so Material defaults no longer leak a purple tint into the chat; bottom navigation is
  white/black with a hairline divider.

Verification: `:app:compileDebugKotlin`, 151 JVM tests, `:app:lintDebug` and `:app:assembleDebug` pass.
Hardware rendering, IME resize, scroll feel and copy behaviour still need the phone.

Artifact: `dist/ASHURA_Tutor-v0.5.1-dev-debug.apk` (~99 MB), SHA-256
`fd2159bf6c40cdec35b522530cc5c412b7b950640eb89577d59116400842f37f`.

---

# Checkpoint 8 — document-intelligence correctness pass and honest status (v0.5.2)

Scope: the v5.0 spec claims and the earlier status file did not match the build. This pass fixed real
document/OCR defects, added the missing CSV path and OCR correction, and rewrote the status document so
unimplemented features are no longer implied to exist.

Fixed defects:
- **XLSX provenance was silently broken.** Sheets were emitted as `[Marks]`, while `TextChunker` and
  `SectionLabel` only recognise `[Sheet: Marks]`. Every spreadsheet passage therefore lost its sheet
  citation. XLSX now emits `[Sheet: Name]`, each cell keeps its coordinate (`A2: Alice`) and formulas keep
  both the displayed value and the expression (`C2: 84 [=B2*2]`).
- **CSV was advertised but unsupported.** New `CsvExtractor` handles quoted fields, escaped quotes,
  newlines inside quotes, `,`/`;`/tab delimiters, a 20 000-row/100-column cap, `[Sheet: CSV]` and `A1`
  references. `TextChunker.Kind.CSV`, strict UTF-8 decoding, `.csv`/`.tsv` MIME + extension detection, and
  the Library picker filters were wired through.
- **OCR skipped pages with a speck of text.** Any embedded character count above zero suppressed OCR.
  Pages with fewer than 24 embedded characters are now OCR'd too; when the embedded layer is thin, both
  layers are kept and the OCR block is labelled.
- **One bad page aborted a whole scan.** Per-page OCR failures are isolated (`failedPages`) and disclosed
  in the imported text; the 24-page OCR cap is disclosed separately.
- **Sideways phone photos failed.** When the first OCR pass finds fewer than 12 characters, 90/180/270°
  rotations are tried and the richest result wins.
- **OCR page labels did not start a new chunk.** The chunker only recognised the exact `[Page N]` form, so
  `[Page N · OCR: check against the original scan]` was treated as ordinary text and pages could merge.
  The provenance pattern now accepts the OCR suffix; a regression test covers it.

Added:
- **Editable OCR text**: Library → edit opens the imported text. Saving normalises it, replaces the body and
  re-chunks/re-indexes its passages atomically, so later search, citations and quizzes use the correction.
- **Truthful architecture status**: `docs/ARCHITECTURE_STATUS.md` now has three tables (verified, device-
  pending, partial) and an explicit "not implemented — do not advertise" table covering online research,
  speech, vision beyond OCR, plotting/simulations, code sandbox, science/programming engines, semantic
  retrieval, evidence-coverage verification, broad curriculum, original-file storage and device benchmarks.
  README carries the same short limitation notice.
- **Tests**: `CsvExtractorTest` (quoted fields, TSV, semicolon, caps, blank rows, provenance, column
  rollover) plus CSV cases in `TextChunkerTest`. **159 JVM tests pass**; `lintDebug` and `assembleDebug`
  pass.

Artifact: `dist/ASHURA_Tutor-v0.5.2-dev-debug.apk` (~99 MB), SHA-256
`3e02c219c86d911bfe3ec1955f7e8481c585d284df18fa6a8b928a4949e662a5`.

Verification: compile, JVM tests and lint pass here. Still device-pending: OCR accuracy/speed on real
scans, Compose editing of a long OCR body, spreadsheet/PDF extraction quality, model residency, and
memory/thermal behaviour.

---

# Checkpoint 9 — confidence labels, hint ladder, clear chat (v0.5.3)

Scope: integrated the external “gap-closing” update (`CHANGES_session.md`) into the v0.5.2 tree after
checking that it was based on the same code and did not revert the document/OCR fixes.

Added:
- **Honest confidence labels** (`ConfidenceLabel`): every completed tutor answer now shows one of
  *verified by calculation*, *based on your notes (individual claims not checked)*, *model-only* or
  *insufficient evidence*. The label is derived from the answer mode and whether citations were actually
  retrieved; it is not a fake percentage. EN + NE strings.
- **Clear chat history**: Settings → *Clear chat history* with confirmation. It deletes conversations and
  messages only; imported notes, learning state and attempts are kept. `clearChatHistory` resets the
  in-memory transcript and cancels an in-flight answer.
- **Hint ladder / stuck detection**: after a wrong attempt the Practice screen nudges the learner to the next
  hint; when hints are exhausted (or there are none) it offers the worked solution. Tests cover fresh
  questions, repeated mistakes, already-taken hints and solution-shown states.
- **Direct-answer override**: if the learner writes “just tell me”, “I give up” and similar phrases while the
  saved style is Socratic, that single answer is generated in direct style. The saved preference is not
  changed, and the Socratic toggle still works normally.

Tests: **173 JVM tests, 0 failures** (159 + 6 confidence + 8 hint-ladder). `lintDebug` and
`assembleDebug` pass.

Artifact: `dist/ASHURA_Tutor-v0.5.3-dev-debug.apk` (~99 MB), SHA-256
`a3e55dcb806e4b63ebd64c0ebfa9b6d6927af10c776bc9b0459fd56d3e5bc697`.

Still open and recorded in `docs/ARCHITECTURE_STATUS.md`: claim-level evidence coverage, explain-my-mistake,
import status/original-file storage, broader assessment types, speech, plotting, code sandbox, online
research, semantic retrieval, encrypted storage and all device benchmarks.

---

# Checkpoint 10 — chat history, regenerate, explain-my-mistake (v0.5.4)

Scope: integrated the second external “gap-closing” update (`ASHURA_Tutor_updated (1).zip`) into the v0.5.3
tree. The zip was based on v0.5.3, so its document/OCR work was already present and was not overwritten.

Added:
- **Chat history** — a History button in the chat header opens a list of saved conversations, newest first.
  Tapping a row reopens it; the bin icon deletes that conversation and its messages only. New chats are
  titled from the first question (48 characters). Reopened chats restore text and answer mode; per-message
  citations were never stored, so the list is intentionally not reconstructed.
- **Regenerate** — the latest assistant answer has a Regenerate action. It drops the last question/answer
  pair from the visible transcript, re-asks the same question, and leaves the previous turn in stored
  history.
- **Explain my mistake** — after an incorrect machine-checked practice answer, a button reveals what the
  learner wrote versus the expected answer, a deterministic reason (known misconception tag, wrong sign,
  decimal point off by a factor of ten, value too large/small), the question’s method, and a next step.
  It never claims to find the first incorrect step, because the app does not capture working.

Fixes made during integration:
- Kept the v0.5.2 document/OCR pipeline, CSV/TSV extractor, per-page OCR isolation and editable OCR text.
- Moved the hint-ladder nudge inside the `!done` branch so a correct answer never shows a “stuck” tip.
- Snapshot the submitted answer against the answer-check result, so editing the field after a wrong answer
  does not change the explanation text.
- Reopened chats restore only the deterministic answer marker. Per-message citations were never stored, so
  restoring a “model-only” or “based on notes” confidence label would be an unverifiable claim.
- Imported the new classes in the project’s normal import order and added EN + NE strings.

Tests: **182 JVM tests, 0 failures** (173 + 9 mistake-explainer). `lintDebug` and `assembleDebug` pass.

Artifact: `dist/ASHURA_Tutor-v0.5.4-dev-debug.apk` (~99 MB), SHA-256
`f33e485bb94bc224a82052325f79fd303aa9b5bb9bebe428a83399f2cd4256e3`.

Still open: import status UI, edit message, claim-level evidence coverage, semantic retrieval, speech,
plotting, code sandbox, online research, encrypted storage and all device benchmarks.

---

# Checkpoint 11 — full derivations no longer hit the 45-second wall (v0.5.5)

Reported: a full-derivation question could still end with “This request took too long. Try a shorter
question.”

Cause: `GenerationLimits` allowed 384 output tokens and only 45 s of wall-clock time. A 1.5B Q8 model on
a phone runs at roughly 4–8 tokens/s, so a multi-step derivation needed 50–100 s and was cut off. The
error text then blamed the learner’s question, which was misleading.

Changed:
- Output budget 384 → **512 tokens**; total answer budget 45 s → **120 s** (the runtime’s allowed
  maximum). The prompt now asks for 2–8 numbered steps for a direct answer.
- The direct-answer prompt explicitly says: if the learner asks for a full derivation, show every
  algebra step and finish it; never reply that the question is too long or ask them to shorten it.
- Socratic override now also recognises “full derivation”, “complete solution”, “show all steps” and
  similar phrases, so those requests switch that one answer to direct style.
- Timeout message is accurate: “The model ran out of time before finishing. Try again, or ask for the
  derivation one step at a time.” It no longer tells the learner their question was too long.

Tests: **184 JVM tests, 0 failures** (182 + prompt assertion + derivation-phrase test + limits guard).
`lintDebug` and `assembleDebug` pass.

Artifact: `dist/ASHURA_Tutor-v0.5.5-dev-debug.apk`, SHA-256
`3a2c7d03758bb2afd49ff423b1b95ca6d961dadd8792498684f08c887012aa12`.

Still device-pending: actual tokens/s on the user’s phone. If a 512-token answer still reaches 120 s,
the next fix should be a per-token idle timeout instead of a total timeout.

---

# Checkpoint 12 — Library import status and re-index (v0.5.6)

Scope: integrated the only genuinely new feature from the second Claude handoff (`ASHURA_v0.5.4_batch2.patch`
/ `ASHURA_Tutor_v0.5.4_source.zip`). The rest of that batch — chat history, Regenerate, Explain my mistake —
was already integrated and verified in v0.5.4, so it was not re-applied. The timeout/derivation fix from
checkpoint 11 is included in this build as well.

Added:
- **Library import status** — every imported item shows a size proxy (chars/k/M), passage count and date
  added. An item whose text has no searchable passages is labelled *not indexed (search cannot find it)*
  and gets a **Re-index** action. `ImportStatus` formats the labels, `ChunkDao.observeCounts` supplies the
  counts as a flow, and `TutorRepository.reindexLibraryItem` rebuilds passages from the stored text in one
  transaction.
- The status line falls back to the old character count until the first database read completes
  (`chunkCounts` starts as `null`), avoiding a false “not indexed” flash.
- Re-indexing a genuinely empty note is refused by the existing text normaliser and reported in the
  Library message line rather than silently creating zero passages.

Tests: **190 JVM tests, 0 failures** (184 + 6 import-status). `lintDebug` and `assembleDebug` pass.

Artifact: `dist/ASHURA_Tutor-v0.5.6-dev-debug.apk` (~99 MB), SHA-256
`b632dbaff067757d7e5c171503e1c485399d9576da362bef95c15614c0471355`.

Device checks for the user: every imported item should show a passage count; Re-index should appear only
on a genuinely unindexed item and should populate the count without changing the text. Also re-check a
full-derivation chat question against the 120 s budget.

---

# Checkpoint 13 — Timed four-option tests and study-set add states (v0.5.7)

Scope: the requested test modes, saved score/time history and clear added/not-added study-set states, built
against the production rules in the supplied completion prompt. Hardware steps remain the user's to run.

Added:
- **Timed test modes** — Quick 20 questions, Medium 35, Long 50. The timer is selected automatically from
  the mode at 60 seconds per question (20 / 35 / 50 minutes). Starting a mode from Library opens the test
  in the Tutor tab.
- **Four-option questions only** — `domain/assessment/ChoiceQuizBuilder.kt` produces exactly four distinct
  options from the learner's imported definitions: “Which option best defines X?” and “Which term does this
  description match?”. There are no fill-in-the-blank or free-text test items, no invented options, and the
  order is seeded deterministically. If the notes cannot supply four distinct choices the test is refused
  with an honest message instead of starting a malformed test.
- **Session and scoring** — `TestSession` records answers, navigation, countdown, correct count, percentage,
  time taken and whether the clock ran out. Unanswered questions count as wrong. The timer is driven by the
  ViewModel and stops when the test finishes or is left.
- **Saved results and score changes** — new Room table `test_results`, additive migration 4→5, and schema
  `5.json`. Each result stores mode, title, total questions, obtained marks, percentage, time taken and timeout
  state. Progress shows the history and the marks/percentage change from the previous test of the same mode.
  Clearing history is confirmed; test results are exported in JSON and wiped by delete-all-data.
- **Study-set add state** — Library subjects show “X of Y added”; added sets show a check mark and a minus
  action (remove after confirmation), unadded sets show “+ Add”. “Add all” is disabled once the subject is
  complete. Removing a set deletes only that note and its passages; other notes and test results stay.
- **Single-note test** — a note row's Test action starts a shorter Quick test from that note so a learner can
  practise one document without needing 20 facts. Library-wide modes still require their exact counts.

Verification: **212 JVM tests, 0 failures** from `clean :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`.
`lintDebug` and `assembleDebug` pass. Debug APK measured at **103,938,285 bytes (~99.1 MiB)**. No APK is committed.

Status labels:
- Four-option builder, session/scoring, history deltas, migrations and data-control semantics: **unit-tested**
  (`ChoiceQuizBuilderTest`, `TestSessionTest`, `TestModeTest`, `TestHistoryTest`, `DataControlsTest`,
  `MigrationTest`).
- Timer UI, result screen, Library indicators and TalkBack/layout: **NOT VERIFIED** — no device or emulator here.

Manual device checks for the user:
1. Import at least a few notes (or add one subject), open Library, start Quick; confirm the header counts down
   from 20:00 and the test opens in the Tutor tab.
2. Answer some questions, navigate back and forth, finish; confirm marks, percentage, time taken and the review
   list. Take a second Quick test and confirm Progress shows the marks change.
3. Let a test run out; confirm it ends automatically and unanswered questions count as wrong.
4. Expand a subject; confirm added sets show a check and minus, unadded sets show “+ Add”, and the subject line
   counts correctly. Remove one set with confirmation and confirm other notes survive.
5. Check English and Nepali at font scale 1.0 and 2.0, with TalkBack on the timer and options.
6. Upgrade from the v0.5.6 APK and confirm notes, chats, attempts and settings survive; test results start empty.

Known limitation: an in-progress test is held in the ViewModel, so rotation keeps it but process death loses
it. Persisting an active session is not implemented and is recorded as missing rather than claimed.

## CI and lint baseline (P0.2 / P0.3)

The earlier workflow lived in `ASHURA_android_dev/ASHURA_Tutor/.github/workflows/`, where GitHub never reads
it, so no Android job had ever run. It now lives at the repository root and uses a working directory of
`ASHURA_android_dev/ASHURA_Tutor`.

- `android-ci` run **42476055931** (green): JDK 21, cached Gradle, `testDebugUnitTest`, `lintDebug`,
  `assembleDebug`, then uploads `app-debug.apk` plus test/lint reports.
- The gate was proven, not assumed: a temporary failing test on branch `ci-failure-selftest` produced run
  **42476341546** with `213 tests completed, 1 failed` and a failed job. The branch was deleted.
- JDK 21 is required for the JVM tests because the pinned LiteRT-LM 0.19.1 classes are newer bytecode than
  Java 17; app bytecode still targets Java 17.
- `app/lint-baseline.xml` records the current 53 warnings. `:app:lintDebug` now says “no new issues (53
  warnings filtered by baseline)”. New issues are still reported and any lint error fails the build
  (`abortOnError = true`); P0.3 does not require new warnings to fail.

---

# Checkpoint 14 — Shareable diagnostics export (P1.2, partial)

P1.2 asks for a Settings action that writes measured runtime counters to a file the user can share.
The export is now implemented; the measurements themselves still need the user's phone and model.

Added:
- `domain/export/DiagnosticsReport.kt`: a dependency-free report containing the already-measured runtime
  counters (backend, load ms, first-token ms, generation ms, estimated tokens, tokens/s, heap MB) plus
  device model/manufacturer, Android version, supported ABIs, RAM tier, low-RAM flag, total RAM, free
  storage and a timestamp.
- Settings → **Export diagnostics** writes `ashura-diagnostics.json` through the Storage Access Framework.
  The file is built as JSON by the existing `Json` writer.
- The report deliberately contains **no learner text**: no questions, answers, note titles, prompts,
  file names or model output. A `privacy` line states this inside the file, and a test asserts the exact
  key set so a later field cannot silently add personal data.

Verification: **215 JVM tests, 0 failures** (`DiagnosticsReportTest` covers valid JSON, quoting, the
no-model-yet case and the exact allowed keys). `:app:lintDebug` and `:app:assembleDebug` pass.
Status labels:
- JSON shape, counter selection and privacy key set: **unit-tested**.
- The Settings button, SAF save dialog and real values: **NOT VERIFIED** — no device or emulator here.

Still missing from P1.2: p50/p95 latency over 20 fixed questions, battery drain per 10 minutes,
thermal throttling behaviour and peak-RAM sampling over a session. The export only reports counters the
runtime already records; it does not claim to measure those missing values.

Manual device check:
1. Open Settings with no model loaded; tap Export diagnostics; save the file; confirm it contains the
   device fields and no runtime keys.
2. Load a model, ask one question, export again; confirm backend/timing/tokens-per-second values appear.
3. Open the file in a text editor and confirm no note title, question or answer text is present.
4. Optionally share the file when reporting performance.

---

# Checkpoint 15 — Home screen now states the next action (v0.5.8, P4.6/§3.2)

The old Home screen was a tagline, a description and two buttons. It did not show recent material,
import, review or whether the app was offline-ready, so the first screen did not answer “what do I do
now?”. It now follows §3.2 directly.

Changed:
- **Continue learning card** shows the recommended topic and a single Continue action; it keeps the
  “all mastered” message when the pack is complete.
- **Four quick actions**: Ask a question, Learn a topic, Import material, Today's review. Import opens the
  same SAF picker as Library (one shared MIME list in `UiCommon.kt`) and switches to Library so the busy
  state and result are visible. Review opens Progress, where due topics live.
- **Recent material** lists up to three imported items with their size; tapping opens Library. It shows a
  clear empty state instead of a blank area.
- **Model/offline status** says whether the on-device model is ready, being prepared, or still missing,
  and a privacy line states that notes and history stay on the device.
- Removed the now-unused `home_description` and `home_next_lesson` strings.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. There are no
Compose UI tests in this project (adding them would need a new dependency), so the layout itself is
**NOT VERIFIED** until it runs on a phone.

Manual device check:
1. Fresh Home: confirm Continue card, four tiles, recent empty state and model status are all visible
   without scrolling on a small phone, and all are reachable at font scale 1.0 and 2.0.
2. Tap Import, pick a PDF; confirm the app switches to Library and shows importing/result.
3. Import three notes; confirm Home lists the three most recent by title and size.
4. Load the model, return Home; confirm the status changes to “On-device model ready · works offline”.
5. TalkBack: confirm the tiles read as buttons with their title and hint, and the headings are announced.

---

# Checkpoint 16 — Library split into sections with item details (P4.7/§3.4)

Library used to be one very long scroll: import, search, three test buttons, 200 expandable study sets
and the imported list, all in one column. Finding a document meant scrolling past the study sets, and
each row hid its actions behind small icons.

Changed:
- **Three sections** selected by chips at the top: **Material**, **Study sets**, **Tests**. Only the
  chosen section is loaded, so the imported list is no longer buried under 200 study sets.
- **Material filters**: All, Recent (added in the last seven days), Documents (PDF, photo, Word, Excel,
  PowerPoint) and Notes (text-like imports). The list stays newest-first.
- **Item detail**: tapping a row opens a dialog with the title, format, size, date added, passage count
  and whether it is indexed, plus Test, Edit text, Re-index (only when unindexed) and Delete. The
  actions are stacked in the dialog body so four buttons cannot overflow a narrow screen.
- **Study sets and Tests** keep their previous behaviour but now live in their own sections.
- Search remains inside Material and still returns passages, not just titles.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. No Compose UI
tests exist, so the layout is **NOT VERIFIED** until it runs on a phone.

Manual device check:
1. Open Library: confirm the three section chips, and that Study sets is not visible in Material.
2. Import a PDF and a .txt; confirm Documents and Notes filters each show the right item.
3. Add an item, confirm it appears under Recent; wait beyond seven days or change the device date to
   confirm it leaves Recent but stays in All.
4. Tap an item: confirm format, size, date and index state, then use Test, Edit, Delete and (on a
   deliberately unindexed item) Re-index.
5. TalkBack: confirm each chip reads as selected/not selected and each row reads its title and status.

---

# Checkpoint 17 — Tutor phases and honest Progress (v0.5.10, §3.3/§3.5)

Two screens still left the learner guessing: Tutor showed an unlabelled “Thinking…” while retrieval and
generation ran, and Progress printed two percentages per topic, which reads like false precision.

Tutor:
- `TutorUiState.phase` now carries `SEARCHING_NOTES` while passages are retrieved and `WRITING` once the
  answer starts. The empty streaming bubble shows “Searching your notes…” or “Writing the answer…”, and
  the phase is cleared on success, timeout, error and cancellation, so the UI never claims work that has
  stopped (spec §3.3).

Progress:
- Three counts at the top: topics practised, due for review, tests taken.
- Each topic no longer shows mastery and evidence percentages. It shows a qualitative band — Strong,
  Developing, Started or Not started — a progress bar, and “Estimated from your answers · next review …”.
  The explainer still states mastery is an estimate, not a grade (spec §3.5).
- The progress bar has a TalkBack label equal to the mastery band.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. There are no
Compose UI tests, so both layouts remain **NOT VERIFIED** on a device.

Manual device check:
1. Ask a question with the model loaded and watch the status change from searching to writing; cancel
   mid-answer and confirm the status disappears and the bubble says “Stopped.”
2. Ask a deterministic question (e.g. a calculation) and confirm the busy state clears when the answer
   appears.
3. Open Progress after some practice: confirm the three counts, the qualitative bands, and that no raw
   mastery percentage is shown.
4. TalkBack: confirm the progress bar reads its band, not an unexplained percentage.

---

# Checkpoint 18 — Model-unavailable banner and reduced motion (v0.5.11, §3.3/§3.6)

Spec §3.3 requires a visible model-unavailable state; the header only changed a small dot and a line of
text, which is easy to miss. Spec §3.6 asks for reduced motion; the typing indicator looped forever.

Changed:
- With no model loaded, Tutor now shows a banner under the header: “No model is loaded yet”, a short
  explanation that offline study mode uses notes, calculations and built-in explanations, and a **Set up**
  action that opens Settings. The banner disappears as soon as a model is ready.
- The typing dots read `Settings.Global.ANIMATOR_DURATION_SCALE`. When the learner has turned animations
  off, the dots render statically; the phase text is unchanged. A content observer updates the state if
  the setting changes while the app is open.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. Both behaviours
are Compose-only and remain **NOT VERIFIED** on a device.

Manual device check:
1. Remove/unload the model, open Tutor: confirm the banner and that Set up opens Settings.
2. Load a model, return to Tutor: confirm the banner is gone.
3. Turn off animations in Developer options, start an answer: confirm the dots are static but the phase
   text still changes.
4. Turn animations back on while Tutor is open: confirm the dots animate again without restarting the app.
5. On Home with no model, confirm the status line now has a Set up action that opens Settings.

---

# Checkpoint 19 — Review a due topic from Progress (v0.5.13, §3.5)

Progress showed which topics were due but offered no way to act on that information; the learner had to go
back to Home or Tutor and find the topic again.

Changed:
- Every topic marked “review due” now has a **Review** button. It starts that topic and switches to Tutor,
  so the review begins on the same tap.
- Topics that are not due show only the next review date and no button.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. The navigation
and topic start are Compose-only, so they remain **NOT VERIFIED** on a device.

Manual device check:
1. Practise a topic until it is due (or use an existing due topic), open Progress.
2. Tap Review and confirm Tutor opens with that topic started, then return Back to Progress.
3. Confirm a non-due topic has no Review button.

---

# Checkpoint 20 — Faster, skippable launch (v0.5.14, §3.2)

The brand screen held every cold start for 1.8 s even though the Home screen was ready underneath. Spec
§3.2 asks the app to load quickly and make the next action obvious.

Changed:
- The brand screen now dismisses after 900 ms instead of 1,800 ms.
- Tapping anywhere on it dismisses it immediately; a small “Tap to continue” hint says so.
- Rotating or returning does not replay it (state is saved), as before.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. Launch timing is
device-dependent and remains **NOT VERIFIED**.

Manual device check:
1. Cold-start the app; confirm Home is reachable in about a second.
2. Kill and cold-start again; tap the brand screen immediately and confirm it closes at once.
3. Rotate on Home and confirm the brand screen does not reappear.

---

# Checkpoint 21 — Practice reachable from the lesson bar (v0.5.15, §1.2A)

A lesson is a long scroll and its practice buttons sat at the very bottom, so starting the check-your-
understanding step meant scrolling past every section.

Changed:
- The lesson top bar now has a **Practice** action that starts the first practice question immediately.
  It is hidden when the lesson has no practice questions.

Verification: **215 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. The action is
Compose-only and remains **NOT VERIFIED** on a device.

Manual device check:
1. Open a topic lesson and confirm Practice appears in the top bar.
2. Tap it and confirm the practice screen opens with the first question.
3. Open a lesson with no practice questions and confirm the action is absent.

---

# Checkpoint 22 — Tutor memory, clean answers and same-subject test options (v0.5.16)

The pasted answers exposed four separate problems: the model repeated its own prompt placeholders
(`[n]`, `[Ref]`, “using its id”, an invented `EVIDENCE:` block), it had no memory of earlier turns,
LaTeX was shown as raw `$...$` commands, and test distractors could come from a different subject.

Changed:
- **Conversation memory:** the current conversation window (up to ten previous turns) is replayed with each
  request, so “why?”, “continue” and follow-ups keep their context. New chat still starts empty.
- **Cleaner answers:** the prompt no longer contains placeholder instructions. `AnswerSanitizer` strips
  leaked placeholders, fake evidence headings, “trusted source” wording, chat-template tokens and
  ` thinking...</think>` or “Thinking Process:” blocks. Real `[1]`/`[2]` citations are kept.
- **Longer derivations:** output budget raised to 1024 tokens and timeout to 180 s; the prompt asks for every
  algebra step, and the UI keeps up to 32 numbered steps.
- **Maths:** a dependency-free `LatexLite` renderer converts fractions, roots, Greek letters, operators,
  accents, superscripts and subscripts to Unicode; the prompt asks for Unicode maths instead of LaTeX.
- **Copy:** every question now has a copy action, and the chat bar copies the whole conversation
  (“You:” / “ASHURA:”).
- **Tests:** distractors are chosen from the same note first, then from the wider library, so a physics
  question no longer offers chemistry terms as obviously wrong options.

Verification: **232 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. All UI,
device timing, real model output, memory quality and maths rendering on a phone remain **NOT VERIFIED**.

Manual device check:
1. Ask a question, then ask “why?” or “continue” and confirm the follow-up refers to the earlier answer.
2. Ask for a derivation and confirm there is no visible thinking text, `[n]`, `[Ref]` or `EVIDENCE:` block.
3. Confirm `$...$`, `\frac`, `\dot`/`\ddot` and `\omega` render as readable symbols.
4. Copy a question, an answer and the whole conversation from their respective actions.
5. Start a library-wide test and confirm a question from one note offers options from that same note.

---

# Checkpoint 23 — Resume a truncated answer (v0.5.17, §3.3)

A 1024-token answer can still stop mid-derivation on a slow phone. Previously the only option was to retype
“continue”, which lost the exact stopping point.

Changed:
- The latest answer now has a compact **Continue** action next to Copy and Regenerate.
- It sends a continuation request with the replayed conversation, asking the model to resume from the last
  line, finish the remaining steps and add the check question.
- The visible conversation keeps a small “Continue” turn, so the transcript still reads naturally and the
  action can be repeated if the model stops again.

Verification: **232 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. Whether a real
model resumes cleanly, and the button's layout at large font scale, remain **NOT VERIFIED**.

Manual device check:
1. Ask for a long derivation that stops before the end.
2. Tap **Continue** and confirm the new answer resumes instead of repeating the whole derivation.
3. Tap Continue twice and confirm it still follows on.
4. Confirm Continue is absent while an answer is streaming and on older answers.

---

# Checkpoint 24 — Recover from a failed answer without duplicating history (v0.5.18, §3.3)

Spec §3.3 requires an error state with a recovery action. The error was plain red text, and the existing
Regenerate action only changed the visible messages: the replaced question and answer stayed in the stored
conversation, so reopening the chat showed duplicates.

Changed:
- A failed request now shows **Try again** beside the error; it re-asks the last question.
- Regenerate and retry rewind the stored conversation to just before the last question, so the saved history
  matches what is on screen.
- Retrying a synthetic **Continue** turn re-sends the continuation instruction instead of the bare word.

Verification: **234 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. The button layout,
real-model retry behaviour and history sync on a physical device remain **NOT VERIFIED**.

Manual device check:
1. Force an answer to fail (for example unload the model mid-answer), confirm Try again appears.
2. Tap Try again and confirm one new answer appears, not two.
3. Regenerate a normal answer, close the chat, reopen it from History and confirm there is no duplicate.
4. Regenerate a Continue turn and confirm it resumes rather than restarting.

---

# Checkpoint 25 — Only cite notes that were actually retrieved (v0.5.19, §12.4)

The answer cleaner kept every `[number]` citation, so a small model could invent `[7]` when only one note
passage had been retrieved. The learner would see a citation that pointed at nothing.

Changed:
- `AnswerSanitizer.clean` now takes the number of retrieved passages. Citations inside `1..n` remain;
  anything outside that range is removed, and all numeric citations are removed when no notes were found.
- Both the streaming and one-shot model paths pass the real citation count, after the app has attached the
  sources it actually has.
- The prompt still asks the model to cite with `[1]`, `[2]`; this is a safety net, not a replacement.

Verification: **238 JVM tests, 0 failures**; `:app:lintDebug` and `:app:assembleDebug` pass. Real-model
citation behaviour on a phone remains **NOT VERIFIED**.

Manual device check:
1. Ask a question with one imported note that supports the answer; confirm `[1]` appears only if a source is
   listed under the answer.
2. Ask a general question with no matching note; confirm no `[number]` citation appears in the answer.
3. Reopen a saved chat and confirm citations are not shown as if they were restored (they are per-answer).
