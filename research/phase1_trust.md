# Phase 1 - trust the learning path (P01-P14)

Status: **implemented and measured on the repair branch** (2026-11-05). This document records
what changed, how it is tested, and what is still not proven. The source register is
`research/problem_register.md`.

Completion condition from the review:

> ASHURA cannot promote or treat an unverified answer as verified merely because it passed
> through the response pipeline.

The controller now enforces this for the response/admission path: only an exact, independently
cross-checked answer may be stored as `verified`, and only `verified` records enter semantic
memory or the DREAM queue. Promotion is separately gated by a hardened NGR and a real DREAM
baseline. This is **not** a claim that the full learning loop is complete (see "Still open").

## What changed

| ID | Status | Implementation | Evidence |
|---|---|---|---|
| P01 | fixed | `AMA.retrieve()` filters records below `retrieval_min_reliability` (0.5) by default and labels everything it returns. Unverified model output (0.2) is no longer retrieval evidence. | `tests/test_phase1_trust.py::test_unverified_memory_is_not_retrieved_or_prompted` |
| P02 | fixed (retrieval path) | Every experience stores `source`, `verification_status`, `verification_method`, timestamp, `reliability` and conflict status (`related_ids`). `RetrievalItem` exposes them to the caller; the prompt labels verified / trusted / user-provided / unverified material. A model-generated reply is never marked verified even when arithmetic elsewhere in the turn was verified. | `test_verified_memory_is_retrieved_with_a_provenance_label`, `test_a_language_generated_response_cannot_borrow_arithmetic_verification` |
| P03 | fixed | `brain/verification.py` defines `VERIFIED`, `FAILED`, `UNAVAILABLE`. `Response.verification` carries the state; `Response.verified` remains the compatibility view (True / False / None). Only VERIFIED can enter verified queues. | `test_unavailable_verification_is_not_success`, `test_failed_verification_is_not_success` |
| P04 | fixed | `TraceStep.verification` records the factual state separately from `ok` (operational success). An unavailable verifier is `ok=True, verification="unavailable"`, not a success claim. | same tests plus `test_verified_arithmetic_marks_the_response_verified` |
| P05 | fixed (storage path) | A user correction/assertion is stored as its own immutable `user_provided` experience (`output=""`, `source="user"`). The assistant's generated reply is not relabelled and, on a correction turn, is not admitted as the correction. | `test_user_correction_is_stored_as_a_separate_user_provided_record`, `test_generated_answer_after_a_correction_is_never_labelled_user_corrected` |
| P06 | fixed | Reliability is provenance-specific: `verified` 1.0, `trusted_material` 0.8, `user_provided`/legacy `user_corrected` 0.6, `unverified` 0.2. User material is retrievable and labelled but cannot enter semantic facts, DREAM, or override verified/trusted evidence. | `test_reliability_is_provenance_specific_and_provenance_is_stored`, `test_only_verified_records_enter_semantic_memory` |
| P07 | interface fixed; full chain deferred | `CAGE.propose()` turns an allowed, independently verified decision into a bounded `UpdateProposal`; `plasticity/gated_update.py::GatedUpdater` is the consumer and only writes temporary fast state when the decision allows it. Candidate training -> NGR -> promotion is still the DREAM path, not connected to CAGE in the live controller. | `tests/test_cage.py::test_gated_updater_consumes_a_verified_authorisation`, `test_gated_updater_rejects_unverified_or_unattributed_signals` |
| P08 | fixed | CAGE receives `verified=True` only when the outcome is VERIFIED *and* the attributed module is covered by an independent verifier. An ordinary controller failure is `verified=False` and diagnostic-only. | `test_controller_attributes_arithmetic_failure_without_updating` |
| P09 | fixed | NGR rejects NaN and +/-infinity in scores and performance values before comparison. | `tests/test_ngr.py::test_nan_scores_are_rejected`, `test_infinite_scores_are_rejected`, `test_invalid_performance_values_are_rejected` |
| P10 | fixed (policy opt-in) | `NGRPolicy(require_performance=True)` requires every key in `required_performance` (default p95 latency and peak RAM); a missing or invalid measurement rejects. Old call sites remain valid. | `test_performance_is_required_when_the_policy_demands_it` |
| P11 | fixed | `MetricSpec` defines range, direction (`higher`/`lower`), minimum sample count and an optional per-capability epsilon. Required capabilities must exist in both baseline and candidate. | `test_out_of_range_scores_are_rejected`, `test_required_capability_must_be_measured`, `test_sample_counts_can_be_required_and_validated`, `test_lower_is_better_metric_direction` |
| P12 | fixed (measured) | `DreamConfig.initialization="stable"` loads the current stable memory and continues training from it; `"fresh"` starts from scratch. The experiment now measures all four arms: stable+new, stable+replay, fresh+new, fresh+replay. | `experiments/dream/results.json`, `tests/test_dream.py::test_stable_initialization_retains_old_capability_where_fresh_does_not` |
| P13 | fixed | The candidate answer vocabulary comes from the training split (or an explicit task specification), never from held-out items. | `test_answer_vocabulary_comes_from_training_not_heldout`, `test_explicit_answer_vocabulary_is_fixed_before_evaluation` |
| P14 | fixed | A missing stable checkpoint is no longer replaced by zero scores. `run()` refuses to promote unless an independently loaded baseline artifact (`cold_start_checkpoint`) exists and the candidate meets a separate `cold_start_min_target_accuracy`. | `test_dream_refuses_a_fake_zero_baseline`, `test_dream_promotes_candidate_then_rolls_back` |

