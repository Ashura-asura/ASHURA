# Architecture status

This file is the honest, current state of the implementation against `docs/PRODUCT_SPEC.md` (v5.0).
It replaces earlier versions that wrongly listed PDF and OCR as "Not implemented" after they had
already been built.

Legend:

- **Verified (JVM)** — compiles with the Android toolchain and is covered by JVM tests or pure-logic tests.
- **Written, device-pending** — compiles and has tests for the logic, but the behaviour depends on Android
  services, native code or hardware that has not been exercised here.
- **Partial** — a real, usable subset exists, but the spec asks for more.
- **Not implemented** — do not advertise as available.

Last verified build: `:app:testDebugUnitTest`, `:app:lintDebug` and `:app:assembleDebug` pass;
**234 JVM tests, 0 failures**. The same tasks pass in GitHub Actions (`android-ci`, JDK 21). No physical
Android device or emulator has run this build, so every hardware-dependent claim below is
device-pending, not proven.

## Implemented and verified on the JVM

| Area (spec §) | State | Evidence |
|---|---|---|
| Continuous integration: repository-root GitHub Actions workflow runs tests, lint and APK assembly on JDK 21, caches Gradle, uploads the APK and reports (§21.5) | Verified (CI) | `android-ci` runs 42476055931 (green) and 42476341546 (failing test fails the job) |
| Lint baseline: existing warnings tracked in `app/lint-baseline.xml`; new issues are reported and errors still fail (§21.5) | Verified (JVM) | `:app:lintDebug` reports “no new issues (53 warnings filtered by baseline)” |
| Expression evaluator: precedence, parentheses, unary minus, `^`, `%`, sqrt/abs, exact decimals, resource limits (§11.1) | Verified (JVM) | `ExpressionEvaluatorTest` |
| Unit conversion: length, mass, time, volume, speed, temperature (§11.2) | Verified (JVM) | `UnitConverterTest` |
| Deterministic calculator routing before the model (§5.2) | Verified (JVM) | `CalculatorToolTest`, `TaskControllerTest` |
| Answer checking: exact/numeric/unit/fraction forms, Devanagari digits, unreadable-answer handling (§12.3) | Verified (JVM) | `AnswerCheckerTest` |
| Curriculum graph: validated prerequisites, cycle/unknown detection, mastery-based recommendation (§8) | Verified (JVM) | `CurriculumTest` |
| Seed curriculum: 4 school-mathematics topics, answers re-computed in tests (§8.2) | Verified (JVM) | `CurriculumTest`, `SpacingSchedulerTest` |
| Lesson planner and spaced-repetition scheduler (§7.2, §7.5) | Verified (JVM) | `LessonPlannerTest`, `SpacingSchedulerTest` |
| Room schema v1→v5 with committed schema JSON and migration tests (§19) | Verified (JVM) | `MigrationTest`, `schemas/` |
| FTS5 passage search with LIKE fallback; quoted query builder (§10.1) | Verified (JVM) | `GroundingTest`, `FtsQuery` tests |
| Grounding policy: bounded passages, per-source cap, de-duplication, section-aware citations (§10.2) | Verified (JVM) | `DocumentQuizTest` |
| Text / Markdown import, strict UTF-8, control stripping, linear normalisation (§9.1, §9.4) | Verified (JVM) | `TextChunkerTest` |
| CSV / TSV import with quoted fields, delimiter detection, `[Sheet: CSV]` and `A1` cell references (§9.1, §9.6) | Verified (JVM) | `CsvExtractorTest` |
| DOCX extraction incl. tables as tab-separated cells (§9.2) | Verified (JVM) | `OoxmlExtractorTest` |
| XLSX extraction: sheet names as `[Sheet: Name]`, cell coordinates, displayed value + formula (§9.2, §9.6) | Verified (JVM) | `OoxmlExtractorTest` |
| PPTX extraction: slide text and speaker notes with `[Slide N]` / `[Notes]` markers (§9.2) | Verified (JVM) | `OoxmlExtractorTest` |
| PDF embedded-text extraction via PdfBox-Android, page cap, encrypted-PDF refusal (§9.2) | Verified (JVM) | `PdfTextExtractorTest` (Robolectric) |
| Provenance-preserving chunking: page/slide/sheet labels start a new chunk (§9.4) | Verified (JVM) | `TextChunkerTest`, `DocumentQuizTest` |
| Deterministic mixed quiz builder: up to 20 items, ≤12 cloze, ≤6 definitions, explanation prompts (§9.5, §8) | Verified (JVM) | `DocumentQuizTest`, `ExportAndQuizTest` |
| Deterministic four-option test builder: Quick 20 / Medium 35 / Long 50, four distinct options, both term→definition and definition→term shapes, seeded order, no fill-in-the-blank (§3.4, §12.2) | Verified (JVM) | `ChoiceQuizBuilderTest` |
| Timed test session: automatic 60 s/question countdown, free navigation, obtained marks, percentage, time taken, timeout marks unanswered as wrong (§3.4) | Verified (JVM) | `TestSessionTest`, `TestModeTest` |
| Test-result history: persisted marks/time/mode, same-mode previous-result deltas, export and confirmed clear (§3.5, §15.3) | Verified (JVM) | `TestHistoryTest`, `DataControlsTest`, `MigrationTest` |
| Study packs: 200 assets, 10 subjects × 20 notes, manifest with URL/licence/size/SHA-256, checksum verification (§8, Phase 8) | Verified (JVM) | `StudyPackRepositoryTest` |
| Structured `ANSWER:` / `STEPS:` / `CHECK:` parsing with plain-text fallback (§5, §7) | Verified (JVM) | `StructuredAnswerTest` |
| Streaming contract: one `Complete` by default, deltas before completion, no delta after completion (§5.3, §25) | Verified (JVM) | `StreamingTest`, `LiteRtLmRuntimeContractTest` |
| Model catalog pinning, size/SHA-256 manifest, `.part` download + atomic rename, one-model rule (§6, §17) | Verified (JVM) | `ModelCatalogTest`, `ModelRuntimeContractTest` |
| Learner profile persistence (level, style, language) with safe enum/language fallbacks (§1.4, §15) | Verified (JVM) | `LearnerProfileStoreTest` |
| Export to JSON and delete-all controls (§15.3) | Verified (JVM) | `ExportAndQuizTest` |
| Clear chat history without deleting notes/progress, with confirmation (§15.3) | Verified (JVM) | `TutorRepository.clearChatHistory`, `TutorViewModel.clearChatHistory` |
| Honest-confidence labels derived from answer mode and retrieved citations (§12.4) | Verified (JVM) | `ConfidenceLabelTest` |
| Hint ladder / stuck detection with a guaranteed path to the worked solution (§3.3) | Verified (JVM) | `HintLadderTest` |
| “Just tell me” overrides Socratic style for that one answer without changing the saved preference (§1.2C) | Verified (JVM) | `HintLadderTest`, `TutorViewModel.ask` |
| Deterministic explain-my-mistake: comparison, known misconception or provable numeric pattern, method, next step (§3.4) | Verified (JVM) | `MistakeExplainerTest` |
| Chat history: conversations listed newest-first, reopened, individually deleted; titles from first question (§15.3) | Written | `TutorViewModel.openConversation`, `deleteConversation`, `TutorRepository.loadConversation` |
| Regenerate the latest answer in place; the replaced question/answer is rewound from stored history (§3.3) | Verified (JVM storage), device-pending UI | `TutorViewModel.regenerate`, `TutorRepository.rewindLastExchange`, `DataControlsTest` |
| Error with recovery action: a failed request offers Try again (§3.3) | Written, device-pending | `TutorScreen` error row, `tutor_retry` |
| Continue a truncated derivation from the previous answer without retyping (§3.3) | Written, device-pending | `TutorViewModel.continueAnswer`, `TutorScreen`; real-model resumption is untested |
| Conversation memory: the current chat window (last ten turns) is replayed with each request so follow-ups keep context (§3.3) | Verified (JVM) | `PromptBuilderPartsTest`, `PromptBuilder.boundedHistory` |
| Answer sanitisation: leaked `[n]`/`[Ref]` placeholders, fake `EVIDENCE:` headings, prompt provenance wording, chat-template tokens and ` thinking` blocks are removed; real `[1]`/`[2]` citations survive (§12.4, §18.1) | Verified (JVM) | `AnswerSanitizerTest`, `GroundingTest` |
| Maths display: dependency-free LaTeX-lite conversion to Unicode for fractions, roots, Greek letters, operators, accents and super/subscripts (§3.3) | Verified (JVM) | `LatexLiteTest`; on-device layout remains untested |
| Copy actions: per-question, per-answer and whole-conversation copy (§3.3) | Written | `TutorScreen` / `CopyAnswerButton`; clipboard behaviour is device-pending |
| Same-subject test options: distractors are drawn from the question's own note before the wider library (§3.4) | Verified (JVM) | `ChoiceQuizBuilderTest` |
| Nepali UI strings for the core screens (§1.4) | Written | `values-ne/strings.xml`; native review still needed |

