# Project completion audit

Status: 2026-11-06, after EXP-016, EXP-017, EXP-018, EXP-018b and F-045. This file is an evidence
audit, not a claim that ASHURA is 87.5% intelligent or 87.5% of the way to general capability.

## Method

The score uses the 36 applicable checklist items in `Goal.txt.txt` section 22, "Final acceptance
criteria". Each item is scored:

- **Full = 1.0:** implemented and supported by a recorded test or experiment.
- **Partial = 0.5:** implemented or measured, but a named gap prevents the full claim.
- **Not done = 0.0:** absent or unsupported.

The optional vector-retrieval item is excluded because vector retrieval was not adopted; FTS5
remains the default. All other items are equally weighted. The resulting percentage is **checklist
coverage**, not a measure of intelligence, generality or production readiness.

## Completion by area

| Area | Applicable items | Full | Partial | Not done | Completion |
|---|---:|---:|---:|---:|---:|
| Foundation | 4 | 3 | 1 | 0 | **87.5%** |
| Memory | 5 | 5 | 0 | 0 | **100%** |
| Cognitive controller | 4 | 4 | 0 | 0 | **100%** |
| Learning | 5 | 2 | 3 | 0 | **70%** |
| DREAM and NGR | 5 | 5 | 0 | 0 | **100%** |
| Specialist skills | 4 | 2 | 2 | 0 | **75%** |
| Resource efficiency | 4 | 3 | 1 | 0 | **87.5%** |
| Research record | 5 | 3 | 2 | 0 | **80%** |
| **Total** | **36** | **27** | **9** | **0** | **87.5%** |

The total is `(27 + 0.5 x 9) / 36 = 31.5 / 36 = 87.5%`.

## Why the partial items are partial

| Area | Partial item | What is missing |
|---|---|---|
| Foundation | Documented, reproducible language checkpoint | `tony:7b-gpa3` (general) and `tony:7b` (privacy) are pinned by digest; temperature, seed, top_p, context and token limit are pinned for EXP-018, and Ollama 0.40.14 is recorded there. The backend version is not locked in config, and licence/dataset provenance remains user-supplied and unverified (P51/P52). |
| Learning | Fast adaptive memory works | It works in isolation and can be reset, but has no measured advantage over FTS5 and is not in the response path (F-037). |
| Learning | Slow consolidation works | EXP-017 persists a promoted **NumPy** candidate; EXP-018 evaluates the user-supplied gpa3/tony checkpoints but ASHURA trains no adapter or fine-tune (F-043). |
| Learning | Generalisation on unseen examples | EXP-014/EXP-017 use author-written held-out wordings that share expression tokens with the correction key (F-044). |
| Specialist skills | OCR works locally | Local Tesseract pipeline and smoke test exist; no held-out real-document CER/WER measurement (F-016/P55-P60). |
| Specialist skills | Specialist outputs can be verified | Exact arithmetic is verified; OCR is unverified and HARN is a non-authoritative linear candidate. |
| Resource efficiency | System remains usable on target hardware | Single-client works; four clients raised general p50 from 5.52 s to 25.80 s and RAM peaked at 83.9% (F-047). |
| Research record | Every algorithm has a hypothesis | Major algorithms are documented; some modules and BrainSim items still lack a full standard record. |
| Research record | Every algorithm has a baseline | Many do; OCR and several specialist/BrainSim paths still lack an independent baseline. |

## The core objective is separate from the checklist

The central research claim is not "the modules exist". It is: **verified experience produces a
measurable, persistent capability improvement in the language foundation while previous
capabilities are retained.** That claim is not captured by the 87.5% checklist score.

| Learning test | ASHURA memory / NumPy candidate | `tony:7b-gpa3` / `tony:7b` language foundation |
|---|---|---|
| Remembering | **Yes** — SQLite storage and retrieval survive a process restart (EXP-016) | **No** — no language-model memory change |
| Generalising | **Partial** — 150/150 held-out wordings in EXP-014; author-written and token-overlapping | **No** |
| Consolidating | **Yes, bounded** — EXP-017 loaded 20/20 promoted NumPy candidates in a fresh process | **No** — no adapter, LoRA or weight update |
| Retaining | **Yes, bounded** — 400/400 old-capability predictions and 20/20 rollbacks after restart | **No** |

**Persistent language-model capability change: 0 of 4 tests demonstrated.** This is the honest
headline. The 87.5% figure measures how much of the engineering checklist has evidence; it does not
mean the central learning objective is 87.5% achieved.

## What would move the score

| Next step | Expected change | Main blocker |
|---|---|---|
| Explicit concurrent-inference configuration and benchmark (F-047) | One partial becomes full: +1.4 points | Local model queueing |
| Held-out OCR corpus (F-016) | One partial becomes full: +1.4 points | Labelled data |
| Independently authored correction set (F-044) | One partial becomes full: +1.4 points | Independent authorship |
| ASHURA-trained adapter/LoRA experiment (F-043) | Moves the core language-learning tests, not just the checklist | 4.7 GB model vs 2 GB GPU; verified corpus |

The largest remaining risk is not a missing module. It is claiming that memory persistence or a
NumPy candidate promotion proves that the language foundation learned a new capability. It does not.

## Evidence

- `research/EXP-016_real_soak.md` — memory persistence, reload and bounded concurrency.
- `research/EXP-017_persistence.md` — NumPy consolidation persistence, retention and rollback.
- `research/EXP-018_subject_tutor.md` — frozen subject comparison and the agentic3 follow-up.
- `research/EXP-014` in `research/experiment_log.md` — held-out correction benchmark.
- `tests/test_worker_durability.py` — durable store, crash recovery, hard timeout and CLI config.
- `research/evidence_standard.md` — requirements-vs-capabilities and the four learning tests.
- `open_problem.md` — F-043, F-047 and the independent-evaluation gaps.