## Measured results

### DREAM four-arm experiment (EXP-006)

Synthetic, 20 old + 20 new facts, held-out reordered variants, dim 256, single seed, NumPy
adaptive memory. All arms use the same stable baseline artifact and the same NGR policy
(`target="new"`, `min_target_gain=0.05`, epsilon 0.02). Vocabulary size 40 in every arm.

| arm | new | old retention | promoted | NGR |
|---|---:|---:|---|---|
| stable + new | 1.00 | **1.00** | yes | all conditions met |
| stable + replay | 1.00 | **1.00** | yes | all conditions met |
| fresh + new | 1.00 | **0.00** | no | regression on old: 1.000 -> 0.000 |
| fresh + replay | 1.00 | **1.00** | yes | all conditions met |

Interpretation: on this small task, starting from the stable memory preserves the old capability
without replay; fresh initialization needs replay to avoid catastrophic interference. The
experiment does **not** show that replay is unnecessary in general - stable+new and stable+replay
tied at 1.00 in a task where all old and new keys fit comfortably in the memory. It does show that
the promotion gate rejects a candidate that forgets the old capability, and that the four arms are
now measured rather than assumed.

### Real-model smoke test (tony:7b, target laptop)

One short manual run through the real controller (not a benchmark): `17*23` returned `391` in
1 ms with `verified=True`; a general language turn returned `Hello!` in 11.8 s including model
load (2.3-2.5 s warm); `remember that project z9 code is 4417` was stored as `user_provided` and a
later question retrieved it and answered `4417`. This checks the wiring and provenance path; it
does not add a new accuracy claim (the 16-item baseline remains EXP-000d).

### Conflict experiment (EXP-005, updated for the new reliability model)

| system | new value returned | old value returned | history kept |
|---|---|---|---|
| AMA + FTS5, independently verified over trusted_material | 1.00 | 0.00 | 100% |
| AMA + FTS5, user-provided correction (0.6) over trusted_material (0.8) | 0.00 | 1.00 | 100% |
| AMA + FTS5, unverified (0.2) over trusted_material | 0.00 | 1.00 | 100% |

A user correction is now review evidence, not a truth claim. This is deliberate: P06 says a user
supplied a statement, not proof of its factual truth. The verified correction pathway that can
eventually supersede a fact is CAGE -> bounded update -> candidate -> NGR, which remains Phase 3.

## Test evidence

- ASHURA: **204 passed** on Windows/Python 3.13 (`python -m pytest -q`).
- BrainSim: **46 passed** (unchanged; ASHURA does not import BrainSim).
- New Phase 1 tests: 12 in `tests/test_phase1_trust.py`, plus 7 NGR validation tests, 2 DREAM
  arm/vocabulary tests, 1 cold-start test, and 2 CAGE update-consumer tests.

## Still open (not claimed as fixed)

1. **Full CAGE -> candidate -> NGR promotion path (P07).** The gate and consumer exist and are
   tested, but the live controller does not turn a verified correction into a trained candidate.
   That is Phase 3, not Phase 1.
2. **Independent verification of natural-language user corrections (P05/P06).** A user statement
   is stored as `user_provided` (0.6); ASHURA has no independent verifier for arbitrary prose, so
   it cannot become `verified` by itself. This is an honest limitation, not a hidden success.
3. **Conflict index (P21).** Contradictory evidence is retained in the database but a weaker
   conflicting record is still stored outside the searchable index. A dedicated conflict index is
   Phase 2.
4. **AMA calibration (P15-P18).** Weights, thresholds, utility, and retrieval cutoff are not
   calibrated on a realistic stream. The 0.5 retrieval cutoff is a safety boundary, not a tuned
   optimum.
5. **NGR performance/sample requirements are opt-in.** A caller that does not set
   `require_performance=True` or `require_sample_counts=True` keeps the legacy behavior. The
   production promotion path should set both once real measurements exist.
6. **DREAM replay advantage is not established.** The four-arm result is a pipeline demonstration
   on one synthetic task, not evidence that replay is the best consolidation method in general.
7. **Adaptive neural memory remains out of the response path** and has no demonstrated advantage
   over FTS5 (F-007).
