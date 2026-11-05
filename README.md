# ASHURA

Adaptive Self-modifying Hierarchical Unified Reasoning Architecture, built from
`spec/New_approach.txt` and the v2 blueprint `spec/New_approach_2.txt`.

**Status:** Phase 0 foundation baseline measured on the target laptop; Phases 1–6 implemented;
Phase 1 trust repair (P01–P14), Phase 2 memory reliability (P15–P29) and Phase 3 verified-correction
loop (P07/P75/A01–A03) implemented and tested; local OCR and a HARN arithmetic candidate are
integrated behind optional dependencies/checkpoints; BrainSim B1–B6 measured as an independent
subproject. **291 ASHURA tests and 46 BrainSim tests pass.** The adaptive memory remains
experimental and out of the response path. BrainSim is not imported by ASHURA. The learning loop is
**not** complete: it is an opt-in controller hook with a durable background worker, only exact
arithmetic corrections are independently verified, and the candidate is the NumPy memory rather
than the language model. EXP-017 shows that a promoted NumPy candidate survives a process restart
and retains the old capability. EXP-018 selects `tony:7b-gpa3` as the general tutor and keeps
`tony:7b` as the privacy profile; EXP-018b keeps `tony:7b-agentic3` as an agentic-benchmark
candidate. ASHURA trains none of them. F-045 is fixed for durable jobs and hard timeout; F-046 is
closed only for a bounded client/reload/restart test. EXP-019 fixes F-047 for explicit bounded
concurrency: one server slot is the safe default, two give ~1.45x at two clients, and four are
rejected because they cut single-client throughput to 3.32 tokens/s. No linear-scaling claim. See
`research/evidence_standard.md`, `research/EXP-018_subject_tutor.md`,
`research/EXP-019_concurrency.md` and `research/completion_audit.md`.

## Run

