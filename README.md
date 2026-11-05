# ASHURA

Adaptive Self-modifying Hierarchical Unified Reasoning Architecture, built from
`spec/New_approach.txt` and the v2 blueprint `spec/New_approach_2.txt`.

**Status:** Phase 0 foundation baseline measured on the target laptop; Phases 1–6 implemented;
Phase 1 trust repair (P01–P14), Phase 2 memory reliability (P15–P29) and Phase 3 verified-correction
loop (P07/P75/A01–A03) implemented and tested; local OCR and a HARN arithmetic candidate are
integrated behind optional dependencies/checkpoints; BrainSim B1–B6 measured as an independent
subproject. **264 ASHURA tests and 46 BrainSim tests pass.** The adaptive memory remains
experimental and out of the response path. BrainSim is not imported by ASHURA. The learning loop is
**not** complete: it is an opt-in controller hook with an in-process background worker, only exact
arithmetic corrections are independently verified, and the candidate is the NumPy memory rather
than the language model.

## Run

```bash
pip install -e ".[dev]"                   # or: pip install psutil numpy pytest
python -m pytest -q                       # 264 tests
python -m app.main --trace                # CLI (echo stub until a real model is configured)
# at the prompt: /ocr <image path>, /help, /quit   (the installed command is `ashura --trace`)
python -m experiments.ama.run             # EXP-001  AMA vs store-everything
python -m evaluation.retrieval_bench      # EXP-002  FTS5 latency vs size
python -m experiments.nfd.run             # EXP-003  NFD vs always-run
python -m experiments.adaptive_memory.run # EXP-004  neural adaptive memory vs FTS5
python -m experiments.adaptive_memory.conflict  # EXP-005  same-key conflicts
python -m experiments.dream.run           # EXP-006  DREAM replay vs new-only
python -m experiments.ama.calibrate       # EXP-009  AMA threshold/cost/storage
python -m experiments.adaptive_memory.stress     # EXP-011  adaptive memory under stress
python -m experiments.dream.replay_sweep  # EXP-012  replay ratio/policy sweep
python -m experiments.memory.retention_bench     # EXP-012  retention/utility
python -m experiments.learning.loop_e2e   # EXP-013  verified correction -> NGR
python -m experiments.learning.correction_bench  # EXP-014  larger frozen correction benchmark
python -m experiments.runtime.load_bench  # EXP-015  module costs + sustained load
python -m learning.review list --db data/ashura.db          # open conflicts
python -m learning.review resolve <id> --db data/ashura.db --reason "reviewed"
python -m evaluation.contradiction_bench  # EXP-010  structured answer comparison
python -m evaluation.ollama_baseline      # PHASE 0   real-model baseline
python -m memory.retention --db data/ashura.db   # forgetting policy dry run
```

## Hardening pass

The 2026-11-05 hardening pass added 38 regression tests (139 -> 177). It fixes reproducible
failure modes without changing the measured research claims:

- **CLI:** huge exact results are formatted instead of crashing; dates and phone numbers are no
  longer treated as verified arithmetic; an explicit `/ocr` is not deferred by CPU/RAM load;
  `/help` and `/quit` work; one bad request does not kill the session.
- **Memory/backend:** a failed language backend degrades to exact arithmetic or retrieved memory
  instead of crashing, and its error text is not learned; admitting a new fact invalidates stale
  cached retrievals; SQLite gets a busy timeout, WAL, an indexed conflict lookup and an automatic
  `input_norm` migration.
- **Files/packaging:** `pip install -e .` works and exposes `ashura`; config discovery works from
  another directory; checkpoint names cannot traverse paths, promotion is atomic and refuses to
  overwrite different stable content; adaptive-memory saves are atomic and seed-checked; OCR has a
  child timeout.
- **Config/experiments:** unknown `[foundation]` keys are clear errors; the `[retention]` section
  is honoured; all model tags are benchmarked even if one non-reference model fails.

Details are in `research/failures.md` F-020–F-040. The `.github/workflows/ci.yml` workflow runs
ASHURA on Ubuntu/Windows with Python 3.11-3.13 and BrainSim on Ubuntu/Windows; BrainSim now installs
`psutil`, the missing dependency that failed the earlier runs. Actions run `41938499183` passed all
eight jobs on commit `17568c3`.

