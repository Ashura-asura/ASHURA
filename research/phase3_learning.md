# Phase 3 - complete the verified learning loop (P07/P08/P75, A01-A03)

Status: **implemented as an explicit, tested loop** (2026-11-05). Source register:
`research/problem_register.md`. This closes the missing connector between CAGE and DREAM/NGR, but it
is **not** a claim that ASHURA learns from arbitrary conversation. The loop trains the small NumPy
adaptive memory, not the language model, and the live controller only verifies arithmetic
corrections.

## What changed

| ID | Status | Implementation | Evidence |
|---|---|---|---|
| P07 | fixed as an explicit loop | `learning/loop.py::run_verified_correction` chains: verified correction -> CAGE attribution -> authorisation -> bounded proposal -> `GatedUpdater` fast update -> DREAM candidate -> NGR -> promotion/rollback. Each stage can refuse and returns its reason. | `tests/test_phase3_loop.py::test_verified_correction_promotes_through_cage_candidate_and_ngr`, `test_ngr_rejects_a_candidate_that_loses_old_capability` |
| P08 | preserved | CAGE still receives `verified=True` only from an independently checked outcome and an attributed module covered by its verifier. Unverified corrections create no proposal, no fast update and no candidate. | `test_unverified_or_untraced_correction_creates_no_candidate_and_no_fast_update`, `test_cage_does_not_authorise_an_unattributed_failure` |
| P75 | fixed (one bounded scenario) | EXP-013 runs observation/wrong reply -> user correction -> independent check -> CAGE -> fast update -> candidate -> NGR, including a promoted arm, an NGR-rejected arm and three refused arms. | `experiments/learning/loop.json` |
| P05/P06 | extended, not weakened | The raw correction is still admitted as a separate `user_provided` record with output `""`. Only a claim ASHURA checks independently (exact arithmetic) also produces a `verified` training record. A false arithmetic claim stays a user assertion and is not relabelled. | `test_verified_arithmetic_correction_is_stored_separately_from_the_reply`, `test_false_or_unverifiable_correction_never_becomes_verified` |
| A01 | partial (isolated) | `FastWeights` measures an immediate change: recall for `6*7` went from empty to `42` after the bounded update. The delta is temporary and not a language-model weight change. | `experiments/learning/loop.json` (`fast_recall_before/after`) |
| A02 | partial (isolated) | A candidate trained from verified data is evaluated by NGR against a real stable artifact. One arm is promoted; a no-replay arm is rejected and the stable pointer is unchanged. | same |
| A03 | partial | Fast state (`FastWeights`) and slow state (`CheckpointStore`) are separate: a rejected candidate leaves the stable checkpoint untouched while the temporary state still reflects the correction. | `test_ngr_rejects_a_candidate_that_loses_old_capability` |

## Correction verification

`learning/corrections.py` parses a correction and reports one of three states:

| claim | state | reason |
|---|---|---|
| `actually, 6*7 = 42` | verified | exact Fraction evaluation plus an independent Decimal(60) cross-check |
| `no, 6*7 = 43` | failed | the equation is false (`6*7 = 42`); not stored as verified |
| `actually, 2^10 = 1024` | unavailable | the Decimal cross-check does not cover `**` (P47) |
| `actually, the project p12 code is 9999` | unavailable | a user assertion is not independent evidence |

Only the verified arithmetic case produces a second, `verified` experience. The controller stores
the user's original sentence as `user_provided` in every case, and it never relabels the assistant's
reply.

## Measured results (EXP-013)

Synthetic old capability: 20 facts x train/held-out. Corrected capability: `6*7 -> 42` with two
held-out wordings. Stable checkpoint trained on the old capability only. Dim 128, single seed,
NumPy adaptive memory. This tests the control flow, not language understanding.

| arm | fast recall | old retention | corrected | NGR | outcome |
|---|---|---:|---:|---|---|
| verified + stable + replay | empty -> 42 | 1.00 | 1.00 | pass | **promoted** |
| verified + fresh + no replay | empty -> 42 | 0.00 | 1.00 | regression on old | **rejected; stable unchanged** |
| unverified factual correction | empty | - | - | not run | refused before attribution |
| false arithmetic correction | empty | - | - | not run | refused before attribution |
| verified correction, no trace | empty | - | - | not run | refused: cannot attribute |

The promoted candidate trains the adaptive memory only. The fast update is bounded and temporary;
the slow checkpoint changes only through NGR.

## Still open

- The loop is an explicit API/experiment, not automatically invoked by the live controller after
  every correction. The controller does not retain the previous execution trace, so it cannot
  attribute a later correction on its own.
- Factual corrections cannot be independently verified; only exact `+ - * /` equations are covered
  (P47). Power, modulo, roots and natural-language facts remain `user_provided`.
- The candidate is the NumPy adaptive memory, not Qwen; no language-model fine-tune or adapter is
  trained (D-009 stands).
- Single synthetic seed and a small author-written task; no claim of general fast adaptation or
  long-term consolidation.
- A production loop needs a reviewer decision for ambiguous corrections, trace retention and a
  background worker (P67/P75).
