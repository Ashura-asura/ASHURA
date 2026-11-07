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
