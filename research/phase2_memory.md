# Phase 2 - make memory reliable (P15-P29)

Status: **implemented and measured on the repair branch** (2026-11-05). Source register:
`research/problem_register.md`. This is a mechanism/measurement result on synthetic, author-written
data. It is **not** evidence of natural-language understanding or of an adaptive-memory advantage.

## What changed

| ID | Status | Implementation | Evidence |
|---|---|---|---|
| P15 | measured; default kept | `experiments/ama/calibrate.py` sweeps the discard threshold on useful/repeated/conflicting/unverified/noise records and reports precision/recall/F1. Best F1 1.0 at 1.6; default 0.45 preserves unverified audit rows (P15 decision below). | `experiments/ama/calibration.json` |
| P16 | fixed | Admission is one SQLite transaction instead of several commits; repeated tokenisation is cached. Mean admission on EXP-001: 1.40 ms vs 1.13 ms baseline (1.24x), down from the reported ~6x. Audit writes still cost; this is not a zero-overhead design. | `experiments/ama/results.json` |
| P17 | measured; audit kept | `AMA.storage_report()` reports payload bytes per table. EXP-001 at 0.45 is 1184 KB vs 931 KB (+27%); `admission_log` is ~308 KB of that, semantic facts ~99 KB, conflicts ~18 KB. The overhead is audit/derived evidence, not accidental duplication. Semantic fact text is no longer copied when it is identical to the source episode. | same, plus `test_storage_report_separates_audit_tables_from_records` |
| P18 | fixed (feedback path) | `memory_feedback` records retrieval hits, acceptance/rejection, task completion and corrections. `AMA.utility_from_feedback()` turns them into [0,1] utility; reliability/verification are never changed. Retrieval-hit logging is opt-in (`record_retrieval_feedback`) so the read path is not a write path by default. | `tests/test_phase2_memory.py::test_feedback_changes_utility_but_not_reliability` |
| P19 | fixed (rule-based) | `learning/compare.py` extracts numbers, dates and identifiers, normalises units (length/mass/time/volume/temperature, percent) and compares values. `1.5 km == 1500 m`, `May 6, 2024 == 2024-05-06`, `twenty three == 23`. No local encoder was adopted because the rule-based comparator already improves the labelled benchmark and the target hardware has no headroom for an unmeasured encoder. | `evaluation/contradiction_bench.py` (28 pairs, accuracy 1.00 vs 0.64 lexical baseline) |
| P20 | fixed (rule-based) | Negation is scoped per clause: a negated value/property is recorded, so "code is 4821" conflicts with "code is not 4821" even though token overlap is high. Unrelated negations do not cancel a positive clause. | same benchmark, `test_negation_scope_detects_clause_negation` |
| P21 | fixed | Dedicated `conflicts` table records question, both record ids/statuses/reliabilities, policy, resolution and timestamps. A new claim supersedes only when it is independently **verified** and strictly stronger than every old claim; two verified claims stay open. Reliability alone never resolves. `resolve_conflict()` requires an explicit explanation and, for supersession, a verified experience. | `test_conflict_index_keeps_both_records_and_is_queryable`, `test_verified_claim_supersedes_weaker_claim_under_explicit_policy`, `test_two_verified_claims_stay_in_review_not_auto_resolved` |
| P22 | measured; FTS5 stays default | Stress benchmark: adaptive memory is 0.997 exact at 100 facts, but 0.41 accuracy at 10 distractor tokens and related-accuracy 0.88 at 400 facts, while FTS5 stays 1.00. With IDF it beats no-memory; it does not beat FTS5. | `experiments/adaptive_memory/stress.json` |
| P23 | fixed (queue gate) | `drain_neural_queue()` requires verified status, a reliability floor, no unresolved conflict, bounded passes and a hard update cap. It snapshots the learned state first and restores it if the drain fails, so old associations remain recoverable. Rejected items are removed and logged as `NEURAL_UPDATE_REJECTED`; they are never silently learned. | `test_neural_queue_rejects_unverified_and_logs_it`, `test_neural_queue_conflict_is_not_written`, `test_adaptive_memory_snapshot_keeps_old_values_recoverable` |
| P24 | measured; interference remains | 8 rounds x 250 writes (~2,100 updates) across three task families: A accuracy 0.84 -> 0.33 -> 0.04 on switches, recovering to ~0.90 after retraining. This is catastrophic interference at the raw memory level, which is why the queue gate exists; the gate does not solve task switching. | `experiments/adaptive_memory/stress.json` |
| P25 | fixed | IDF is on by default and measured: exact recall 0.01 without IDF vs 0.997 with IDF on the same 100-fact task. Common tokens are down-weighted relative to rare ones (`test_idf_downweights_common_tokens`). | same stress file |
| P26 | fixed (continuous proxy) | `surprise_from_prior()` uses `answer_similarity()`, a continuous [0,1] comparison rather than 0/1 exact matching. Brier score 0.013 vs 0.381 for the lexical baseline on the labelled pairs; this is a proxy, not a calibrated probability. | `evaluation/contradiction_results.json` |
| P27 | fixed (policy + measurement) | Retention protects recently retrieved/used records in addition to verified/trusted/user entries; only old, unverified, unreinforced, unrelated records are forgotten. Benchmark: 100/100 intended records forgotten, 0 protected records forgotten, 0 stale FTS/fact rows, kept facts still retrievable. | `experiments/memory/results.json` |
| P28 | measured; default not changed | `ReplayBuffer.replay_set(policy="random"/"recent")` and a ratio sweep (0.25/0.5/0.75/1.0) were measured on the EXP-006 buffer. Every arm scored 1.00 new / 1.00 old retention, so this task cannot distinguish ratios or policies. No calibration claim; default stays 0.5. | `experiments/dream/replay_sweep.json` |
| P29 | fixed | `SemanticMemory.add_fact()` requires a source experience whose status is `verified`, checks the reliability floor, and stores verification method, provenance JSON, derivation text and source id. Deleting the source removes the fact (SQL trigger). Legacy facts are migrated with an explicit legacy derivation. | `test_semantic_memory_rejects_unverified_source`, `test_semantic_fact_preserves_provenance_and_is_deleted_with_source` |