## Phase 1 trust repair (P01–P14)

The 2026-11-05 Phase 1 pass makes the response-to-learning path conservative:

- **Tri-state verification.** `VERIFIED` / `FAILED` / `UNAVAILABLE` replace the old boolean.
  Only `VERIFIED` can produce verified admission, semantic facts or a DREAM label. An unavailable
  verifier is no longer counted as success (`Response.verified` stays True/False/None for
  compatibility; `Response.verification` and `TraceStep.verification` carry the real state).
- **Reliability-aware retrieval.** `AMA.retrieve()` excludes records below reliability 0.5 by
  default and labels every result (`verified fact`, `user-provided, not independently verified`,
  etc.). Unverified model answers are still stored for audit but are not presented as memory.
- **Corrections are separate records.** A user correction is stored as `user_provided` at
  reliability 0.6 with `source="user"`; the assistant's reply is never relabelled
  `user_corrected`. User material cannot enter semantic/DREAM queues.
- **Hardened NGR.** NaN/±infinity, out-of-range scores, missing required capabilities and invalid
  sample counts reject promotion. `require_performance=True` requires p95 latency and peak RAM.
- **DREAM arms and baselines.** Four arms are measured (stable/fresh × new/replay), candidates can
  start from the stable checkpoint, the answer vocabulary comes from training data only, and a
  missing stable checkpoint requires a real cold-start baseline artifact plus a separate acceptance
  criterion - no fabricated zero baseline.

Measured evidence, four-arm DREAM results and the remaining limits are in
`research/phase1_trust.md`, `research/experiment_log.md` EXP-006/EXP-008 and
`research/failures.md` F-029–F-034.

## Phase 2 memory reliability (P15–P29)

The 2026-11-05 Phase 2 pass makes memory evidence auditable and keeps the neural memory out of the
response path:

- **Structured comparison.** `learning/compare.py` normalises numbers, units, dates and identifiers
  and scopes negation per clause. On 28 author-written pairs it scores 1.00 accuracy vs 0.64 for the
  old lexical comparator; this is not general semantic understanding.
- **Conflict index.** A `conflicts` table stores every contradiction and its policy. A claim
  supersedes only when independently `verified` and strictly stronger than every old claim; two
  verified claims stay open. `resolve_conflict()` requires an explicit explanation.
- **Utility feedback.** `memory_feedback` records retrieval hits, acceptance/rejection, task
  completion and corrections. Utility changes usefulness ranking only, never reliability.
- **Measured AMA.** Admission is one transaction with cached tokenisation: 1.40 ms/item vs 1.13 ms
  for store-everything on EXP-001 (1.24x, down from ~6x). The remaining +27% storage is audit and
  derived evidence; the threshold sweep is in `experiments/ama/calibration.json`.
- **Measured retention.** Recently used records are protected. The benchmark forgot 100/100
  intended unverified records, lost 0 protected records and left 0 stale index/fact rows.
- **Adaptive memory stays experimental.** IDF is essential (0.997 vs 0.010 exact), but FTS5 stays
  1.00 while adaptive recall falls to 0.41 with 10 distractors and 0.04 after task switches. Its
  queue now requires verified status, a reliability floor, no unresolved conflict and a hard update
  bound.
- **Semantic provenance.** A semantic fact requires a verified source episode and stores
  verification method, provenance, derivation and source id; deleting the source deletes the fact.

Measured evidence and limits: `research/phase2_memory.md`, `research/experiment_log.md`
EXP-009–EXP-012, `experiments/adaptive_memory/stress.json`, `experiments/dream/replay_sweep.json`
and `evaluation/contradiction_results.json`. Replay ratios remain uncalibrated (all arms tie), and
the adaptive memory is still not integrated.

## Phase 3 verified-correction loop (P07/P75)

The 2026-11-05 Phase 3 pass connects the existing pieces into one explicit chain:

- **Correction parsing.** `learning/corrections.py` classifies a correction and reports whether it
  is `verified`, `failed` or `unavailable`. Exact `+ - * / %`, integer powers and perfect-square
  roots are independently checked (Fraction + Decimal(60)); irrational roots, non-integer powers and
  factual claims stay `user_provided`.
