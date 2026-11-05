# Open problems

Status: 2026-11-05, after the Phase 3 follow-up and EXP-016. Test evidence: **265 ASHURA tests** and
**46 BrainSim tests** pass on Windows/Python 3.13. This file records what is still not closed; it is
not a roadmap promise and not a claim that the learning loop is complete. The canonical issue list
with remedies remains `research/problem_register.md` (P01-P80, A01-A10); this file explains which
items the latest pass could and could not close.

## 1. What the latest pass closed or narrowed

| Item | New status | Evidence | Remaining gap |
|---|---|---|---|
| F-041 controller trace retention | **fixed at controller level; worker added** | `Controller` keeps the last non-correction `ExecutionTrace`; verified corrections can invoke an opt-in `correction_loop` hook. Hook errors are captured in `Response.correction`, never raised. `LearningWorker` can run the hook on a daemon thread and return a `job_id`; queue-full, cancellation, error capture and controller integration are tested. | The CLI does not configure the loop: there is no live replay corpus or stable checkpoint bootstrap. Jobs are in-process and lost on restart; no durable queue or hard timeout. |
| F-042 / P47 arithmetic coverage | **partly fixed** | Decimal(60) now cross-checks `%`, integer `**` and perfect-square `sqrt`; corrections for these can become verified. Negative-modulo semantics are tested. | Irrational roots, non-integer powers, comparisons and all natural-language facts remain unverified. |
| F-039 conflict review | **partly fixed** | `learning/review.py list / resolve`; superseding still requires an independently verified experience. Two tests. | No UI, notification, queue prioritisation or background worker; an open conflict can go unseen. |
| F-044 correction benchmark evidence | **partly fixed** | EXP-013 runs seeds 0-4. EXP-014 adds 10 arithmetic forms x 3 held-out wordings x 5 seeds: 50/50 replay promotions, 0/50 no-replay promotions, 150/150 held-out predictions, 25/25 controls refused. | The corpus is still author-written; held-out wordings share expression tokens with the correction key; no independent distribution or independent author. |
| F-006 arithmetic verifier | **partly fixed** | Same as F-042. | Same as F-042. |
| P61-P63/P69 resources | **partly measured** | EXP-015 measures exact arithmetic, AMA/FTS5, controller (EchoModel), full NumPy loop, a 300-turn sustained mix and a cold-start `tony:7b` mixed load: arithmetic p50 <= 0.015 ms, AMA admit p50 1.35 ms, FTS5 0.29 ms, loop 24.4 ms, sustained p50 1.39 ms / p95 1.78 ms, single-client language p50 5.52 s / p95 8.06 s. EXP-016 adds 4 clients, 80 turns, forced reload and restart: 0 failures, general p50 25.80 s / p95 35.23 s, arithmetic p50 4.43 ms. | Concurrent inference queues instead of scaling (F-047); temperature telemetry unavailable; production endurance and routing estimates remain open. |
| F-045 worker durability | **open** | In-process daemon thread, bounded queue, queued cancellation, error capture and drain-on-stop are implemented and tested. | Jobs are lost on process exit; running jobs cannot be force-killed; no durable store, hard timeout, restart test or CLI wiring. |
| F-046 runtime scope | **fixed (bounded)** | EXP-016: 4 concurrent clients, 80 mixed turns, 0 failures; one forced `tony:7b` reload (22.41 s wall / 9.11 s Ollama load); fresh-process restart found both a verified arithmetic record and a user-provided memory record (write PID 1552, verify PID 12164); client RSS max 97 MB; system RAM max 83.9%. | Closed only for client lifecycle, DB persistence, model unload/reload and application restart. Production endurance, thermal telemetry and parallel throughput remain separate; see F-047. |
| F-047 concurrent inference throughput | **open** | EXP-016 ran 4 concurrent clients: general p50 rose from 5.52 s single-client to 25.80 s (~4.7x), server CPU utilisation ~0.31, 0 failures. The local model appears to queue requests. | No parallel speedup; need explicit Ollama parallel/batching configuration, queueing policy and a concurrency benchmark before claiming concurrent serving. |
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

The controller can call a hook and `LearningWorker` can run it off the answer path, but no shipped
command configures either one. A live session has no replay buffer of old verified material and no
bootstrapped stable checkpoint, so there is nothing DREAM can safely train or compare against. The
worker is an in-process daemon thread with a bounded queue: it captures job errors and cancels queued
work, but it does not persist jobs, force-kill a running job, survive a restart or coordinate across
processes.

**What would close it:** a configured replay source, an initial independently evaluated stable
checkpoint, a durable job store with a hard timeout/termination policy, and a restart test showing
the stable pointer and fast state behave as declared.

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

