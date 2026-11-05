# Phase 3 - complete the verified learning loop (P07/P08/P75, A01-A03)

Status: **implemented as an explicit, tested loop with an opt-in controller hook and an in-process
background worker** (2026-11-05). Source register: `research/problem_register.md`. This closes the
missing connector between CAGE and DREAM/NGR and lets the controller attribute a correction to the
preceding execution, but it is **not** a claim that ASHURA learns from arbitrary conversation. The
loop trains the small NumPy adaptive memory, not the language model, and only exact arithmetic
corrections are independently verifiable.

## What changed

| ID | Status | Implementation | Evidence |
|---|---|---|---|
| P07 | fixed as an explicit loop | `learning/loop.py::run_verified_correction` chains: verified correction -> CAGE attribution -> authorisation -> bounded proposal -> `GatedUpdater` fast update -> DREAM candidate -> NGR -> promotion/rollback. Each stage can refuse and returns its reason. | `tests/test_phase3_loop.py::test_verified_correction_promotes_through_cage_candidate_and_ngr`, `test_ngr_rejects_a_candidate_that_loses_old_capability` |
| P08 | preserved | CAGE still receives `verified=True` only from an independently checked outcome and an attributed module covered by its verifier. Unverified corrections create no proposal, no fast update and no candidate. | `test_unverified_or_untraced_correction_creates_no_candidate_and_no_fast_update`, `test_cage_does_not_authorise_an_unattributed_failure` |
| P75 | fixed (one bounded scenario) | EXP-013 runs observation/wrong reply -> user correction -> independent check -> CAGE -> fast update -> candidate -> NGR across seeds 0-4, including the replay and no-replay arms and three refused arms. | `experiments/learning/loop.json` |
| F-041 | fixed at controller level; residual lifecycle work | `Controller` retains the last non-correction `ExecutionTrace` and accepts an optional `correction_loop` hook, invoked only for a verified correction. Hook errors are recorded, never raised into the reply. | `test_controller_invokes_the_loop_on_the_previous_trace_after_a_correction`, `test_loop_hook_failure_never_breaks_the_reply` |
| P67 | implemented, opt-in | `learning/worker.py::LearningWorker` owns one daemon thread and a bounded queue. `submit()` never raises; queued jobs can be cancelled; running jobs are not force-killed; `stop()` drains. The controller returns the `job_id` in `Response.correction["loop"]`. | `test_learning_worker_runs_a_job_and_records_its_result`, `test_learning_worker_refuses_new_work_when_its_queue_is_full`, `test_controller_hands_a_verified_correction_to_the_background_worker` |
| F-039 | minimal reviewer workflow | `learning/review.py` lists open/all conflicts and resolves one with a reason; superseding still requires a verified experience. No UI or notification. | `test_review_workflow_lists_and_dismisses_a_conflict` |
| P05/P06 | extended, not weakened | The raw correction is still admitted as a separate `user_provided` record with output `""`. Only a claim ASHURA checks independently (exact arithmetic) also produces a `verified` training record. A false arithmetic claim stays a user assertion and is not relabelled. | `test_verified_arithmetic_correction_is_stored_separately_from_the_reply`, `test_false_or_unverifiable_correction_never_becomes_verified` |
| A01 | partial (isolated) | `FastWeights` measures an immediate change: recall for `6*7` went from empty to `42` in 5/5 seeds after the bounded update. The delta is temporary and not a language-model weight change. | `experiments/learning/loop.json` (`fast_recall_before/after`) |
| A02 | partial (isolated) | A candidate trained from verified data is evaluated by NGR against a real stable artifact: 4/5 seeds promoted, 5/5 no-replay rejected in EXP-013; EXP-014 promoted 50/50 replay runs and rejected 50/50 no-replay runs. One EXP-013 seed was refused because the stable baseline accidentally already scored 1.00 on the corrected held-out set. | `experiments/learning/loop.json`, `experiments/learning/correction_bench.json` |
| A03 | partial | Fast state (`FastWeights`) and slow state (`CheckpointStore`) are separate: a rejected candidate leaves the stable checkpoint untouched while the temporary state still reflects the correction. | `test_ngr_rejects_a_candidate_that_loses_old_capability` |

## Correction verification

`learning/corrections.py` parses a correction and reports one of three states:

| claim | state | reason |
|---|---|---|
| `actually, 6*7 = 42` | verified | exact Fraction evaluation plus an independent Decimal(60) cross-check |
| `no, 6*7 = 43` | failed | the equation is false (`6*7 = 42`); not stored as verified |
| `actually, 2^10 = 1024` | verified | independent Decimal(60) check now covers integer powers (P47) |
| `actually, 10%3 = 1` | verified | independent Decimal(60) check now covers modulo, including floor semantics |
| `actually, sqrt(144) = 12` | verified | independent Decimal(60) check now covers perfect-square roots |
| `actually, sqrt(2) = 1.41421356` | unavailable | irrational roots have no exact rational value |
| `actually, 2 ** 0.5 = 1.41421356` | unavailable | fractional exponents are outside the exact domain |
| `actually, the project p12 code is 9999` | unavailable | a user assertion is not independent evidence |

Only the verified arithmetic case produces a second, `verified` experience. The controller stores
the user's original sentence as `user_provided` in every case, and it never relabels the assistant's
reply. If a Decimal(60) operation exceeds the cross-check's precision (for example a modulo whose
quotient has more than 60 digits), the state is `unavailable`, not `verified`.

