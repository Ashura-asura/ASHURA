# Open problems

Status: 2026-11-06, after EXP-016, EXP-017, EXP-018, EXP-018b, EXP-019 and the F-045 worker work.
Test evidence: **291 ASHURA tests** and **46 BrainSim tests** pass on Windows/Python 3.13. Completion audit:
`research/completion_audit.md` records 87.5% checklist coverage but **0 of 4 language-model learning
tests** demonstrated. This file records what is still not closed; it is
not a roadmap promise and not a claim that the learning loop is complete. The canonical issue list
with remedies remains `research/problem_register.md` (P01-P80, A01-A10); this file explains which
items the latest pass could and could not close.

## 1. What the latest pass closed or narrowed

| Item | New status | Evidence | Remaining gap |
|---|---|---|---|
| F-041 controller trace retention | **fixed at controller level; worker wired** | `Controller` keeps the last non-correction `ExecutionTrace`; verified corrections can invoke an opt-in `correction_loop` hook. Hook errors are captured in `Response.correction`, never raised. `LearningWorker` runs the hook in a durable job store with restart recovery and an optional hard timeout; queue-full, cancellation, error capture, crash recovery, timeout termination and controller integration are tested. | The CLI wiring is opt-in and disabled by default; no live real-model learning run has been recorded. |
| F-042 / P47 arithmetic coverage | **partly fixed** | Decimal(60) now cross-checks `%`, integer `**` and perfect-square `sqrt`; corrections for these can become verified. Negative-modulo semantics are tested. | Irrational roots, non-integer powers, comparisons and all natural-language facts remain unverified. |
| F-039 conflict review | **partly fixed** | `learning/review.py list / resolve`; superseding still requires an independently verified experience. Two tests. | No UI, notification, queue prioritisation or background worker; an open conflict can go unseen. |
| F-044 correction benchmark evidence | **partly fixed** | EXP-013 runs seeds 0-4. EXP-014 adds 10 arithmetic forms x 3 held-out wordings x 5 seeds: 50/50 replay promotions, 0/50 no-replay promotions, 150/150 held-out predictions, 25/25 controls refused. | The corpus is still author-written; held-out wordings share expression tokens with the correction key; no independent distribution or independent author. |
| F-006 arithmetic verifier | **partly fixed** | Same as F-042. | Same as F-042. |
| A02/A03 consolidation persistence | **measured (NumPy only)** | EXP-017: 20/20 promoted NumPy candidates loaded in a fresh process with matching SHA-256, 60/60 corrected held-out predictions, 400/400 old-capability predictions, 20/20 rollbacks restored the parent; 131 KB artifact, 41.2 MB RSS, 6.25 s total. | This is the NumPy adaptive memory, not `tony:7b`; the corpus is author-written; no power-loss, corrupt-manifest, backup/restore or shared-database durability test. |
| Model role selection | **measured (bounded)** | EXP-018: gpa3 and tony:7b both 41/42 adjudicated; gpa3 1.86 s p50, tony:7b 3.04 s p50. EXP-018b: `tony:7b-agentic3` also 41/42 but 0.881 format, 2.11 s p50 and a transient 154.7 s outlier. Adopt gpa3 general, tony:7b privacy; agentic3 is an agentic-benchmark candidate. | Author-written subject suite; base-model and privacy claims not re-measured; no tool-use/agentic benchmark; 4.7 GB exceeds the 2 GB dedicated GPU. |
| P61-P63/P69 resources | **partly measured** | EXP-015 measures exact arithmetic, AMA/FTS5, controller (EchoModel), full NumPy loop, a 300-turn sustained mix and a cold-start `tony:7b` mixed load: arithmetic p50 <= 0.015 ms, AMA admit p50 1.35 ms, FTS5 0.29 ms, loop 24.4 ms, sustained p50 1.39 ms / p95 1.78 ms, single-client language p50 5.52 s / p95 8.06 s. EXP-016 adds 4 clients, 80 turns, forced reload and restart: 0 failures, general p50 25.80 s / p95 35.23 s, arithmetic p50 4.43 ms. EXP-019 adds an explicit concurrency matrix: one slot serializes; two slots give ~1.45x at two clients; four slots are rejected. | No linear scaling; temperature telemetry unavailable; production endurance and routing estimates remain open. |
| F-045 worker durability | **fixed (bounded)** | SQLite job store persists payload/status/result; a fresh worker re-schedules queued jobs and marks running jobs interrupted; a killed child process was recovered as interrupted; `hard_timeout_s` terminates a spawned child and returns stateful-runner updates; CLI wiring is opt-in and config-tested. | Single worker per store; queued recovery is at-least-once; hard timeout requires a picklable runner; no live real-model learning run. |
| F-046 runtime scope | **fixed (bounded)** | EXP-016: 4 concurrent clients, 80 mixed turns, 0 failures; one forced `tony:7b` reload (22.41 s wall / 9.11 s Ollama load); fresh-process restart found both a verified arithmetic record and a user-provided memory record (write PID 1552, verify PID 12164); client RSS max 97 MB; system RAM max 83.9%. | Closed only for client lifecycle, DB persistence, model unload/reload and application restart. Production endurance, thermal telemetry and parallel throughput remain separate; see F-047. |
| F-047 concurrent inference throughput | **fixed (bounded)** | EXP-019 ran a private-server sweep on `tony:7b-gpa3` with `OLLAMA_NUM_PARALLEL` 1/2/4, `OLLAMA_MAX_QUEUE=8` and 1/2/4 clients. One slot serialized (4.93 to 5.95 tokens/s, p50 6.57 to 13.53 s); two slots gave 1.45x at two clients but only 1.19x at four; four slots cut single-client throughput to 3.32 tokens/s and reached 87.7% RAM. The client gate (`max_inflight=1`, bounded queue) and shipped config are in place. | No linear four-way scaling; two slots are the opt-in maximum, four are rejected; the gate is per process and there is no cross-process queue. |
| P70-P72 CI | **fixed and green** | BrainSim installs the missing `psutil`; ASHURA matrix covers Python 3.11-3.13; BrainSim runs on Ubuntu and Windows. Actions run `41938499183` passed all eight jobs on commit `17568c3`. | Keep the matrix green; add real-model integration separately (P74). |