`FastWeights` and the DREAM candidate are NumPy associative memory. No `tony:7b` weight, adapter
or LoRA is trained. The target laptop (i7-1165G7, 16 GB RAM, MX350 2 GB) cannot fine-tune the 7.6 GB
Q4_K_M foundation; the 7B model already spills from the 2 GB GPU (F-014), and there is no verified
instruction-tuning corpus. Local-only fine-tuning would require a smaller model or an offline
adapter run with a separate measured pipeline. `tony:7b` is the only model under consideration; no
Qwen replacement is planned. Until then, EXP-013 must not be described as model self-improvement.

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
  failures, so the clients coexist but the local model queues requests (F-047). The language row in
  `config/module_costs.json` remains from the Ollama baseline because prompt/output lengths differ;
  routing priorities are still heuristic. Do not swap the routing estimates for these numbers
  without a routing experiment.
- **P64/P65:** semantic retrieval and the reasoning module are not built; the registry marks them
  unavailable. Do not advertise them.
- **P67:** `LearningWorker` now provides an opt-in bounded background queue with cancellation and
  error capture, but jobs are in-process only, non-durable and not configured by the CLI.
- **P68:** a failed language backend can still leave general questions unanswered; fallback must
  keep exact computation, retrieved evidence and generated answers distinct.
- **P69:** EXP-015 provides a 300-turn single-process sustained run (0 errors, ~1 MB RSS, 548 KB
  DB) and a cold-start `tony:7b` mixed load. EXP-016 adds 4 concurrent clients, 80 mixed turns, one
  forced reload and one fresh-process persistence check: 0 failures, general p50 25.80 s under
  concurrency, arithmetic p50 4.43 ms, client RSS max 97 MB. It is still not a production endurance
  test, thermal telemetry was unavailable, and parallel inference did not scale (F-047).
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
7. the response path survives a background training error; a process-level crash/restart is not
   covered by the in-process worker;
8. old-task performance is measured after a real task switch, not just on a frozen replay set.

Items 1-6 have targeted tests today. Item 7 is covered at the job-error level but not at the
process/restart level. Item 8 and the larger independent evaluation do not.

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
| F-043 model learning | A measured adapter/fine-tune of `tony:7b` on feasible hardware with a verified corpus and an NGR-style evaluation. | Hardware + data; not feasible on the current 2 GB GPU. |
| F-014/F-015/P48 | A better local foundation or an accepted accuracy limit; no new Qwen model. | Hardware/scope decision. |
| F-016/P55-P60 OCR | A labelled target-document corpus; CER/WER, field accuracy and confidence calibration. | Data. |
| P30-P44 BrainSim | Harder temporal tasks, hidden task/need labels, partial observations, independent distributions and more seeds. | Separate code + data effort. |
| P61-P63/P69 resources | EXP-015 measures the main non-language modules, a 300-turn sustained mix and a cold-start `tony:7b` mixed load; EXP-016 adds 4-client concurrency, a forced reload and a fresh-process persistence check with 80 turns and 0 failures. Still needed: production endurance, thermal telemetry and parallel inference (F-047). | Runtime measurements; partly done. |
| P64/P65 modules | A semantic-retrieval and reasoning implementation that beats the current baseline before routing to it. | Algorithm + benchmark; do not advertise early. |
| P67 background worker | In-process worker with queue bounds, cancellation and error capture is done; durable jobs, hard timeout, CLI wiring and restart tests remain. | Code + storage design. |
| P76-P80 engineering | One canonical spec, checkpoint/experiment manifests, clean-install verification and backup/restore tests. | Code/docs; can be done incrementally. |
| A04-A10 | Research programmes (hidden needs, segmentation, causal attribution, curriculum, self-preservation, forgetting). | Research; not a single patch. |

The previous sequence (green CI -> measured module costs and a sustained-load run -> larger frozen
benchmark -> background worker) is now implemented as EXP-015, EXP-014, EXP-016 and `learning/worker.py`.
EXP-016 closes the bounded F-046 scope; the next honest steps are:
durable/restartable worker jobs and CLI configuration (F-045) -> concurrent-inference queueing and
parallel-throughput work (F-047) -> independently authored benchmark/real usage data.
The AMA, adaptive-memory and BrainSim claims should stay conservative until their data exists.

## 9. Deliberately not doing now

- Do not replace FTS5 with a vector store because neural memory sounds advanced.
- Do not enlarge the model or add external APIs before the local pipeline is reliable.
- Do not tune the EXP-013/EXP-014 held-out sets until every seed promotes.
- Do not describe the NumPy candidate as language-model learning, continual learning or
  self-improvement.
- Do not claim consciousness, emotion or self-awareness from routing scores or resource rules.
