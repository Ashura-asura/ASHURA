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
