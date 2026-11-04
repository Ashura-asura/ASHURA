# ASHURA problem and remedy register

Saved from the 2026-11-05 source review. This is the working register for the repair
milestone; it is not a claim that every item is already fixed. The review covered
correctness, learning safety, evaluation validity and reliable operation. It was a
source-level review plus the documented experiments, not a fresh execution of every
experiment and not a formal security audit.

Status legend: **CRITICAL** = fix before trusting learning or promoting updates;
**HIGH** = fix before claiming the capability works; **MEDIUM** = improve after the
foundations are reliable. Implementation status is tracked in `research/phase1_trust.md`
(P01-P14) and `research/phase2_memory.md` (P15-P29).

## 1. Critical: learning safety and correctness

| ID | Problem | Best remedy |
|---|---|---|
| P01 | Unverified answers can enter searchable memory. Retrieval does not check reliability; AMA can index unverified responses. | Reliability-aware retrieval. Separate verified facts, unverified experiences, conflicting evidence and user-provided material. Never silently present an unverified answer as established memory. |
| P02 | A model can reinforce its own mistakes: an unverified answer is admitted, retrieved later and treated as evidence. | Provenance-aware retrieval. Every item carries source, verification method, timestamp, confidence and conflict status. Model-generated claims must not verify themselves. |
| P03 | Verification returning `None` is treated as success (`verified is not False`). | Strict three-state verification: VERIFIED, FAILED, UNAVAILABLE. Only VERIFIED may receive verified status or enter verified learning queues. |
| P04 | The verification trace marks unavailable verification as successful (`ok=verified is not False`). | Trace status must reflect the three-state result. Separate operational success from factual correctness. |
| P05 | A user correction can certify the assistant's response instead of the correction. The controller stores the generated response as `user_corrected`. | Store the user's correction as a separate immutable input. Verify and admit it independently. Never label the assistant response corrected merely because the user sent a correction. |
| P06 | `user_corrected` is automatically reliability 0.9. A correction is not necessarily true because a user supplied it. | Provenance-specific reliability. User-provided material is a record of what the user said; factual truth is classified separately. |
| P07 | CAGE authorises an update but no connected updater consumes the authorisation. | Controlled interface: verified correction → CAGE attribution → bounded update proposal → candidate training → NGR → promotion/rollback. |
| P08 | CAGE is called with `verified=False` for controller failures, so it cannot establish a verified correction pathway. | Feed independently verified outcomes into CAGE. An ordinary model failure must never become a training label. |
| P09 | NGR accepts non-finite evaluation values. | Reject NaN and ±infinity before any comparison. Validate score ranges, required capabilities and data completeness. |
| P10 | NGR silently skips performance checks when metrics are absent. | Require p95 latency and peak RAM when the policy demands them. Missing or invalid measurements reject promotion. |
| P11 | NGR does not validate scores against a defined range. | Define a metric schema: name, direction, permitted range, minimum sample count and tolerance. |
| P12 | DREAM always creates a fresh adaptive-memory model instead of starting from the stable model. | Measure explicit arms: stable+new, stable+replay, fresh+new, fresh+replay. Choose the consolidation method from the measurements. |
| P13 | DREAM derives its answer vocabulary from held-out data, leaking evaluation information. | Define the vocabulary before evaluation, from the task specification or training data. |
| P14 | DREAM compares against a fake zero baseline when no stable checkpoint exists. | Require an independently evaluated baseline before promotion. First-time initialization needs a frozen baseline and a separately defined acceptance criterion. |

## 2. High priority: memory and learning quality