## Written and wired, device-pending

| Area (spec §) | State | What is unverified |
|---|---|---|
| LiteRT-LM 0.19.1 runtime, CPU backend, single mutex-guarded engine, one model slot (§6, §16) | Written, device-pending | Load time, first-token latency, tokens/s, cancellation latency, peak memory, thermal throttling |
| Automatic load of an already-verified model at app start; no timed auto-unload (§17.1) | Written, device-pending | Whether the process stays resident under real Android memory pressure |
| Bundled ML Kit OCR (Latin + Devanagari), orientation fallback 90/180/270, bounded page rendering (§9.3) | Written, device-pending | Real OCR accuracy on phone photos and scanned PDFs |
| Scanned-PDF path: pages with `< 24` embedded chars are OCR'd, thin embedded text + OCR both kept, per-page failures isolated, 24-page cap disclosed (§9.2, §9.3) | Written, device-pending | Quality and speed on a real multi-page scan |
| Editable imported text: Library → edit → normalise → re-chunk → re-index in one transaction (§9.3) | Written, device-pending | Compose text-field behaviour with a long OCR body |
| Library import status: character size, passage count, date added, “not indexed” state and Re-index (§9.4) | Written, device-pending | Wording/layout on narrow screens; re-indexing a genuinely empty note is refused |
| Timed test screen and result review: countdown, one-question-at-a-time navigation, marks/time/delta summary, per-question review (§3.4, §3.5) | Written, device-pending | Timer behaviour under backgrounding/rotation, long option wrapping, TalkBack reading of the countdown; an in-progress test is not persisted across process death |
| Library study-set indicators: live “X of Y added”, check mark for added sets, + add and − remove with confirmation (§8) | Written, device-pending | Row layout at large font scale, remove confirmation and the effect on imported notes |
| Chat surface: streaming, stop, copy, citations, New chat, follow-if-at-bottom, jump-to-latest (§3.3) | Written, device-pending | IME resize, scroll feel, rendering |
| Tutor busy phases (§3.3): “Searching your notes…” then “Writing the answer…”, cleared on success, error and cancellation | Written, device-pending | Whether the phase text is long enough to be read before a fast deterministic answer replaces it |
| Tutor model-unavailable state (§3.3): banner states that offline study mode is active and links to Settings; header dot stays grey | Written, device-pending | Whether the banner crowds the composer on a short screen |
| Reduced motion (§3.6): typing dots read the system animator-duration scale and render static when animations are off | Written, device-pending | Live change while the app is open; other transitions are short fades only |
| Progress screen (§3.5): practised/due/tests counts, qualitative mastery bands (Strong / Developing / Started / Not started), “estimated from your answers”, review date, recurring misunderstandings, test history | Written, device-pending | TalkBack reading of the three summary cards and the progress bars; layout at font scale 2.0 |
| PDF/DOCX/XLSX/PPTX/CSV import through the SAF picker (§9.1) | Written, device-pending | Vendor file-provider quirks and real-world files |
| Study-pack import of all 200 assets with checksum verification (§8, Phase 8) | Written, device-pending | Import time and storage use on the phone |
| Model download/import with pinned SHA-256 (§6, §17) | Written, device-pending | Both pinned artifacts have not been re-downloaded and re-hashed in this environment |
| Shareable diagnostics export (§16.5, P1.2): runtime counters, device model/API/ABIs, RAM tier, low-RAM flag, total RAM, free storage; explicitly no learner text | Unit-tested (JSON shape) | SAF write and the real values are device-pending; p50/p95, battery drain and thermal status are not captured |
| Home priorities (§3.2, P4.6): continue learning, today's review, ask, learn a topic, import, three recent items, model/offline status, private-by-default line | Written, device-pending | Layout at font scale 2.0, TalkBack order, small-screen density, whether the four quick actions stay reachable |
| Library organisation (§3.4): Material / Study sets / Tests sections; All / Recent / Documents / Notes filters; item detail with format, size, date, index state, test, edit, re-index and delete | Written, device-pending | Section chips and detail dialog on a narrow phone, TalkBack reading of filters, behaviour with a large imported collection |