- **Controller behaviour.** The user's sentence is still stored separately as `user_provided` with
  no generated reply. A verified arithmetic correction also produces a second `verified` record;
  the assistant's reply is never relabelled. The controller retains the previous non-correction
  trace so an opt-in `correction_loop` hook can attribute the failure (F-041).
- **CAGE -> candidate -> NGR.** `learning/loop.py` runs verified correction -> CAGE attribution ->
  authorisation -> bounded proposal -> temporary `FastWeights` update -> DREAM candidate -> NGR ->
  promotion/rollback. Every stage can refuse with a reason.
- **Measured arms (EXP-013, seeds 0-4).** Verified + stable + replay: fast recall empty -> 42 in
  5/5, candidate 1.00 old / 1.00 corrected, promoted 4/5. The fifth candidate was refused because
  the stable baseline accidentally scored 1.00 on the corrected held-out items. Verified + fresh +
  no replay: old 0.02 mean, rejected 5/5, stable pointer unchanged. Unverified factual, false
  arithmetic and no-trace corrections: refused 5/5 before training.
- **Larger frozen benchmark (EXP-014).** Ten arithmetic forms (including `%`, `**` and `sqrt`),
  three held-out wordings per form, five seeds and two arms: 50/50 replay runs promoted, 50/50
  no-replay runs rejected, 150/150 held-out wording predictions correct, and 25/25 control probes
  refused with zero fast updates, candidates or stable changes. This is still an author-written
  synthetic set whose held-out wordings share the expression tokens; it is not an independent
  capability estimate.
- **Background worker (P67).** `learning/worker.py` runs one daemon thread with a bounded queue.
  `submit()` never raises, queued jobs can be cancelled, running jobs are not force-killed, and
  `stop()` drains the queue. The controller can use it as the `correction_loop` hook and returns a
  `job_id`. It is in-process only: jobs are lost on restart and the CLI does not configure it.
- **Measured runtime (EXP-015).** On this Windows 11 / Python 3.13 machine: exact arithmetic p50
  <= 0.015 ms, AMA admission p50 1.15 ms, FTS5 search p50 0.25 ms, a full NumPy loop job p50
  ~22 ms, and a 300-turn EchoModel mix p50 ~1.2 ms / p95 ~1.7 ms with 0 errors, ~1 MB RSS and a
  548 KB database. The EchoModel is a plumbing stub, not `tony:7b`; no sustained real-model run was
  made.
- **Not language-model learning.** The candidate is the NumPy adaptive memory; no `tony:7b`
  fine-tune or adapter is trained (D-009 stands).

The default CLI does not configure the loop: no live replay corpus or stable checkpoint is defined,
so sessions do not learn automatically. Arbitrary factual corrections remain unverifiable (F-042).
EXP-014 improves the evidence but does not close the independent-author/independent-distribution
gap (F-044). Conflict review is a minimal CLI without notification or a UI (F-039). Details:
`research/phase3_learning.md`, `experiments/learning/loop.json`,
`experiments/learning/correction_bench.json`, `experiments/runtime/results.json` and
`open_problem.md`.

### Ollama (Windows PowerShell)

```powershell
ollama serve
python -m evaluation.ollama_baseline --models tony:7b --reference tony:7b --calibrate tony:7b
python -m app.main --config config/ashura.ollama.toml --trace
```

The foundation is pinned to `tony:7b` (Q4_K_M, local Qwen2 7.6B fine-tune, digest `0455603ff430`);
a digest mismatch is refused. `qwen3.5:2b` remains the 2.3 GB fallback. No external LLM API is
used.

## Local OCR (optional)

```powershell
pip install -e ".[perception]"     # Pillow + pytesseract
# Install the Tesseract executable for your OS; add it to PATH or set OCRConfig.tesseract_cmd.
python -m app.main --config config/ashura.ollama.toml --trace
# at the prompt:
/ocr "C:\path\to\image.png"
```

`skills/perception/ocr.py` validates the image, hashes it, optionally preprocesses/upscales it,
calls local Tesseract, and records text/confidence/engine/version. OCR output is **unverified**.
Explicit user corrections are stored separately in `ocr_records`; they are not automatic training
labels. `evaluation.ocr_benchmark` computes CER/WER against a labelled JSONL manifest, but no
held-out OCR corpus has been measured on the target laptop yet, so no OCR accuracy claim is made.
A clean synthetic smoke image (900x220, 56 px text) returned the exact string at 0.935 mean
confidence in 0.6-1.2 s with Tesseract 5.4.0; the Tesseract child peaked at ~27 MB RSS in that
run. This is a smoke test, not document accuracy.

