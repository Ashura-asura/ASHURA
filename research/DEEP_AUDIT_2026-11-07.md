# Deep repository audit — 2026-11-07

## Scope and verdict

Audited `main` at `b9ae6a405b50f63398a4062b463a905be79850ee` (351 tracked files; recursive tree complete), the two ASHURA specifications, Android v5 product specification/status/roadmap, research completion/evidence documents, Core controller/memory/learning paths, BrainSim README/results, Android domain/UI/data/runtime sources, and the latest GitHub Actions run.

**Verdict: a credible research prototype plus an early Android product scaffold; not production-ready.** This is a source-level audit, not a formal security review, not a fresh execution of every experiment, and not a device test.

The latest observed main workflow run (#25) succeeded, but the workflow at the audited commit did not include an Android build. A green Python/BrainSim/browser workflow cannot establish that the Android project compiles or launches.

## What the project was meant to become

### ASHURA Core
A local, resource-aware cognitive architecture around a frozen pretrained language foundation: need/controller/router, working and persistent memory, specialist skills, independent verification, temporary adaptation, replay/consolidation, non-regression gates and rollback. Its central research claim was that verified experience could create a new capability, generalise to unseen examples, persist in parameters and retain previous capabilities.

### BrainSim
An independent small neural system trained from scratch on structured tasks to investigate recurrent state, prediction, need/action selection, fast associative memory, online adaptation and replay-based consolidation. It was explicitly not meant to be a chatbot and was not supposed to block ASHURA.

### FIRE
A longer-term research direction for artificial metabolism and continuous self-regulation. It is not a completed implementation or a launch dependency.

### Android Tutor v5
A separate offline-first educational app for school-to-university learners and low-memory Android phones: local model, real curriculum/prerequisites, guided tutoring, practice/assessment, misconception feedback, progress/review, local library/document intake, privacy controls and optional later research/speech/simulation features.

## What exists today

### ASHURA Core — research prototype with real implementation
The Python tree contains a cognitive controller, routing/need machinery, local Ollama and llama.cpp adapters, SQLite episodic memory, FTS5 retrieval, provenance/conflict/reliability handling, deterministic arithmetic, optional OCR/document intake, correction attribution, bounded candidate construction, NGR promotion/rollback, an opt-in durable learning worker, CLI and local operator console. The README records 367 ASHURA tests (2 skipped), 46 BrainSim tests and 19 browser screenshot baselines.

This is meaningful engineering progress. However, the Qwen/Tony language checkpoints are user-supplied and frozen. ASHURA does not train them. The promoted candidate in the learning experiments is NumPy adaptive memory, not the language model. The project's own evidence standard correctly records **0/4 persistent language-model capability-learning tests demonstrated**. Correction evaluation is narrow and largely synthetic/author-written; independent distribution-shifted evaluation is still needed.

Adaptive neural memory has not shown a robust advantage over FTS5 and is correctly kept out of the response path. Routing weights/costs remain partly heuristic. OCR lacks held-out real-document CER/WER evidence. Four-client tests are bounded and do not establish production throughput or thermal endurance.

### BrainSim — useful but narrow experimental programme
B1–B6 provide measured structured-task experiments. Fast associative memory helps on the studied hidden-permutation task; explicit task isolation matters; replay reduces forgetting in the tested synthetic consolidation task; and a small policy matches a finite-horizon DP oracle on a synthetic budgeted-choice task.

Important negative limits: B2 did not show a recurrent advantage over a parameter-matched MLP; B3 receives task identity externally; the experiments are synthetic/structured, not evidence of broad cognition; BrainSim is not integrated into ASHURA Core, by design.

### Android Tutor — early scaffold, not the v5 product
The current app is a single-module Kotlin/Compose shell with Room, basic arithmetic, a generic lesson scaffold, a simple scheduler and a replaceable model interface. Its own status document correctly lists actual local inference, model lifecycle, FTS5, document/OCR import, curriculum, assessment/misconception diagnosis, source research, speech, code sandbox, export/delete UX, localization, accessibility and low-RAM/thermal validation as not implemented.

Concrete source findings:
1. `LlamaCppModelRuntime` is a stub and always unavailable.
2. `TaskController.fallthrough()` returns a placeholder even when `isAvailable` is true; it never calls `ModelRuntime.generate()`. This is a broken runtime seam.
3. Application DI creates separate runtime instances for controller and engine, which is the wrong ownership model for a stateful load/unload backend.
4. Each `TutorViewModel.ask()` creates a new conversation, so consecutive questions do not continue one session.
5. Practice UI passes the learner's answer, but the callback ignores it. Outcomes are self-selected; the UI does not reveal/check the reference answer or distinguish objective grading from self-report.
6. The app passes mastery=0 and interval=1 on every practice attempt. The scheduler therefore does not use previously persisted state and mastery cannot accumulate correctly.
7. `LessonPlanner` emits placeholder objectives and a placeholder expected answer, not curriculum content or a valid assessment key.
8. Library search uses SQL `LIKE`, not FTS5; document picking/parsers are not integrated.
9. Progress UI says spaced repetition is not enabled even though a scheduler write path exists.
10. No Android job existed in CI at the audited main commit.

## Goal-versus-reality summary

| Goal | Reality | Assessment |
|---|---|---|
| Local model | Core local model adapters; Android has no actual runtime | Partial in Core; absent in Android |
| Cognitive routing | NFD/module registry and traces, with heuristic/unavailable paths | Prototype |
| Persistent episodic memory | SQLite storage/restart persistence measured | Demonstrated narrowly |
| Reliable facts | Provenance and tri-state verification; narrow independent verification | Partial |
| Adaptive memory | Experimental; FTS5 remains stronger default | Correctly not promoted |
| Fast/slow adaptation | Temporary update and NumPy candidate consolidation tested | Narrowly demonstrated |
| Language-model learning | No ASHURA training of Qwen/Tony weights | Not demonstrated: 0/4 |
| BrainSim cognition | B1–B6 structured tasks, mixed positive and negative results | Research in progress |
| Android offline tutor | No model runtime, real curriculum or assessment | Not delivered |
| Production readiness | Android CI/device validation, endurance and release gates absent | Not ready |

The 87.5% figure in the Core completion audit is engineering checklist coverage, not intelligence or completion of the central learning objective.

## Architecture alignment

Keeping BrainSim independent is sound. FIRE should stay outside the launch critical path. Android Tutor is **not currently an Android port of Python ASHURA Core**: it has no shared engine, memory schema or runtime protocol. That can be a valid split because Android needs native inference/storage, but the boundary must be explicit.

Recommended split:
- Core: Python desktop/research reference implementation.
- BrainSim: independent neural mechanism lab; integrate only after a repeatable advantage is shown.
- Tutor: Android product with Kotlin/Compose, Room/FTS5, on-device inference, curriculum packs and assessment.
- Shared contract: versioned request/response schema, provenance/verification semantics, model manifest, evaluation datasets and benchmark definitions. Do not import Python modules into Android.

## Priorities

### P0 — Android
1. Wire the controller to the real runtime interface; preserve cancellation and generation limits.
2. Use one application-owned runtime instance.
3. Build Android in CI: unit tests and debug APK at minimum.
4. Persist practice attempts and prior mastery/interval; store submitted and expected answers; mark self-report separately from verified grading.
5. Replace placeholder lessons with a versioned real content pack or label the screen as a demo.
6. Benchmark on actual 4 GB/6 GB/8 GB devices: cold start, peak RAM, tokens/s, battery and thermal behavior before selecting a model.

### P0 — Core research integrity
1. Keep language weights frozen until a controlled adapter/parameter-learning experiment has independent data and a baseline.
2. Test remembering, generalisation, consolidation and retention separately.
3. Use independently authored and distribution-shifted evaluation; do not tune on held-out items.
4. Never promote factual corrections without an independent verifier.

### P1 — Android product
Real curriculum/prerequisites; objective rubrics and misconception feedback; conversation continuity/history; SAF document import and provenance; real FTS5; OCR confidence/correction; progress/review backed by attempt history; export/delete-all-data; migration tests; Nepali/English and accessibility testing.

### P1 — Core/BrainSim
Long-run multi-task interference and learned task identification; independent replications of structured BrainSim results; held-out OCR corpus; long-duration thermal/resource tests; conflict-review workflow.

### P2 — defer
Speech, wider web research, simulations, sandboxed code execution, advanced multimodal models and FIRE-style metabolism. None should delay a reliable offline learning loop.

## Conclusion

The project has not become pointless. It has become a testable Python research workbench, a separate neural experiment suite and a new Android educational shell. The biggest risk now is fragmentation: different runtimes, data models and acceptance criteria under one name.

**Recommendation: freeze feature expansion. Make Android compile continuously, close the model-runtime and practice-state defects, then ship one real offline lesson → assessment → feedback → review loop on a real phone. Keep Core and BrainSim as separate research tracks. Do not claim “self-learning LLM”, “complete offline tutor” or “production-ready” yet.**

This is a source-level assessment. The new Android code changes in this branch require CI and device validation before production use.