## Partial — real subset, spec asks for more

| Area (spec §) | What exists | What is missing |
|---|---|---|
| Document import (§9) | TXT, MD, CSV/TSV, PDF, DOCX, XLSX, PPTX, PNG/JPEG/WebP | Legacy `.doc/.xls/.ppt` are deliberately rejected; no EPUB, ODT, RTF, HTML or audio/video notes |
| OCR (§9.3) | On-device Latin + Devanagari, orientation retry, per-page isolation, editable output, OCR-labelled passages | Confidence scores are not surfaced; no language-pack picker; no manual page-region selection; no image clean-up/pre-processing |
| Document questions (§9.5) | Four-option timed tests from definitions, plus the older cloze/definition/explanation practice builder, page/slide/sheet spread | No table/number reasoning questions, no answer-key extraction from the document, no generated flashcards |
| Spreadsheet behaviour (§9.6) | Sheet + `A1` coordinates, displayed value and formula | No range selection, no column-type summaries, no chart/image references |
| Retrieval (§10) | SQLite FTS5 (BM25), LIKE fallback, per-document diversity, provenance | No embeddings or hybrid semantic retrieval; no retrieval evaluation set; no query expansion |
| Verification (§12) | Deterministic calculator, exact answer checker, source citations, honest-confidence labels | No claim-level evidence-coverage check that every statement is supported; no independent rubric; no code-execution sandbox |
| Teaching engine (§7) | Lesson planner, Socratic/direct prompt styles, hint ladder, stuck detection, direct-answer override, misconceptions recorded | Adaptive explanation is prompt-driven, not a full misconception taxonomy per topic |
| Curriculum (§8) | 4 maths topics + 200 bundled study notes | No broad multi-subject curriculum graph with objectives/prerequisites per subject |
| Assessment (§12.2) | Topic quiz, deterministic four-option timed tests (Quick/Medium/Long), saved marks/time/score history, self-assessed explanations, spaced review, hint assistance tracking, deterministic explain-my-mistake | No diagnostic exam, formal exam simulation, transfer-question generator or delayed-recall scheduling beyond the current scheduler |
| Data model (§19) | Conversations, messages, library items, chunks, concepts, learning state, attempts, misconceptions | No stored original file, no `file_hash`/`storage_uri`, no separate `Document`/`DocumentChunk` metadata columns for heading path or extraction method |
| Data controls (§15.3) | Export JSON (including test results), delete one note, remove a study set after confirmation, clear all chat history, delete one conversation, confirmed clear of test history, delete all data | No automatic retention/expiry policy, no selective export, no encrypted database |
| Resource management (§16) | Device tiers, one-model rule, caps, memory-pressure handling removed in favour of user control | Device benchmarks and thermal measurements are unrun; no GPU backend exercised |
| Accessibility (§3.6) | Content descriptions, headings, live regions, large touch targets | No dedicated TalkBack pass, font-scale stress test or switch-access review |