| ID | Problem | Best remedy |
|---|---|---|
| P15 | AMA's discard branch is nearly unreachable with default weights. | Calibrate on realistic useful/useless/repeated/conflicting/unverified data; sweep thresholds and report precision/recall. |
| P16 | AMA admission is about 6× slower than store-everything. | Profile scoring, database, conflict lookup and indexing; cache repeated work. |
| P17 | AMA database growth is about 24% greater than store-everything. | Measure storage per admitted experience; remove redundant payloads. Do not sacrifice audit history blindly. |
| P18 | AMA utility is a heuristic proxy. | Measure utility from later retrieval success, user acceptance, repeated use, task completion and correction rates. Keep utility separate from correctness. |
| P19 | Answer comparison is not semantic understanding. | Structured value extraction, unit normalization and entity/date comparison; use a local encoder only if it improves held-out conflict detection. |
| P20 | Negation detection is simplistic token parity. | Structured rule-based comparison first; evaluate a local contradiction classifier against a labelled set. |
| P21 | Conflict resolution de-indexes older records when the new record has higher reliability. Reliability alone does not prove truth. | Keep conflicting evidence in a dedicated conflict index. Supersede only after independent verification and an explicit resolution policy. |
| P22 | Adaptive neural memory has no demonstrated advantage over FTS5. | Keep FTS5 default. Test semantic generalization, partial cues, noisy recall and capacity limits. Adopt only on a measured win. |
| P23 | Adaptive memory can overwrite a correct association with a wrong one. | Gate writes on verified evidence, confidence, conflict detection and bounded update size; keep old values recoverable. |
| P24 | Long-term interference from repeated adaptive-memory updates is untested. | Run thousands of sequential updates, task switches, contradictory writes and recall tests. |
| P25 | Hashed-token keys are dominated by common words. | Add IDF weighting or a better representation; compare with bag-of-words TF-IDF before a neural encoder. |
| P26 | Surprise compares only exact question/answer matches. | Calibrated prediction error across related inputs; separate novelty from lexical mismatch. |
| P27 | Forgetting thresholds are guessed. | Measure utility and retrieval frequency over time; test retention and recovery benchmarks. |
| P28 | Replay new/old ratio is not calibrated. | Compare ratios, sampling policies and capacities across distribution shifts; report acquisition and retention. |
| P29 | Semantic memory is not verified understanding; a status flag can make a fact "reliable". | Require explicit provenance and verification evidence; preserve the original episode and derivation path. |

### Phase 2 resolution (2026-11-05)

| ID | Status | Evidence / remaining gap |
|---|---|---|
| P15 | measured, default kept | EXP-009: 0.45 precision 0.35 / recall 1.00; 1.6 precision/recall 1.00 but discards unverified audit rows. Synthetic only (F-035). |
| P16 | fixed | 1.40 ms/item vs 1.13 baseline on EXP-001 (1.24x, was ~6x); one transaction + token cache. |
| P17 | measured, audit kept | +27% DB; `admission_log` ~308 KB, facts ~99 KB, conflicts ~18 KB; fact text deduplicated. |
| P18 | fixed | `memory_feedback`; utility separate from reliability; read-path logging opt-in. |
| P19/P20 | fixed (rule-based) | EXP-010: 1.00 vs 0.64 accuracy; units/dates/ids/negation. Not general semantics. |
| P21 | fixed | `conflicts` table; verified + strictly stronger only; explicit resolution API. |
| P22 | measured, FTS5 default | EXP-011: adaptive loses under noise/capacity; FTS5 1.00. |
| P23 | fixed (queue gate) | Verified + reliability + conflict + bounded update; rejected items logged. |
| P24 | measured, open | ~2,100 writes: task-switch accuracy 0.84 -> 0.04; gate does not solve interference (F-036). |
| P25 | fixed | IDF exact 0.997 vs 0.010 without. |
| P26 | fixed (proxy) | Continuous surprise; Brier 0.013 vs 0.381; not a calibrated probability. |
| P27 | fixed | 100/100 intended forgotten, 0 protected lost, 0 stale rows; recent use protected. |
| P28 | measured, not calibrated | All ratios/policies tie at 1.00 on EXP-006 (F-038). |
| P29 | fixed | Verified source required; provenance/derivation stored; cascade delete. |

### Phase 3 resolution (2026-11-05)