The multi-seed EXP-013 result should be read with care. In seed 3 the stable memory already scored
1.00 on the corrected held-out items (and 0.50 in seeds 1/4), so NGR correctly refused promotion for
zero target gain. That is evidence about the noisy NumPy memory and the tiny held-out set, not
evidence that the loop failed to attribute the correction. EXP-014 expands the set and removes the
accidental stable hits on its frozen cases, but it is still author-written. Full data:
`experiments/learning/loop.json`, `experiments/learning/correction_bench.json`,
`research/phase3_learning.md`, EXP-013/EXP-014 in `research/experiment_log.md`.

## 2. Phase 3 learning: still open

### 2.1 No production learning loop (F-041 residual, P66/P67)

The controller can call a hook and the CLI can build a durable worker from `[learning]`, but the
shipped configs leave it disabled and no live replay corpus or stable checkpoint is committed. A
default session therefore still does not learn automatically. The worker now persists jobs,
re-schedules queued work, marks interrupted running jobs and can hard-terminate a spawned job; it is
single-worker and at-least-once, not a multi-process scheduler.

**What would close it:** configure a replay source and an initial independently evaluated stable
checkpoint, run a live session, and show the stable pointer and fast state behave as declared.
EXP-017 now shows that a promoted NumPy
candidate survives a fresh process and can be rolled back; that covers the NumPy checkpoint path,
not durable worker jobs or a language-model adapter.

### 2.2 Independent verification is narrow (F-042/P47)

Only exact arithmetic equations are independently checked. `sqrt(2)`, `2 ** 0.5`, comparisons and
factual claims remain `user_provided`. Natural-language truth needs a trusted local knowledge source
or a verifier that ASHURA does not have, and the project forbids external LLM APIs. A symbolic
radical representation or a rational-exponent policy could extend arithmetic, but it is a design
change, not a bug fix.

**Do not** treat a user repeating a claim, or a conflict with memory, as independent evidence. If a
language model is involved, it must be the pinned local `tony:7b` (D-025/D-046); it cannot verify its
own claim. A trusted local source or a genuinely independent verifier is still required.

### 2.3 The candidate is not the language model (F-043, by design)