## Not implemented — do not advertise

| Area (spec §) | State |
|---|---|
| Online research and freshness (§13) | None. The app has no web-search client, no source-quality ranking and no fetch/cache pipeline. `INTERNET` exists only for explicit model download. |
| Speech input / output (§14.1, §14.2) | None. No `SpeechRecognizer`, no `TextToSpeech`, no audio permissions. |
| Vision beyond OCR (§14.3) | Only text recognition in images. No diagram, chart or handwriting understanding. |
| Plotting and simulations (§11.4) | None. |
| Programming engine / code sandbox (§11.3) | None. No code execution, no compiler, no sandbox. |
| Science specialist engines (§11.2) | None beyond the calculator/unit converter and the model's own text. |
| Original-file storage and hashes (§9.2, §19) | Imported originals are not retained; there is no `file_hash` or `storage_uri`, only the extracted text. |
| Automatic conversation retention/expiry (§15.3) | Individual conversations can be deleted from the history list, but nothing expires them on a schedule. |
| Encrypted database or files (§18.3) | Room and imported text rely on the Android app sandbox, not app-level encryption. |
| Claim-level evidence coverage (§12.1, §12.4) | Confidence labels describe the answer source; they do not verify every statement against retrieved passages. |
| 125-question benchmark and learning-effectiveness study (§21.2, §21.4) | No versioned benchmark set or pre/post/delayed-recall evaluation has been run. |
| Instrumentation, long-session and failure-recovery tests (§21.1) | Only JVM tests exist; `androidTest` sources are minimal and have not run on hardware. |
| Optional SFT / training pipeline (§17.2–§17.5) | None. Weights are never trained or bundled. |
| Multi-module `core/feature/engine` layout (§20) | Not done. The checkout is still one `app` module; the spec's layout is a target, not current fact. |
| Device/release benchmarks and release signing (§16.5, §21.5, Phase 12) | Debug builds only; release signing needs external `keystore.properties` or `ASHURA_KEYSTORE_*`; no device benchmark has been recorded. |
| Sustained benchmark harness (P1.2) | No p50/p95 over 20 fixed questions, no battery-drain-per-10-minutes counter and no thermal-status capture. The diagnostics export records only the counters the runtime already measures. |