| ID | Status | Evidence / remaining gap |
|---|---|---|
| P05/P06 | extended | Raw correction remains `user_provided`; only an independently checked arithmetic equation adds a verified record. False facts stay user assertions. |
| P07 | fixed as an explicit loop | `learning/loop.py`: verified correction -> CAGE -> fast update -> DREAM -> NGR -> promote/rollback. Not yet invoked automatically by the controller (F-041). |
| P08 | preserved | CAGE still needs a verified outcome and a verifier-covered attributed module; unattributed failures produce no proposal. |
| P75 | fixed (one scenario) | EXP-013: promoted arm, NGR-rejected arm, three refused arms; stable pointer unchanged on rejection. |
| A01 | partial (isolated) | Fast recall for `6*7`: empty -> `42`; temporary NumPy state only. |
| A02 | partial (isolated) | Candidate trained from verified data passed/failed NGR against a real stable artifact. |
| A03 | partial | Fast `FastWeights` and slow `CheckpointStore` remain separate; rejected candidate leaves stable unchanged. Not a language-model fine-tune. |

Recommended separation: episodic (what happened, including uncertainty), verified
semantic (facts that passed an independent policy), and adaptive neural memory
(learned associations updated only through a gated process). These are not
interchangeable.

## 3. BrainSim: experimental validity and actual learning

| ID | Problem | Best remedy |
|---|---|---|
| P30 | B1 frozen unseen-rule accuracy is weak (~0.085). | Test rule inference from partial observations instead of relying on associative memory. |
| P31 | B1 fast memory interferes after task switches. | Task-boundary detection, confidence-aware isolation and learned reset decisions; test unknown boundaries. |
| P32 | B2 does not establish a recurrent advantage; GRU and fixed MLP both reach 1.000. | Genuinely temporal task: variable-length cues, distractors, delayed queries, changing relations, incomplete observations. |
| P33 | B2 evaluation is teacher-forced, not free-running. | Add autoregressive evaluation; keep teacher-forced loss as a diagnostic only. |
| P34 | B3 supplies task identity externally. | Hide task IDs; require inference from observations or uncertainty. |
| P35 | B3 uses verified writes, bypassing admission. | Run the full pipeline with incorrect, incomplete, conflicting and noisy observations. |
| P36 | B4 is a narrow controlled replay result. | Test partial replay, imbalanced streams, repeated shifts, delayed recall and limited storage. |
| P37 | B5 confidence targets do not match evaluation correctness. | Generate confidence labels with the same feasibility mask and resolution policy used at evaluation. |
| P38 | B5 is supervised imitation of a DP oracle, not RL. | Keep the label accurate; add an environment-driven experiment only if RL is a real objective. |
| P39 | B5 need labels are supplied by the environment. | Hide need labels at inference; test inference from observations, resource changes and outcomes. |
| P40 | B6 depends on full transition coverage and external task identity. | Test partial coverage, unseen task IDs, noisy transitions and incorrect retrieval. |
| P41 | B6 does not establish rule induction; 1.000 is consistent with lookup. | Tasks where memorizing every transition is impossible; compositional generalization. |
| P42 | BrainSim tasks are small and author-designed. | Independently generated distributions, adversarial generators, a held-out task family frozen before evaluation. |
| P43 | Three seeds are not strong statistical evidence. | More seeds where affordable, confidence intervals, and separation of descriptive from supported differences. |
| P44 | BrainSim is not integrated with ASHURA. | Integrate only after one measurable task shows an improvement; keep it behind an optional interface. |

B2's failure to show a recurrent advantage is a valid experimental result: the task
was too easy to justify recurrence.

## 4. Neural capability and specialist modules

| ID | Problem | Best remedy |
|---|---|---|
| P45 | HARN addition is linear least squares; 1.000 is expected for a linear function. | Do not present it as learned neural arithmetic. If pursued, test carries, longer numbers and unseen distributions. |
| P46 | The neural candidate adds no capability over exact arithmetic. | Keep exact arithmetic authoritative; remove the candidate from the normal path unless it shows a distinct advantage. |
| P47 | Independent verification covers only +, -, *, /. | Add verification for modulo, powers and roots with explicit precision and domain policies. |
| P48 | Qwen3.5-2B is weak at arithmetic and general benchmarks. | Route exact operations to deterministic tools; evaluate reasoning on a larger diverse benchmark before changing foundation. |
| P49 | The 16-question language benchmark is too small and single-author. | Larger benchmark, independent authors, difficulty levels, paraphrases, adversarial cases and task metrics. |
| P50 | The judge can under-credit valid answers that think aloud. | Separate exact-answer, semantic-equivalence and format-compliance metrics; audit a sample manually. |
| P51 | A model tag can point to a different artifact over time. | Pin digests, record configuration and benchmark metadata; treat a digest change as a new experiment. |
| P52 | Thinking-model output is not reproducible unless inference parameters are pinned. | Freeze think, num_predict, temperature, context length, seed where supported, and backend version. |
| P53 | The 7B model is large for the 2 GB target GPU. | Keep the 2B-class local foundation as the practical default; use 7B only as an offline reference if justified. |
| P54 | The llama.cpp adapter is not measured. | Benchmark against Ollama on identical files and settings before claiming an advantage. |