`FastWeights` and the DREAM candidate are NumPy associative memory. ASHURA trains neither
`tony:7b-gpa3` nor `tony:7b`; no adapter or LoRA is trained. The user supplies two fine-tunes:
`tony:7b-gpa3` as the general tutor and `tony:7b` as the privacy profile. EXP-018 evaluates them on a frozen 42-item suite
and selects that role split, but neither checkpoint becomes an ASHURA-learned capability. The
target laptop (i7-1165G7, 16 GB RAM, MX350 2 GB) cannot fine-tune the 7.6 GB Q4_K_M foundation; the
7B model already spills from the 2 GB GPU (F-014), and ASHURA has no verified instruction-tuning
corpus. Local-only ASHURA fine-tuning would require a smaller model or an offline adapter run with a
separate measured pipeline. EXP-017 shows that the NumPy candidate persists across a process restart
and retains old capability, but that does not change either language model. Until a real ASHURA
adapter experiment exists, EXP-013/EXP-017/EXP-018/EXP-018b must not be described as model
self-improvement.

### 2.4 Correction benchmarks are larger but still author-written (F-044)

EXP-013's five seeds did not turn 20 synthetic facts and two corrected wordings into a capability
benchmark; its stable baseline's accidental hits showed that the evaluation set was too small.
EXP-014 now runs 10 arithmetic forms, 3 held-out wordings each and 5 seeds, plus five control
probes. It promoted 50/50 replay runs, rejected 0/50 no-replay runs, predicted 150/150 held-out
wordings and refused 25/25 controls. That is stronger non-regression evidence, but the corpus is
still author-written, the held-out wordings share expression tokens with the correction key, and
there is no independent distribution. The 50/50 promotion rate must not be read as a capability
estimate.

**What would close it:** an independently authored frozen set with non-overlapping wordings, a
control probe that measures accidental stable hits on that set, more seeds with reported intervals,
and tasks designed so memorising one key cannot pass.

### 2.5 Reviewer workflow is minimal (F-039/F-040)

`learning/review.py` lists and resolves conflicts, but there is no UI, notification or queue
priority, and no general natural-language verifier. Semantic facts still require a verified source
within ASHURA's verifier coverage, so most user statements can never become semantic facts. This is
honest by design, not a hidden capability.

## 3. Earlier memory and consolidation problems

These were not changed in this pass and remain open as documented:

- **F-035 / P15:** AMA threshold calibration is synthetic. The default 0.45 was deliberately kept;
  precision at 0.45 is 0.35 on the synthetic sweep. A realistic stream of useful and useless
  unverified items is required. Do not present 0.45 or 1.6 as truth-calibrated.
- **F-036 / P24:** adaptive memory still suffers catastrophic task-switch interference (old-task
  accuracy 0.84 -> 0.04 in the long run). The queue gate does not solve continual learning.
- **F-037 / P22:** the adaptive memory has no measured advantage over FTS5 (FTS5 1.00 throughout;
  adaptive recall 0.41 under 10 distractors). FTS5 remains the default and the adaptive memory stays
  out of the response path.
- **F-038 / P28:** replay ratio and sampling policy are uncalibrated; all arms tied at 1.00 on
  EXP-006. The 0.5 ratio is a placeholder.
- **F-040 / P29:** semantic provenance records where a fact came from, not that it is true.

## 4. Foundation, language and evaluation

- **F-014/F-015/P48/P53:** the 7B model is too large for the 2 GB GPU and the 2B fallback is weak at
  arithmetic/general questions. Exact arithmetic is routed away from the model, but general-answer
  quality remains limited. Changing the foundation requires a new measured baseline.
- **P45/P46:** the "neural" addition candidate is linear least squares; 1.000 accuracy is expected
  for a linear function and adds no capability over exact arithmetic. Keep it non-authoritative.
- **P49/P50:** the 16-question language benchmark is small and single-author; the judge can
  under-credit answers that think aloud. A larger independent benchmark and separate exact /
  semantic / format metrics are still required.
- **P51/P52:** pin model digests and inference parameters for every reported run; DOIs are present
  for the chosen model, but reproducibility still depends on the backend version and settings.
- **P54:** the llama.cpp adapter has not been benchmarked against Ollama.
- **F-016/P55-P60:** OCR is implemented and code-tested but has no held-out real-document accuracy
  measurement (CER/WER, languages, low quality, tables). OCR confidence is not calibrated, and OCR
  corrections do not train a model.

## 5. BrainSim experimental validity (P30-P44)

BrainSim B1-B6 pass their small tests, but the following are not established and were not re-run in
this pass:

- **P30/P31:** B1 frozen unseen-rule accuracy is weak (~0.085) and fast memory interferes after task
  switches.
- **P32/P33:** B2 shows no recurrent advantage over a fixed MLP; evaluation is teacher-forced rather
  than free-running.
