# EXP-017 - Consolidation persistence and retention across a process restart

Date: 2026-11-05. Status: **supported for the NumPy adaptive-memory candidate; not evidence of
`tony:7b` learning.**

## Hypothesis and baseline

Hypothesis: a verified arithmetic correction can train a NumPy candidate, pass NGR, be promoted to
the stable checkpoint, and then be loaded by a fresh process that still solves the corrected
held-out wordings, retains the old capability, and can roll back to the parent checkpoint.

Baseline: EXP-014 measured 50/50 replay promotions and 150/150 held-out wording predictions inside
one process. EXP-017 adds the restart, retention and rollback check.

## Implementation and configuration

- Runner: `experiments/learning/persistence_bench.py`
- Dataset: `experiments/learning/corrections_v1.json` (10 frozen, author-written arithmetic cases)
- Seeds: 0 and 1; 10 cases x 2 seeds = 20 runs
- Candidate: NumPy `AdaptiveMemory`, dimension 128, stable initialization, replay enabled
- Gate: `NGRPolicy("corrected", min_target_gain=0.5)`
- Store: `CheckpointStore` with a stable pointer, immutable promoted artifact and parent history
- Fresh-process check: one `python -m experiments.learning.persistence_bench --verify` child per
  promoted candidate
- Environment: Windows 11, Python 3.13.14, local CPU only

## Dataset and separation

The 10 correction cases are author-written. Each case has one training key and three held-out
wordings. The old capability has 20 training items and 20 differently-worded held-out items. The
held-out wordings share expression tokens with the correction key, so this is a non-regression and
persistence benchmark, not an independent capability estimate.

## Results

| Measurement | Result |
|---|---|
| Promotions | 20/20 |
| Fresh-process checks | 20/20 |
| Stable artifact name and SHA-256 match after restart | 20/20 |
| Corrected held-out predictions after restart | 60/60 (1.00) |
| Old-capability held-out predictions after restart | 400/400 (1.00) |
| Rollbacks restoring the parent `old_memory.npz` | 20/20 |
| Parent checkpoint after rollback | old 20/20 per run; corrected 0/3 per run |
| Stable artifact size | max 131.1 KB |
| Write time | p50 48.219 ms |
| Fresh-process verify time | p50 33.241 ms |
| ASHURA RSS | max 41.2 MB |
| Total wall time | 6.25 s |

## Accuracy and generalisation

The promoted candidate predicted all 60 corrected held-out wordings and all 400 old-capability
held-out wordings after a process restart. This demonstrates persistence and retention for this
NumPy candidate on this author-written set. It does **not** demonstrate generalisation to an
independent distribution, and it does not demonstrate a language-model capability change.

## Regression and rollback

Rollback changed only the stable pointer, not the artifact. In every run the parent checkpoint
returned old-capability accuracy 1.00 and corrected accuracy 0.00, which is the expected pre-learning
state. This is a pointer-level rollback test, not a backup/restore or corruption-recovery test.

## Failure analysis

- No run failed to promote, load, evaluate or roll back.
- The experiment does not test a power loss, a half-written artifact, a corrupt manifest, a shared
  database or concurrent writers.
- The fresh process is a child of the same test runner, not a machine reboot.
- The candidate is the NumPy memory; `tony:7b` weights are untouched.
- The corpus is author-written and the held-out wordings are not independently authored.

## Conclusion

**Supported** for the bounded claim: a promoted NumPy candidate persists across a process restart,
retains the old capability, and can be rolled back. **Not supported:** persistent learning in
`tony:7b`, independent generalisation, or production durability.

F-043 (language-model fine-tune/adapter) remains open. A02/A03 move from "partial (isolated)" to
"measured for the NumPy candidate, not the language foundation."

Raw data: `experiments/learning/persistence.json`.
