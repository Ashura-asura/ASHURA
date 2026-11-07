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