```bash
pip install -e ".[dev]"                   # or: pip install psutil numpy pytest
python -m pytest -q                       # 291 tests
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
python -m experiments.learning.persistence_bench # EXP-017  restart persistence/retention/rollback
python -m experiments.runtime.load_bench  # EXP-015  module costs + sustained load
python -m experiments.runtime.load_bench --real-model --real-cold  # optional local tony:7b mixed load
python -m experiments.runtime.real_soak  # EXP-016  4-client/reload/restart bounded soak
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
- **Background worker (P67/F-045).** `learning/worker.py` runs one daemon thread with a bounded
  queue. `submit()` never raises, queued jobs can be cancelled, and `stop()` drains by default.
  A SQLite job store persists payload, status and result; a restart re-schedules queued jobs and
  marks previously running jobs interrupted. `hard_timeout_s` runs a job in a spawned child and
  terminates it at the deadline. The CLI wiring is opt-in via `[learning]` and disabled by default;
  it requires a JSONL replay corpus and a checkpoint directory. Residual limits: one worker per
  store and at-least-once recovery for queued jobs.
- **Measured runtime (EXP-015).** On this Windows 11 / Python 3.13 machine: exact arithmetic p50
  <= 0.015 ms, AMA admission p50 1.35 ms, FTS5 search p50 0.29 ms, a full NumPy loop job p50
  ~24 ms, and a 300-turn EchoModel mix p50 ~1.4 ms / p95 ~1.8 ms with 0 errors, ~1 MB RSS and a
  548 KB database. An optional cold-start `tony:7b` mixed load (24 free-form general turns + 8
  exact arithmetic turns) measured language p50 5.5 s / p95 8.1 s, 7.4 generated tokens/s and 0
  errors; the arithmetic turns stayed at p50 2.4 ms because they bypass the model. Ollama reported
  a 4.64 GB model footprint and the ASHURA client stayed at ~97 MB RSS. The EchoModel numbers
  remain the non-language baseline.
- **Bounded real-model closure (EXP-016).** Four concurrent clients completed 80 mixed turns with
  0 failures; one forced unload/reload took 22.41 s wall (9.11 s Ollama load); a fresh ASHURA
  process found both a verified arithmetic record and a user-provided memory record. General p50
  under four clients was 25.80 s / p95 35.23 s, versus 5.52 s single-client, so the local model
  queues requests rather than scaling. Arithmetic stayed at p50 4.43 ms. Client RSS max 97 MB;
  system RAM max 83.9%; temperature telemetry was unavailable. This closes F-046 only for client
  lifecycle, database persistence, model reload and application restart — not production endurance
  or parallel throughput.
- **Concurrency policy (EXP-019/F-047).** A private-server sweep on `tony:7b-gpa3` measured
  `OLLAMA_NUM_PARALLEL` 1/2/4 with 1/2/4 clients and a fixed 32-token output. One slot serialized
  (4.93 to 5.95 tokens/s, p50 6.57 to 13.53 s); two slots gave 1.45x at two clients (9.21 tokens/s)
  but only 1.19x at four; four slots cut single-client throughput to 3.32 tokens/s and raised
  system RAM to 87.7%. Keep one slot as the default, two as the opt-in maximum, and reject
  four. The client profiles now set `max_inflight=1`, `max_queue=8`, `queue_timeout_s=60`; these
  bounds are per process, not a cross-process scheduler.
- **Consolidation persistence (EXP-017).** A verified correction promoted a NumPy candidate in one
  process; a fresh process loaded the same stable artifact (SHA-256 match 20/20), predicted 60/60
  corrected held-out wordings and 400/400 old-capability wordings, and rolled back to the parent
  20/20. Artifact max 131 KB; write/verify p50 48.219/33.241 ms; RSS max 41.2 MB; 6.25 s total.
  This is persistence and retention for the NumPy candidate, not a language-model capability change.
- **Not language-model learning.** The candidate is the NumPy adaptive memory; ASHURA does not
  train `tony:7b-gpa3` or `tony:7b` (D-009 stands). Both are user-supplied fine-tunes; EXP-018
  evaluates them but does not turn them into a learned ASHURA capability. The completion audit
  scores the engineering checklist separately from this central language-learning claim.

The default CLI does not configure the loop: no live replay corpus or stable checkpoint is defined,
so sessions do not learn automatically. Arbitrary factual corrections remain unverifiable (F-042).
EXP-014 improves the evidence but does not close the independent-author/independent-distribution
gap (F-044). Conflict review is a minimal CLI without notification or a UI (F-039). Details:
`research/phase3_learning.md`, `experiments/learning/loop.json`,
`experiments/learning/correction_bench.json`, `experiments/learning/persistence.json`,
`experiments/runtime/results.json`, `experiments/runtime/real_soak.json`,
`research/EXP-016_real_soak.md`, `research/EXP-017_persistence.md`,
`research/evidence_standard.md`, `research/completion_audit.md` and `open_problem.md`.

### Ollama (Windows PowerShell)

```powershell
ollama serve
python -m evaluation.ollama_baseline --models tony:7b-gpa3 --reference tony:7b --calibrate tony:7b-gpa3
python -m evaluation.subject_bench          # EXP-018 frozen 42-item subject comparison
python -m app.main --config config/ashura.ollama.toml --trace
```

The general foundation is pinned to `tony:7b-gpa3` (Q4_K_M, local Qwen2 7.6B fine-tune, digest
`2a86766287cf`); a digest mismatch is refused. `tony:7b` (digest `0455603ff430`) remains the
privacy profile via `config/ashura.ollama.private.toml`. EXP-018 tied them at 41/42 adjudicated
answers; gpa3 was faster (1.86 s vs 3.04 s p50). `tony:7b-agentic3` tied accuracy but was slower
and less format-compliant, so it remains an agentic-benchmark candidate (EXP-018b). `qwen3.5:2b`
remains the 2.3 GB fallback. No external LLM API is used.

Durable background learning is opt-in: `[learning].enabled = true` requires a JSONL
`learning.replay_path` and `learning.checkpoint_dir`; `hard_timeout_s > 0` runs each job in a
killable child. The shipped configs leave it disabled.

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
| Foundation | `foundation/*` | Echo, Ollama and llama.cpp adapters; general `tony:7b-gpa3` and privacy `tony:7b` pinned; 41/42 adjudicated each, 1.86/3.04 s p50 (EXP-018, n=42); 4.7 GB shared footprint; bounded per-process concurrency gate (EXP-019); llama.cpp untested |
| Memory (LAMS) | `memory/*`, `brain/working_memory.py` | SQLite episodic + verified semantic facts, FTS5, provenance/derivation, conflict index, utility feedback, bounded working memory, deletion integrity, utility-aware retention |
| AMA | `learning/ama.py`, `learning/compare.py` | duplicate/conflict detection, scoring, continuous surprise, conflict index, feedback-based utility, decision log, reliability-aware retrieval; weights hand-set except the measured threshold sweep |
| NFD + router | `brain/need_field.py`, `brain/router.py`, `brain/controller.py` | priority scoring, RAM/CPU-aware selection, cheap-skill path, traces, measured costs when calibrated |
| Arithmetic | `skills/arithmetic/*` | exact rational path + independent Decimal verifier; neural addition is a non-authoritative candidate |
| OCR | `skills/perception/ocr.py`, `evaluation/ocr_benchmark.py` | optional local Tesseract, confidence, corrections, CER/WER runner; no target-corpus measurement yet |
| Adaptive memory | `memory/adaptive_memory.py` | Titans-inspired linear memory; **no advantage over FTS5 yet** |
| DPF + CAGE | `plasticity/*`, `learning/cage.py` | bounded fast state, candidate checkpoints, NGR-only promotion, trace attribution, gated update consumer (`GatedUpdater`) |
| Learning loop | `learning/loop.py`, `learning/corrections.py`, `learning/worker.py`, `learning/jobs.py` | verified correction -> CAGE -> fast update -> DREAM -> NGR; exact arithmetic corrections only; opt-in durable worker with restart recovery and hard timeout; CLI wiring disabled by default; no live real-model learning run |
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
  EXP-017 covers the NumPy candidate only; it is not a substitute for a language-model experiment.
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
- DREAM trains a small NumPy memory, never the language model. EXP-017's restart persistence and
  retention result applies to that NumPy candidate, not to `tony:7b`.
- Exact arithmetic is authoritative; the HARN candidate is linear regression and adds no capability.
- OCR is implemented but unmeasured on a held-out target corpus.
- BrainSim tasks are synthetic and author-designed; B2 and B6 do not support a recurrent
  advantage. B4 replay is a bounded mitigation; B5 is supervised imitation; B6's gated 1.000 is
  full-coverage lookup with external task IDs.
- LoRA on `tony:7b`, PACE capacity mutation and BrainSim integration into the response path are not done.

See `research/experiment_log.md`, `research/failures.md` and `research/decisions.md` for the
measured record and known limits.
