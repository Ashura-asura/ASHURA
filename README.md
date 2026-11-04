# ASHURA

Adaptive Self-modifying Hierarchical Unified Reasoning Architecture, built from
`spec/New_approach.txt` and the v2 blueprint `spec/New_approach_2.txt`.

**Status:** Phase 0 foundation baseline measured on the target laptop; Phases 1–6 implemented;
local OCR and a HARN arithmetic candidate are integrated behind optional dependencies/checkpoints;
BrainSim B1–B6 measured as an independent subproject. **139 ASHURA tests and 46 BrainSim tests
pass.** The adaptive memory remains experimental and out of the response path. BrainSim is not
imported by ASHURA.

## Run

```bash
pip install psutil numpy pytest
python -m pytest -q                       # 139 tests
python -m app.main --trace                # CLI (echo stub until a real model is configured)
python -m experiments.ama.run             # EXP-001  AMA vs store-everything
python -m evaluation.retrieval_bench      # EXP-002  FTS5 latency vs size
python -m experiments.nfd.run             # EXP-003  NFD vs always-run
python -m experiments.adaptive_memory.run # EXP-004  neural adaptive memory vs FTS5
python -m experiments.adaptive_memory.conflict  # EXP-005  same-key conflicts
python -m experiments.dream.run           # EXP-006  DREAM replay vs new-only
python -m evaluation.ollama_baseline      # PHASE 0   real-model baseline
python -m memory.retention --db data/ashura.db   # forgetting policy dry run
```

### Ollama (Windows PowerShell)

```powershell
ollama serve
python -m evaluation.ollama_baseline --models qwen3.5:2b --reference qwen3.5:2b --calibrate qwen3.5:2b
python -m app.main --config config/ashura.ollama.toml --trace
```

The foundation is pinned to `qwen3.5:2b` (Q8_0, Apache-2.0, digest `0689d44085e0`); a digest
mismatch is refused. No external LLM API is used.

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
| Foundation | `foundation/*` | Echo, Ollama and llama.cpp adapters; `qwen3.5:2b` pinned; Phase 0 0.56 strict / 4.5 s p50 (EXP-000c); llama.cpp untested |
| Memory (LAMS) | `memory/*`, `brain/working_memory.py` | SQLite episodic + semantic facts, FTS5, bounded working memory, deletion integrity, retention policy |
| AMA | `learning/ama.py` | duplicate/conflict detection, scoring, surprise, queues, decision log; weights uncalibrated |
| NFD + router | `brain/need_field.py`, `brain/router.py`, `brain/controller.py` | priority scoring, RAM/CPU-aware selection, cheap-skill path, traces, measured costs when calibrated |
| Arithmetic | `skills/arithmetic/*` | exact rational path + independent Decimal verifier; neural addition is a non-authoritative candidate |
| OCR | `skills/perception/ocr.py`, `evaluation/ocr_benchmark.py` | optional local Tesseract, confidence, corrections, CER/WER runner; no target-corpus measurement yet |
| Adaptive memory | `memory/adaptive_memory.py` | Titans-inspired linear memory; **no advantage over FTS5 yet** |
| DPF + CAGE | `plasticity/*`, `learning/cage.py` | bounded fast state, candidate checkpoints, NGR-only promotion, trace attribution |
| DREAM / NGR | `learning/dream.py`, `learning/replay.py`, `evaluation/ngr.py` | verified replay, new-only vs replay (EXP-006), promotion/rollback gate |
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
`BrainSim/research/decisions.md`.

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
- DREAM trains a small NumPy memory, never Qwen.
- Exact arithmetic is authoritative; the HARN candidate is linear regression and adds no capability.
- OCR is implemented but unmeasured on a held-out target corpus.
- BrainSim tasks are synthetic and author-designed; B2 and B6 do not support a recurrent
  advantage. B4 replay is a bounded mitigation; B5 is supervised imitation; B6's gated 1.000 is
  full-coverage lookup with external task IDs.
- LoRA on Qwen, PACE capacity mutation and BrainSim integration into the response path are not done.

See `research/experiment_log.md`, `research/failures.md` and `research/decisions.md` for the
measured record and known limits.