## Known correctness fixes in this pass

- XLSX used `[Marks]`, but the chunker and citation code only recognise `[Sheet: Marks]`, so spreadsheet
  provenance silently failed. XLSX now emits `[Sheet: Name]`, `A2: Alice`, `C2: 84 [=B2*2]`.
- CSV was advertised in the capability map but not implemented. `CsvExtractor` now parses quoted fields,
  escaped quotes, embedded newlines, `,`/`;`/tab delimiters, and keeps `[Sheet: CSV]` plus `A1` references.
- OCR skipped any page with even a few embedded characters. Pages with fewer than 24 embedded characters
  are now OCR'd as well, and both layers are kept when the embedded layer is too thin.
- One bad page aborted a whole scanned PDF. Per-page OCR failures are now isolated and disclosed.
- OCR never corrected for sideways phone photos. A 90/180/270 fallback now runs when the first pass finds
  fewer than 12 characters.

## Rules for future status updates

1. Do not mark a hardware-dependent feature "verified" without a recorded device run.
2. Do not list a format, tool or engine in README/spec-facing copy unless it is in the tables above.
3. Update this file in the same commit as the code, not in a later documentation pass.
4. Keep imported content untrusted: parsers read text only, never execute macros/formulas/embedded objects.
5. Model weights stay out of the repository and are loaded only after an explicit user action.