- **P34/P35:** B3 supplies task identity externally and uses verified writes, bypassing admission.
- **P36:** B4 is a narrow controlled replay result.
- **P37-P39:** B5 confidence targets do not match evaluation correctness, learning is supervised
  imitation of a DP oracle, and need labels are supplied externally.
- **P40/P41:** B6 depends on full transition coverage and external task identity; 1.000 is
  consistent with lookup rather than rule induction.
- **P42-P44:** tasks are small and author-designed, three seeds are weak evidence, and BrainSim is
  not integrated with ASHURA.

Treat B2's missing recurrent advantage as a valid negative result, not a bug to hide.

## 6. Routing, resources, engineering (P61-P80, A04-A10)

Not addressed by the Phase 3 follow-up:

- **P61-P63:** exact arithmetic, AMA/FTS5 and the NumPy loop now have measured single-process costs
  (EXP-015), plus a 4-client/80-turn bounded run with one reload and one restart (EXP-016). The
  single-client language p50 was 5.52 s; under four concurrent clients it rose to 25.80 s with 0
  failures, so the clients coexist but the local model queues requests. EXP-019 now measures that
  queue explicitly: one slot serializes; two slots give ~1.45x at two clients; four slots are
  rejected on this laptop. The language row in `config/module_costs.json` remains from the Ollama
  baseline because prompt/output lengths differ;
  routing priorities are still heuristic. Do not swap the routing estimates for these numbers
  without a routing experiment.
- **P64/P65:** semantic retrieval and the reasoning module are not built; the registry marks them
  unavailable. Do not advertise them.
- **P67:** `LearningWorker` provides an opt-in bounded background queue with cancellation, error
  capture, a durable SQLite job store, restart recovery and a hard-timeout policy. The CLI wiring
  is opt-in and disabled by default; no live real-model learning run has been recorded.
- **P68:** a failed language backend can still leave general questions unanswered; fallback must
  keep exact computation, retrieved evidence and generated answers distinct.
- **P69:** EXP-015 provides a 300-turn single-process sustained run (0 errors, ~1 MB RSS, 548 KB
  DB) and a cold-start `tony:7b` mixed load. EXP-016 adds 4 concurrent clients, 80 mixed turns, one
  forced reload and one fresh-process persistence check: 0 failures, general p50 25.80 s under
  concurrency, arithmetic p50 4.43 ms, client RSS max 97 MB. EXP-019 adds the explicit server sweep:
  one slot serializes, two slots give ~1.45x at two clients, and four slots cut single-client
  throughput to 3.32 tokens/s. It is still not a production endurance test, thermal telemetry was
  unavailable, and there is no linear-scaling claim.
- **P70-P74:** CI coverage and clean-install/reproducibility checks are incomplete (including
  Python 3.13 and Windows BrainSim); unit tests are not real-model correctness tests.
- **P76-P80:** multiple specifications remain; checkpoint/experiment lifecycle, environment
  manifests, install verification and backup/recovery tests are not complete.
- **A04-A10:** hidden-need inference, learned task segmentation, causal attribution, autonomous
  learning selection, validated dream/consolidation, resource-aware self-preservation and
  catastrophic-forgetting protection are research gaps. The controller's CAGE hook is a mechanism,
  not evidence of causal learning or autonomous curriculum selection.

## 7. Conditions before calling the loop complete

At minimum, the register's section 10 tests still need to pass together, including:

1. unverified or false corrections never become verified facts or promotion labels;
2. an unavailable verifier produces no verified admission;
3. NGR rejects NaN, missing capabilities and target-gain-with-regression candidates;
4. a rejected candidate leaves the stable checkpoint unchanged;
5. contradictory evidence remains auditable and reaches a reviewer;
6. restart preserves the declared fast/slow state policy;
7. the response path survives a background training error and a process-level crash/restart;
8. old-task performance is measured after a real task switch, not just on a frozen replay set.

Items 1-7 have targeted tests today; item 7 covers the job store (interrupted running job, replayed
queued job) but not a live real-model learning session. Item 8 and the larger independent evaluation
do not.

## 8. What is needed to close the rest