## 5. OCR and perception

| ID | Problem | Best remedy |
|---|---|---|
| P55 | No held-out real-document accuracy measurement. | Labelled target corpus; report CER, WER and exact-field accuracy. |
| P56 | Smoke success does not establish document accuracy. | Test low resolution, blur, skew, handwriting, tables, mixed languages, shadows and compression. |
| P57 | OCR confidence is not calibrated correctness. | Compare confidence with character/word errors; calibrate thresholds on held-out samples. |
| P58 | OCR corrections are stored but do not train a model. | Treat corrections as labelled data; validate and build a separate supervised experiment. |
| P59 | OCR language and performance coverage is unknown. | Measure each language on the target laptop, including runtime and memory. |
| P60 | OCR output can enter context without independent content verification. | Label it as extracted text, preserve confidence and image identity, and require confirmation for high-impact fields. |

## 6. Routing, resources and reliability

| ID | Problem | Best remedy |
|---|---|---|
| P61 | Many module costs are estimates. | Measure each module on the target laptop, cold and warm; record p50/p95 latency and incremental RAM. |
| P62 | Routing depends on heuristic priorities and thresholds. | Evaluate against always-run and task-quality outcomes, not execution frequency alone. |
| P63 | CPU/RAM load can still influence module selection. | Test sustained load, low memory and concurrency; explicit requests must not be silently deferred. |
| P64 | Semantic retrieval is not built. | Keep unavailable until a real implementation shows a measured gain over FTS5. |
| P65 | The reasoning module is not built. | Do not advertise it as implemented; define interface and benchmark first. |
| P66 | Learning is unavailable in the routing registry. | Make status explicit; enable only after the verified learning pipeline works. |
| P67 | AMA runs synchronously after generation. | Move expensive consolidation/training to a controlled background worker when lifecycle and data justify it. |
| P68 | A failed backend can leave ASHURA unable to answer general questions. | Improve fallback while distinguishing exact computation, retrieved evidence and generated answers. |
| P69 | Resource efficiency is not demonstrated over a sustained workload. | Long-duration test: latency, peak RAM, CPU, database growth, model load and recovery. |

## 7. Engineering, packaging and reproducibility

| ID | Problem | Best remedy |
|---|---|---|
| P70 | GitHub CI was added but had not run. | Confirm successful Actions runs on every configured OS and Python version. |
| P71 | CI does not cover Python 3.13. | Add 3.13, the locally reported version. |
| P72 | BrainSim CI only tests Ubuntu/3.12. | Add Windows if supported, or at least the exact target environment. |
| P73 | Test count is not independent verification of the current branch. | Run the full suite from a clean editable install on the latest commit; save SHA and logs. |
| P74 | CI does not establish real-model correctness. | Add an optional integration job with a pinned local model or deterministic mock, separate from unit tests. |
| P75 | No complete repeatable end-to-end learning test. | One small scenario: observation → verified correction → admission → candidate update → NGR → promotion/rollback. |
| P76 | Multiple specifications and older documents. | One canonical architecture spec and decision log; archive superseded ideas. |
| P77 | Checkpoints and experiment outputs need lifecycle management. | Naming, retention, manifests, hashes, provenance and cleanup policies. |
| P78 | Benchmark reproducibility depends on environment. | Save OS, Python, packages, CPU/GPU, model digest, inference settings, dataset hash, seeds and commit SHA. |
| P79 | Installation path needs clean-environment verification. | Test editable and normal install, package data, CLI from another directory and optional dependencies separately. |
| P80 | No demonstrated backup/recovery test for memory and checkpoints. | Backup, restore, corruption detection and recovery tests; keep database, FTS5, manifests and checkpoints consistent. |

