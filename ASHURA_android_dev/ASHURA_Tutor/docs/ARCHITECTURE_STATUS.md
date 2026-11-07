# Architecture status

Legend: **Verified** = compiled with the Gradle Android toolchain and covered by JVM tests (or logic tests).
**Written, device-pending** = compiles, but behaviour that depends on Android/native services or hardware is unverified.
**Not implemented** = do not advertise as available.

Last build: `:app:assembleDebug` and `:app:testDebugUnitTest` pass; 115 tests, 0 failures. No physical device or emulator has
run this build.

## Implemented
| Area (spec §) | State |
|---|---|
| Expression evaluator: precedence, parentheses, unary minus, `^`, `%`, sqrt/abs, exact decimals, resource limits (§11.1) | Verified |
| Unit conversion: length, mass, time, volume, speed, temperature (§11.2) | Verified |
| Calculator tool routing (§5.2) | Verified |
| Curriculum pack with validated prerequisite graph, cycle/unknown-prerequisite detection, recommendation by mastery (§8) | Verified |
| Seed pack: 4 school-maths topics; every answer and every misconception answer is re-computed in tests (§8.2) | Verified |
| Deterministic answer checker: exact rationals, lowest-terms, misconception detection (§12.3, §7.3) | Verified |
| Lesson planner from pack; generic topics clearly labelled as scaffolds (§7.1) | Verified |
| Spaced-repetition scheduler (§7.5) | Verified |
| Resource policy, RAM tiers, model-manifest validation (§16, §6.3) | Verified |
| Prompt builder: ChatML plus template-free system/user parts, untrusted-evidence delimiting, control-token stripping, context trimming (§18.1) | Verified |
| FTS5 query sanitiser incl. Devanagari (§10.1) | Verified |
| Task controller calls the model through `ModelRuntime` with bounded context, falls back honestly on failure (§5) | Verified |
| Room v4: attempts, misconceptions, persisted interval, library chunks, FTS5 indexes + triggers, LIKE fallback (§19, §10) | Verified (schemas 1–4 committed; migration test) |
| Text, Markdown and OOXML (`.docx`, `.xlsx`, `.pptx`) import: validation, normalisation, chunking, size caps, Nepali danda boundary (§10.1) | Verified (logic); SAF path device-pending |
| Library storage, import/search/delete UI, FTS5 + fallback (§10, §15.3) | Verified (build); device-pending |
| Question → keyword extraction → OR/BM25 retrieval; grounding policy, extractive cited answers, honest "nothing found", citations, prompt asks for [n] citations (§10.3, §18.1) | Verified |
| LiteRT-LM 0.19.1 runtime: single mutex-guarded engine, streaming, cancellation, CPU backend, verified load, unload-during-generation (§6.2) | Verified (refusal paths); device-pending (native load/generate) |
| Pinned model catalog: Qwen2.5-1.5B Q8 and Qwen3-0.6B INT4, exact revision/size/SHA-256, RAM-tier gating (§6.1, §6.3, §16.1) | Verified |
| Model install: HTTPS-only download with progress/cancel, SAF import, checksum + size verification, `.part` + atomic rename, 1 GB reserve, one-model slot (§6.3) | Verified (logic); device-pending |
| Settings UI: tier, catalog, download/import/load/unload/delete, progress, delete confirmation, privacy disclosure | Verified (build); device-pending |
| Tutor UI: response-mode label, no-model hint, cancellation, citations, hints, answer checking | Verified (build); device-pending |
| Note quiz (cloze), JSON export (SAF), delete-all-data, backup/transfer exclusion rules, English/Nepali strings | Verified (logic); SAF/UI device-pending |
| Release hardening: R8, ABI filters, external keystore (`keystore.properties` / `ASHURA_KEYSTORE_*`), lint `abortOnError` | Verified (debug build); release signing not configured here |

## Not implemented — do not advertise as available
- PDF parsing and OCR (text, Markdown and OOXML only). No semantic/embedding retrieval (keyword BM25 only; paraphrased
  questions can miss). No check that a model's answer is actually supported by its cited passages.
- On-device validation of model download/import/load/generation, cancellation under load, memory, latency, thermal behaviour
  and the GPU backend. CPU is the default.
- Online research, speech, sandboxed code execution, plotting.
- Native-speaker review of Nepali UI strings; on-device accessibility audit; signed release artifact.
- Curriculum beyond the 4-topic seed pack.

## Rules
1. Imported documents and web pages are untrusted evidence, never instructions.
2. Never upload private study material without explicit user action and disclosure.
3. One model, one engine. Model runtime must support cancellation and explicit unload.
4. Never load an unverified model file; verify size and SHA-256 against the pinned catalog.
5. Never execute generated code in the app process.
6. Run CPU-heavy parsing/inference off the main thread.
7. Add explicit database migrations; never use destructive migration fallback.