## HARN arithmetic candidate

The exact rational evaluator in `skills/arithmetic/exact.py` remains authoritative. A NumPy
addition candidate (`skills/arithmetic/neural_expert.py`) is trained on random integer pairs and,
when a checkpoint exists, logged as agreeing/rejected against the exact answer. It cannot replace
or veto exact arithmetic.

```bash
python -m skills.arithmetic.train_addition --samples 50000 --test-samples 5000
```

Measured on seed 0, range −1000..1000: 50,000 training pairs, 5,000 held-out pairs, exact match
1.000, MAE 0.000, train time 0.016 s. This is a **linear least-squares fit**, not a deep network or
evidence that a learned arithmetic circuit is needed; the result is expected and the candidate adds
no capability over the exact path. See `research/experiment_log.md` EXP-007.

## What exists

| Area | Files | State |
|---|---|---|
| Foundation | `foundation/*` | Echo, Ollama and llama.cpp adapters; `tony:7b` pinned; Phase 0 0.94 strict / 2.35 s p50 (EXP-000d, n=16); 4.6 GB shared footprint; llama.cpp untested |
| Memory (LAMS) | `memory/*`, `brain/working_memory.py` | SQLite episodic + verified semantic facts, FTS5, provenance/derivation, conflict index, utility feedback, bounded working memory, deletion integrity, utility-aware retention |
| AMA | `learning/ama.py`, `learning/compare.py` | duplicate/conflict detection, scoring, continuous surprise, conflict index, feedback-based utility, decision log, reliability-aware retrieval; weights hand-set except the measured threshold sweep |
| NFD + router | `brain/need_field.py`, `brain/router.py`, `brain/controller.py` | priority scoring, RAM/CPU-aware selection, cheap-skill path, traces, measured costs when calibrated |
| Arithmetic | `skills/arithmetic/*` | exact rational path + independent Decimal verifier; neural addition is a non-authoritative candidate |
| OCR | `skills/perception/ocr.py`, `evaluation/ocr_benchmark.py` | optional local Tesseract, confidence, corrections, CER/WER runner; no target-corpus measurement yet |
| Adaptive memory | `memory/adaptive_memory.py` | Titans-inspired linear memory; **no advantage over FTS5 yet** |
| DPF + CAGE | `plasticity/*`, `learning/cage.py` | bounded fast state, candidate checkpoints, NGR-only promotion, trace attribution, gated update consumer (`GatedUpdater`) |
| Learning loop | `learning/loop.py`, `learning/corrections.py`, `learning/worker.py` | verified correction -> CAGE -> fast update -> DREAM -> NGR; exact arithmetic corrections only; opt-in controller hook and in-process bounded worker; no default live wiring or durable jobs |
| DREAM / NGR | `learning/dream.py`, `learning/replay.py`, `evaluation/ngr.py` | four consolidation arms (stable/fresh × new/replay, EXP-006), ratio/policy sweep (all arms tie), training-only vocabulary, real cold-start baseline, hardened promotion/rollback gate |
| Adaptive memory | `memory/adaptive_memory.py` | experimental IDF memory; verified/conflict-gated queue; stress and long-run measurements; not in the response path |
| BrainSim | `BrainSim/*` | independent B1–B6; 46 tests; not imported by ASHURA |
| Evaluation | `evaluation/*` | strict/lenient judge, 16-item suite, Ollama baseline with CIs and paired sign test, latency, retrieval bench |

## BrainSim (v2 blueprint, independent)

```bash
cd BrainSim
python -m pytest -q                       # 46 tests
python -m experiments.b1_sequence         # B1 + fast memory
python -m experiments.b2_delayed_copy     # B2 delayed recall
python -m experiments.b3_gated_memory     # B3 task-scoped gate
python -m experiments.b4_consolidation    # B4 replay vs new-only fine-tuning
python -m experiments.b5_control          # B5 budgeted need/action control
python -m experiments.b6_validation       # B6 four-arm held-out validation
```