## Measured results

### Admission calibration (P15)

Synthetic stream, 3 seeds, 120 projects: verified facts/rewordings (positive), contradicted claims,
novel unverified claims and unique noise (negative). Prediction = a record is newly admitted.

| threshold | precision | recall | F1 | negatives admitted |
|---:|---:|---:|---:|---:|
| 0.45 (default) | 0.350 | 1.000 | 0.519 | 294 |
| 1.00 | 0.644 | 1.000 | 0.784 | 88 |
| 1.40 | 0.994 | 1.000 | 0.997 | 1 |
| **1.60** | **1.000** | **1.000** | **1.000** | **0** |
| 1.80 | 1.000 | 0.998 | 0.999 | 0 |

Decision: **keep 0.45 as the default**. Raising it to 1.6 maximises precision on this synthetic
stream but discards *all* novel unverified experiences, which the design keeps for audit and later
review. The threshold is configuration, not a truth setting; any deployment that prefers a smaller
audit footprint can set 1.6 and re-measure on its own distribution.

### Answer comparison and contradiction detection (P19/P20/P26)

28 author-written pairs (`evaluation/contradiction_bench.py`): 14 equivalent (units, dates, number
words, rewordings) and 14 contradictory (digit changes, negation, hedges, entity swaps).

| comparator | accuracy | Brier |
|---|---:|---:|
| previous lexical / token parity | 0.643 | 0.381 |
| structured values + scoped negation | **1.000** | **0.013** |

This is a same-author benchmark and therefore optimistic. It does not test synonyms, entailment or
long paraphrase; those cases fall back to "conflict for review".

### Adaptive memory stress (P22/P24/P25)

100 facts, dim 256, 3 seeds unless noted; single seed for the long run.

| condition | adaptive | FTS5 |
|---|---:|---:|
| exact, 100 facts | 0.997 | 1.000 |
| related paraphrase, 400 facts | 0.880 | 1.000 |
| 2 distractor tokens | 0.950 | 1.000 |
| 5 distractor tokens | 0.770 | 1.000 |
| 10 distractor tokens | 0.410 | 1.000 |
| IDF off / on (exact) | 0.010 / 0.997 | - |

Long run: ~2,100 writes with task switches. Old-task accuracy fell from 0.84 to 0.04 after two
switches and returned to ~0.90 only after retraining. Direct contradictory writes overwrote the old
answer in 5% of 100 cases *without a gate*; the production path blocks those records before the
queue. Conclusion: **FTS5 remains the default**; the adaptive memory stays experimental and out of
the response path (D-009 stands).

### Retention (P27)

60-day-old synthetic records: 50 verified, 50 trusted, 50 user-provided, 100 unverified, 30
unverified with a recent retrieval hit, 20 reinforced unverified.

| measure | result |
|---|---:|
| intended unverified records forgotten | 100 / 100 |
| verified/trusted/user records forgotten | 0 |
| recently used or reinforced records forgotten | 0 |
| stale FTS / fact rows after deletion | 0 |
| kept verified fact still retrievable | yes |

Utility feedback is separate: a verified fact scored 0.60 after acceptance and 0.00 after rejection,
with reliability still 1.00. Utility ranks usefulness; it does not rewrite truth.

## Still open

- The calibration, contradiction and stress data are synthetic and mostly author-written.
- No local encoder or contradiction classifier was trained; the rule-based comparator is the
  measured option, not a claim of semantic understanding.
- Replay ratios/policies are indistinguishable on the small EXP-006 task; F-033/F-038 remain open.
- The adaptive memory still suffers severe task-switch interference; the queue gate prevents bad
  writes but is not a continual-learning solution.
- Conflict resolution has an API and an explicit policy. `learning/review.py` adds a minimal
  list/resolve CLI, but there is no UI, notification or queue prioritisation (F-039).
- AMA weights remain hand-set; only the discard threshold was swept. The 27% storage overhead is
  intentional audit/derived evidence, and no retention/compaction policy for `admission_log` exists.