## 8. Biggest architectural gaps

| ID | Missing capability | Best remedy |
|---|---|---|
| A01 | No demonstrated continuous neural weight learning during use. | Small isolated fast-plasticity network first; measure weight change and later improvement. |
| A02 | No proven persistent slow consolidation. | Train a candidate adapter/small model from verified replay; evaluate; promote or roll back. |
| A03 | No established fast-adaptation / persistent-learning separation in the model. | Keep fast state separate from slow weights; test adaptation, restart persistence and long-term retention. |
| A04 | No demonstrated independent inference of hidden needs. | Hide need labels; test prediction from observations, outcomes and resource changes. |
| A05 | No demonstrated learned task segmentation. | Hide task IDs; evaluate boundary detection, uncertainty and memory interference. |
| A06 | No demonstrated causal learning from execution traces. | Controlled interventions and counterfactual tests; do not mistake proximity for causality. |
| A07 | No demonstrated autonomous selection of what to learn. | Evaluate learning priority against future usefulness, uncertainty reduction and compute cost. |
| A08 | No validated dream/consolidation mechanism. | Separate offline replay laboratory; compare with no-dream and random-replay baselines. |
| A09 | No demonstrated resource-aware self-preservation. | Budgets, expected costs, risk estimation and recovery rules; treat as control engineering, not subjective fear. |
| A10 | No proven protection against all catastrophic forgetting. | Multi-task benchmark with new distributions, partial replay, limited memory and repeated switches. |

## 9. Repair order

**Phase 1 — make learning trustworthy.** Tri-state verification, user-correction
handling, reliability-aware retrieval, no unverified generated material in verified
training, NGR hardening, tests proving failed candidates cannot replace stable
checkpoints.

**Phase 2 — make memory reliable.** Separate verified facts, unverified episodes and
conflict evidence; provenance; calibrate AMA; benchmark FTS5 against adaptive memory;
long-run interference and forgetting.

**Phase 3 — complete the learning loop.** CAGE to a bounded updater; DREAM from a
defined baseline; remove held-out leakage; candidate training to NGR; test fast
adaptation and slow consolidation separately.

**Phase 4 — strengthen BrainSim.** Temporal B2, hidden task IDs, B5 confidence labels,
partial observations, more seeds and independent distributions.

**Phase 5 — integrate only proven capabilities.** One defined API, measured latency/RAM,
end-to-end and long-duration tests, tested fallback.

## 10. Tests required before calling the learning loop complete

| Test | Expected result |
|---|---|
| Unverified wrong answer enters memory | Never becomes a verified fact |
| User corrects a wrong answer | The correction is stored, not the assistant's previous response |
| Verifier unavailable | No verified admission or promotion |
| Candidate contains NaN | NGR rejects it |
| Candidate lacks an old capability score | NGR rejects it |
| Candidate improves target but damages a critical capability | NGR rejects it |
| Candidate fails evaluation | Stable checkpoint unchanged |
| New verified fact is admitted | Relevant retrieval caches update |
| Contradictory claim arrives | Both sources remain auditable |
| Restart after fast learning | Fast state matches its declared persistence policy |
| Restart after slow consolidation | Promoted parameters remain available |
| New task arrives | Old-task performance is measured after the switch |
| Training data contains a false correction | It is not automatically learned as truth |
| Background training crashes | Response path and stable model remain usable |

## 11. Deliberately not doing now

- Do not replace FTS5 with a vector database because neural memory sounds advanced.
- Do not expand HARN until exact arithmetic is demonstrably insufficient.
- Do not enlarge the model before the learning pipeline is reliable.
- Do not integrate BrainSim until it has a measured advantage.
- Do not add memory categories before reliability boundaries work.
- Do not rebuild the architecture from scratch.
- Do not claim consciousness, emotion or self-awareness from risk scores, recurrent
  state or resource-management behaviour.

## Final verdict

ASHURA is a research prototype, not a validated continual-learning system. The
engineering foundation has improved, but the verified learning loop, memory
reliability, independent evaluation and persistent neural adaptation are not yet
proven. The highest-risk problem is not that ASHURA cannot learn; it is that it does
not yet reliably know when what it has learned deserves to be trusted.