B1 (3 seeds, CPU, 30 epochs): 128-hidden model, 206k parameters, train-rule 0.957, frozen unseen
0.085, token memory 0.771, pair memory 0.681. Leaving new-rule memory active drops old-rule
accuracy to 0.309 (token) or 0.904 (pair); after reset it returns to 0.957. The 384-hidden model
adds 8.7× parameters with no accuracy gain.

B2 (3 seeds): GRU and a parameter-matched fixed MLP both score 1.000 token/full recall at every
delay, including unseen delays 12–20. The fixed MLP trains 6–16× faster. **This is a capability
baseline, not evidence that recurrence is necessary**; the task saturates and the delay carries no
task-relevant information.

B3 (3 seeds): shared token memory retains old-rule accuracy 0.104 after a task switch; a
task-scoped gate retains 1.000. The task ID is supplied externally, so this proves isolation when
the boundary is known, not learned task identification or general interference control.

B4 (3 seeds): new-only fine-tuning on 8 new rules dropped old-rule accuracy by 49.3 points; a 50%
replay mix cut the drop to 1.18 points (0.945 old, 0.931 new). Replay costs ~38% more fine-tuning
time and is a bounded mitigation, not a retention guarantee.

B5 (3 seeds): a supervised 201k-parameter policy matched a finite-horizon DP oracle on a synthetic
budgeted-choice task (5.574 vs 5.5745 total utility; 0.9998 action accuracy; 0.0 infeasible
actions; confidence ECE 0.0002). Needs and budgets are observed inputs, so this is not
reinforcement learning, latent need inference, or general resource management.

B6 (3 seeds, disjoint held-out rules): fixed in-context MLP 0.327 token accuracy / 0.000 full
recall; frozen GRU 0.083 / 0.000; fast memory 0.771 / 0.000 but 0.083 after reset; per-rule gated
memory 1.000 / 1.000 and 1.000 on revisit. The gated 1.000 is full-coverage verified lookup with an
externally supplied rule ID, not rule induction or learned task segmentation. The fixed baseline
beats the frozen GRU, so B6 does not support a recurrent advantage.

Full reports: `BrainSim/research/experiment_log.md`, `BrainSim/research/failures.md`,
`BrainSim/research/decisions.md`. Detailed cross-milestone report:
[`results_brainsim.md`](results_brainsim.md).

## Remaining work

- **LoRA/QLoRA on the pinned local model:** not started. No adapter, training run or evaluation.
- **OCR accuracy:** the runner exists; no labelled held-out target corpus has been measured. The
  synthetic smoke test is not a document-accuracy result.
- **Real nonlinear HARN:** the current addition candidate is linear least squares. No deep or
  nonlinear arithmetic circuit has been trained or shown to help.
- **Perception/reasoning skills beyond OCR and exact arithmetic:** not implemented or benchmarked.
- **BrainSim → ASHURA integration:** deferred. No BrainSim mechanism has beaten a deterministic or
  retrieval baseline on an ASHURA response-path task.
- **AMA/NFD calibration:** weights and thresholds remain engineering defaults.
- **Expanded language evaluation:** the current suite is 16 items; broader capability and safety
  coverage is missing.
- **PACE capacity mutation and FIRE:** blueprint-only; not implemented.
- **B2b harder recall:** variable-length or relational recall was proposed but is not a blueprint
  milestone and has not been run.

## Research boundaries

- AMA/NFD weights and thresholds are uncalibrated defaults.
- Adaptive memory has no measured advantage over FTS5 and stays behind AMA's reliability gate.
- DREAM trains a small NumPy memory, never the language model.
- Exact arithmetic is authoritative; the HARN candidate is linear regression and adds no capability.
- OCR is implemented but unmeasured on a held-out target corpus.
- BrainSim tasks are synthetic and author-designed; B2 and B6 do not support a recurrent
  advantage. B4 replay is a bounded mitigation; B5 is supervised imitation; B6's gated 1.000 is
  full-coverage lookup with external task IDs.
- LoRA on `tony:7b`, PACE capacity mutation and BrainSim integration into the response path are not done.

See `research/experiment_log.md`, `research/failures.md` and `research/decisions.md` for the
measured record and known limits.