## Measured results (EXP-013)

Synthetic old capability: 20 facts x train/held-out. Corrected capability: `6*7 -> 42` with two
held-out wordings. Each seed gets its own stable checkpoint trained on the old capability only.
Dim 128, seeds 0-4, NumPy adaptive memory. This tests the control flow, not language understanding.

| arm | fast recall | old retention (mean) | corrected (mean) | outcome across 5 seeds |
|---|---|---:|---:|---|
| verified + stable + replay | 5/5 empty -> 42 | 1.00 | 1.00 | **4/5 promoted, 1/5 candidate rejected** |
| verified + fresh + no replay | 5/5 empty -> 42 | 0.02 | 1.00 | **0/5 promoted; all rejected on old-capability regression; stable unchanged** |
| unverified factual correction | 0/5 | - | - | refused before attribution in 5/5 |
| false arithmetic correction | 0/5 | - | - | refused before attribution in 5/5 |
| verified correction, no trace | 0/5 | - | - | refused: cannot attribute in 5/5 |

The promoted candidate trains the adaptive memory only. The fast update is bounded and temporary;
the slow checkpoint changes only through NGR.

The multi-seed run exposed a measurement problem rather than a loop bug. The stable memory already
scored 1.00 on the corrected held-out items in seed 3 (and 0.50 in seeds 1 and 4) because the
hashed associative memory can accidentally return the right value for an unseen key. The stable
baseline's corrected mean was 0.40, so the seed-3 candidate had zero measured target gain and NGR
correctly refused promotion. The tiny two-item held-out set makes both the baseline and the gate
noisier than the single-seed result suggested; do not read 4/5 as a generalisation estimate.

## Larger frozen benchmark (EXP-014)

`experiments/learning/correction_bench.py` loads `corrections_v1.json`, re-checks every arithmetic
correction with `skills.arithmetic.exact`, and runs ten cases with three held-out wordings each.
The cases cover multiplication, addition, subtraction, division, integer powers, modulo,
perfect-square roots, decimals and parentheses. Seeds 0-4, two arms, five controls.

| measurement | result |
|---|---|
| verified + stable + replay | **50/50 promoted**; promotion-rate 95% Wilson CI [0.929, 1.000] |
| target score / old score | 1.00 / 1.00 mean (stable target 0.00; 0 accidental stable hits) |
| held-out wording predictions | 150/150 correct |
| fast recall after update | 50/50 correct |
| verified + fresh + no replay | **0/50 promoted**; old score 0.029 mean; stable pointer unchanged |
| control probes (false arithmetic, unverified fact, irrational root, no trace, unattributable) | **25/25 refused**; 0 fast updates, 0 new candidates, 0 stable changes |

This is a larger control-flow and non-regression check, not a capability benchmark. The corpus is
author-written, the held-out wordings share the expression tokens with the correction key, and the
candidate is the hashed NumPy memory. It improves on EXP-013's two wordings and one expression, but
it does not supply an independent author or an independent distribution.

## Measured module costs (EXP-015)

`experiments/runtime/load_bench.py` measures the runtime path on the target Windows 11 laptop
(Python 3.13, 8 logical CPUs). It uses `EchoModel`, so the controller numbers exclude `tony:7b`.

| module | measurement |
|---|---|
| exact arithmetic evaluate (slowest case) | p50 0.015 ms |
| exact Decimal(60) cross-check | p50 0.007-0.012 ms |
| AMA admission (200 records, synthetic) | p50 1.15 ms, p95 1.57 ms |
| FTS5 search / AMA retrieve (200 records) | p50 0.25 / 0.30 ms |
| controller arithmetic turn (EchoModel) | p50 ~1.1 ms, p95 ~2.0 ms; 40/40 exact-verified |
| full NumPy correction loop job | p50 ~22 ms, p95 ~26 ms |
| worker submit / 100 no-op jobs drained | p50 0.004 ms / 1.84 ms total |
| 300-turn sustained mix | p50 ~1.2 ms, p95 ~1.7 ms, 0 errors, ~1 MB RSS, 548 KB DB |

The sustained run is single-process and synthetic: 240 of 300 turns were arithmetic with no
language model. It does not establish `tony:7b` sustained latency, concurrency safety, restart
recovery or production database growth. Full data: `experiments/runtime/results.json`.

## Still open

- The loop is opt-in. The controller retains the previous trace and can call a `correction_loop`
  hook, but the CLI does not configure a replay corpus or a stable checkpoint, so a live session
  still does not learn automatically.
- The worker is in-process and non-persistent: queued/running jobs are lost if the process exits,
  and a running job has no forced timeout or kill. A restart test and a durable job store are still
  missing.
- Factual corrections cannot be independently verified. Arithmetic coverage now includes
  `+ - * / %`, integer powers and perfect-square roots; irrational roots, non-integer powers and
  arbitrary prose remain `user_provided` (F-042).
- The candidate is the NumPy adaptive memory, not `tony:7b`; no language-model fine-tune or
  adapter is trained (D-009 stands).
- EXP-014 is larger but still author-written, with held-out wordings that share expression tokens.
  It is a non-regression and control-flow benchmark, not a capability estimate (F-044).
- A production loop needs a reviewer UI/queue, durable job storage and CLI configuration
  (F-039/P67/P75). The CLI in `learning/review.py` only lists and resolves conflicts.
