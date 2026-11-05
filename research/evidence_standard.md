# Evidence standard

Status: 2026-11-05. This file states how ASHURA claims are separated from ASHURA requirements.

## Requirements are not demonstrations

The capabilities listed in `Goal.txt.txt` are **project requirements**. They are not evidence that
the architecture already works. A successful experiment supports only the narrow claim it measured;
it does not establish general intelligence, general learning or general capability retention.

## Memory is not capability change

The project must keep these mechanisms distinct:

| Mechanism | What changes | What the current evidence supports |
|---|---|---|
| SQLite memory | Stored experiences and facts | Storage and retrieval, including persistence across a process restart (EXP-016) |
| `FastWeights` | Temporary adaptive state | Short-lived adaptation inside one process; not persistent model learning |
| DREAM | Candidate consolidation process | A candidate is built and compared; it is not proof that a capability improved |
| Persistent neural parameters | Actual learned model parameters | The current candidate is the NumPy adaptive memory; EXP-017 shows it persists and retains old capability across a restart. Neither language checkpoint is trained by ASHURA. |
| `tony:7b-gpa3` / `tony:7b` weights | The language models' own parameters | User-supplied and unchanged by ASHURA; EXP-018 selects gpa3 as general tutor and tony:7b as privacy profile, which is model selection, not learning |

Therefore, remembering a correction and retrieving it later is **memory and retrieval**. It is not,
by itself, learning a new capability. The current verified-correction experiments are evidence about
the NumPy candidate and the safety gates, not evidence that `tony:7b` acquired new parameters.

## Four separate learning tests

A capability claim needs four separate tests:

1. **Remembering:** the system stores and retrieves the experience.
2. **Generalisation:** the system improves on a related, previously unseen example.
3. **Consolidation:** an independently verified change is written into persistent parameters.
4. **Retention:** previously learned capabilities do not regress after consolidation, and rollback
   restores the previous stable state.

Passing one test does not imply the others. In particular, EXP-013/EXP-014 exercise replay,
candidate training, NGR promotion and held-out wordings in the NumPy memory; they do not train
`tony:7b` and do not demonstrate a language-model capability improvement.

## Standard experiment record

Every algorithm or capability claim should record:

- **Hypothesis and baseline:** the claim, the comparator and the expected direction.
- **Implementation and configuration:** code path, model digest, flags and seeds.
- **Dataset and separation:** source, author, train/test/held-out split and leakage risks.
- **Resources:** CPU, RAM, storage, model footprint and runtime budget.
- **Latency:** distributions (p50/p95/p99/max), not only averages.
- **Accuracy and generalisation:** held-out results, not only replay of the training example.
- **Regression:** before/after capability checks and rollback behaviour.
- **Failures:** errors, empty answers, thermal or resource guards and negative findings.
- **Conclusion:** **supported**, **rejected** or **inconclusive**, with the exact scope.

Negative results count. A failed hypothesis that was tested properly is research evidence, not a
feature to hide. Do not tune a held-out set after inspection merely to force a promotion.

## Current application

- EXP-015/EXP-016 measure runtime behaviour; they do not establish learning.
- EXP-013/EXP-014 measure the verified-correction loop and its NumPy candidate; they do not train
  `tony:7b`.
- EXP-017 measures persistence, retention and rollback of a promoted NumPy candidate across a fresh
  process. It is evidence for the consolidation mechanism, not for language-model capability change.
- EXP-018 compares two user-supplied checkpoints on a frozen subject suite and selects a role split.
  It is model evaluation, not training and not a language-model capability change.
- F-042 (independent natural-language verification) and F-043 (an ASHURA-trained language-model
  adapter) remain blocked or open.
- F-046 is closed only for the bounded scope recorded in EXP-016: client lifecycle, database
  persistence, model unload/reload and process restart. Production endurance and parallel inference
  throughput remain separate.