| Remaining item | What is required | Dependency |
|---|---|---|
| P70-P73 CI | Done: workflow fix plus green Actions run `41938499183` on `17568c3` (8/8 jobs). | Keep it green; P74 (real-model integration) remains separate. |
| F-041 production loop | A defined replay source, a bootstrapped stable checkpoint, a durable background job store with hard timeout/cancel, CLI configuration and restart tests. | Code + storage design; no new data. |
| F-042 arithmetic residual | Symbolic radicals or a rational-exponent policy with explicit domain/precision rules. Natural-language facts need a trusted local source. | Code/design for arithmetic; data/verifier for facts. |
| F-039 reviewer workflow | UI or notification, queue prioritisation and an audit view. | Code; not required for learning safety. |
| F-044 benchmark | An independently authored frozen corrected set, non-overlapping wordings, control probes for accidental stable hits, more seeds and confidence intervals. EXP-014 supplies size, controls and intervals but not independent authorship. | Benchmark data; no model training. |
| F-035 AMA calibration | A realistic stream of useful, useless, repeated and contradictory unverified items. | Real usage data. |
| F-036 task switches | A continual-learning benchmark with task boundaries and unknown switches, plus a method that actually retains old tasks. | Data + algorithm. |
| F-037 adaptive advantage | A semantic/partial-cue task where the adaptive memory beats FTS5 under a measured protocol. | Data + a better encoder. |
| F-038 replay calibration | A larger distribution-shift benchmark where replay ratios are distinguishable. | Data + compute. |
| F-040 semantic truth | A general local fact verifier or a trusted knowledge source. | Blocked by design/data. |
| F-043 model learning | An ASHURA-trained adapter/fine-tune on feasible hardware with a verified corpus and an NGR-style evaluation. The user-supplied gpa3/tony split is evaluated, not ASHURA-trained. | Hardware + data; not feasible on the current 2 GB GPU. |
| F-014/F-015/P48 | A better local foundation or an accepted accuracy limit; no new Qwen model. | Hardware/scope decision. |
| F-016/P55-P60 OCR | A labelled target-document corpus; CER/WER, field accuracy and confidence calibration. | Data. |
| P30-P44 BrainSim | Harder temporal tasks, hidden task/need labels, partial observations, independent distributions and more seeds. | Separate code + data effort. |
| P61-P63/P69 resources | EXP-015 measures the main non-language modules, a 300-turn sustained mix and a cold-start `tony:7b` mixed load; EXP-016 adds 4-client concurrency, a forced reload and a fresh-process persistence check with 80 turns and 0 failures; EXP-019 adds the explicit one/two/four-slot concurrency matrix. Still needed: production endurance and thermal telemetry. | Runtime measurements; partly done. |
| P64/P65 modules | A semantic-retrieval and reasoning implementation that beats the current baseline before routing to it. | Algorithm + benchmark; do not advertise early. |
| P67 background worker | Durable SQLite jobs, restart recovery, hard timeout and opt-in CLI wiring are done and tested (F-045/D-058); no live real-model learning run exists. | A configured replay corpus and stable checkpoint. |
| P76-P80 engineering | One canonical spec, checkpoint/experiment manifests, clean-install verification and backup/restore tests. | Code/docs; can be done incrementally. |
| A04-A10 | Research programmes (hidden needs, segmentation, causal attribution, curriculum, self-preservation, forgetting). | Research; not a single patch. |

The previous sequence (green CI -> measured module costs and a sustained-load run -> larger frozen
benchmark -> background worker) is now implemented as EXP-015, EXP-014, EXP-016, EXP-017 and
`learning/worker.py`. EXP-016 closes the bounded F-046 scope; EXP-017 measures NumPy consolidation
persistence and retention; EXP-018 selects gpa3 as the general tutor and tony:7b as the privacy
profile; EXP-018b keeps agentic3 as an agentic-benchmark candidate; F-045 is fixed for durable jobs
and hard timeout; EXP-019 fixes F-047 for explicit bounded concurrency without claiming linear
scaling. The next honest steps are: an agentic/tool-use benchmark for `tony:7b-agentic3` ->
independently authored benchmark/real usage data (F-044) -> an ASHURA-trained language-model adapter
experiment (F-043, currently blocked by hardware and corpus).
The AMA, adaptive-memory and BrainSim claims should stay conservative until their data exists.

## 9. Deliberately not doing now

- Do not replace FTS5 with a vector store because neural memory sounds advanced.
- Do not enlarge the model or add external APIs before the local pipeline is reliable.
- Do not tune the EXP-013/EXP-014 held-out sets until every seed promotes.
- Do not describe the NumPy candidate as language-model learning, continual learning or
  self-improvement.
- Do not claim consciousness, emotion or self-awareness from routing scores or resource rules.
