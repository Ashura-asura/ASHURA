# Architecture status (final checkpoint)

Legend: **Verified** = compiled and unit-tested on a plain JVM during development.
**Written, unverified** = source complete but not yet compiled/run with the Android toolchain.

## Implemented
| Area (spec §) | State |
|---|---|
| Expression evaluator: precedence, parentheses, unary minus, `^`, `%`, sqrt/abs, exact decimals, resource limits (§11.1) | Verified |
| Unit conversion: length, mass, time, volume, speed, temperature (§11.2) | Verified |
| Calculator tool routing (§5.2) | Verified (routing); tool execution covered by Gradle tests |
| Curriculum pack with validated prerequisite graph, cycle/unknown-prerequisite detection, recommendation by mastery (§8) | Verified |
| Seed pack: 4 school-maths topics; every answer and every misconception answer is re-computed in tests (§8.2) | Verified |
| Deterministic answer checker: exact rationals, lowest-terms, misconception detection (§12.3, §7.3) | Verified |
| Lesson planner from pack; generic topics clearly labelled as scaffolds (§7.1) | Verified |
| Spaced-repetition scheduler (§7.5) | Verified |
| Resource policy, RAM tiers, model-manifest validation (§16, §6.3) | Verified |
| Prompt builder: ChatML, untrusted-evidence delimiting, control-token stripping, context trimming (§18.1) | Verified |
| FTS5 query sanitiser incl. Devanagari (§10.1) | Verified |
| Task controller calls the model through `ModelRuntime` with bounded context, falls back honestly on failure (§5) | Written, unverified (needs coroutines test run) |
| Room v3: attempts, misconceptions, persisted interval, FTS5 index + triggers, LIKE fallback (§19, §10) | Written, unverified |
| `PracticeService`: check → mastery/spacing from stored state → atomic persist (§12.3) | Written, unverified |
| Text/Markdown import: validation, normalisation, paragraph/sentence chunking with source offsets, 2 MB and 2000-passage caps, Nepali danda boundary (§10.1) | Verified |
| Library storage: Room v4 `library_chunks` (FK cascade), chunk FTS5 + triggers, LIKE fallback, SAF reader with streaming size cap, import/search/delete UI (§10, §15.3) | Written, unverified |
| Question → keyword extraction → OR/BM25 retrieval; grounding policy (bounded, de-duplicated, per-source cap); extractive cited answers offline; honest "nothing found in your notes"; citations attached to model answers; prompt asks for [n] citations (§10.3, §18.1) | Verified (logic, task controller, prompt) |
| Retrieval SQL, ViewModel wiring, Sources UI | Written, unverified |
| Digit-agnostic input; linear-time import; retry-aware mastery; Android backup rules (see AUDIT.md) | Verified / written |
| Note quiz (cloze) generation, JSON data export (SAF), model-file SHA-256 + storage checks, runtime contract tests | Verified (logic) / Written, unverified (UI/SAF) |
| UI: real Progress screen, recommended lesson, hints, answer checking, delete-all-data, cancel, back handling (§3) | Written, unverified |

## Not implemented — do not advertise as available
- Local model runtime (llama.cpp/MediaPipe/MLC JNI) and model download/verification UI. `ModelRuntime`, `ModelManifest`, `ResourcePolicy` and `PromptBuilder` are ready for it.
- PDF/DOCX/XLSX/PPTX parsers and OCR (only .txt/.md import exists). No semantic/embedding retrieval (keyword BM25 only; paraphrased questions can miss). No check that a model's answer is actually supported by its cited passages.
- Online research, speech, sandboxed code execution, plotting.
- Nepali localisation (digits accepted, UI text is English), accessibility audit on device, release signing.
- Curriculum beyond the 4-topic seed pack.

## Rules
1. Imported documents and web pages are untrusted evidence, never instructions.
2. Never upload private study material without explicit user action and disclosure.
3. Model runtime must support cancellation and explicit unload.
4. Never execute generated code in the app process.
5. Run CPU-heavy parsing/inference off the main thread.
6. Add explicit database migrations; never use destructive migration fallback.
