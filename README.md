# ASHURA
Adaptive Self-modifying Hierarchical Unified Reasoning Architecture - built from `New_approach.txt`.

**Current status: Phases 0-3 partially implemented (Phase 0 now has a real-model harness for Ollama but has NOT been run yet), Phase 4 prototype built and evaluated (spec Steps 1-7).** The adaptive memory is experimental and is *not* wired into the response path; EXP-004 found no advantage over FTS5.

## Run
```bash
pip install psutil numpy pytest
python -m pytest -q                       # 113 tests
python -m app.main --trace                # CLI (uses the echo stub model until a real GGUF is configured)
python -m experiments.ama.run             # EXP-001  AMA vs store-everything
python -m evaluation.retrieval_bench      # EXP-002  FTS5 latency vs size
python -m experiments.nfd.run             # EXP-003  NFD vs always-run
python -m experiments.adaptive_memory.run # EXP-004  neural adaptive memory vs FTS5 (needs numpy)
python -m experiments.adaptive_memory.conflict  # EXP-005  same-key conflicting updates
python -m evaluation.ollama_baseline      # PHASE 0   real-model baseline over every installed Ollama model
python -m memory.retention --db data/ashura.db   # forgetting policy (dry run; add --apply)
```
### Using your Ollama models (Windows PowerShell)
```powershell
cd path\to\ASHURA
pip install psutil numpy pytest
ollama serve                                   # if it is not already running as a service
# 1) Phase 0 baseline. Start small: the reference, the untouched lfm3, and one or two fine-tunes
python -m evaluation.ollama_baseline --models ref-base:7b lfm3:latest tony_control:7b --calibrate ref-base:7b
# 2) everything installed (slow: expect roughly 4-8 min per 7B model on CPU)
python -m evaluation.ollama_baseline
# 3) chat through ASHURA's controller with a real model
python -m app.main --config config/ashura.ollama.toml --trace
```
Results land in `results/baseline_<timestamp>.md/.json`. `--calibrate` writes `config/module_costs.json`, which replaces the router's placeholder cost for the language module. A fine-tune is only reported as better/worse than `ref-base:7b` when a sign test on the paired results gives p < 0.05.

To use a llama.cpp model instead: install `llama-cpp-python`, download a Qwen Instruct GGUF, and set `backend`, `path`, `checkpoint`, `quantization`, `licence`, `sha256` in `config/ashura.toml`. The loader refuses a file whose hash does not match.

## What exists
| Area | Files | State |
|---|---|---|
| Foundation | `foundation/*` | config, hash-verified loading, read-only protection, **Ollama backend (tested against a fake server only - never against a real Ollama)**, llama.cpp backend (**untested**), echo stub |
| Memory (LAMS) | `memory/*`, `brain/working_memory.py` | SQLite episodic + semantic facts, FTS5 behind `MemoryIndex`, bounded/expiring working memory, persistence tested, **deletion cleans index + facts (F-010 fixed)**, conservative forgetting policy |
| AMA | `learning/ama.py` | duplicates, value-aware conflict detection (F-002 fixed), scoring, surprise (prediction error vs memory), queues, decision log (**weights uncalibrated**) |
| NFD + router | `brain/need_field.py`, `router.py`, `controller.py` | priority scoring, module registry, RAM- and CPU-aware selection, cheap-skill path, execution traces, measured costs when `config/module_costs.json` exists |
| Arithmetic | `skills/arithmetic/*` | exact path + independent Decimal verifier (neural HARN experts not started) |
| Adaptive memory | `memory/adaptive_memory.py` | Titans-inspired linear memory: surprise/momentum/decay/gate, reset, checkpoint, AMA-queue consumer; NumPy; **no advantage over FTS5 yet** |
| NGR | `evaluation/ngr.py` | promotion rule with frozen tolerances (no checkpoint promote/rollback yet) |
| Evaluation | `evaluation/*` | strict+lenient judge (echo-proof), 16-item suite v2, Ollama baseline with CIs and paired sign test, latency p50/p95, retrieval bench |
| Research record | `research/*` | hypotheses, experiment log, failures, decisions |

## Not started (by design, per spec section 23)
DPF/CAGE (5), DREAM + checkpoint promotion/rollback (6), neural HARN experts (7), OCR (8), LoRA adapters (9), PACE (10). Placeholder modules are registered as `available=False`, so the router reports them as "needed but not implemented" instead of silently pretending.

## Acceptance checklist (spec section 22) - honest status
- Foundation: Ollama backend + baseline harness built; **no real checkpoint pinned (licence TBD) and the baseline has not been run**; checkpoint protection implemented.
- Memory: working memory, SQLite episodic (delete verified), FTS5, forgetting policy done; admission evaluated on synthetic data only; vector retrieval not built (intentionally).
- Controller: intent/need analysis, routing, skipping and traces done (keyword-based heuristics).
- Learning / DREAM / specialist OCR+HARN / most research criteria: not yet.
- Resource efficiency: measured only in a 1-vCPU sandbox, **not on the target laptop**.

## Next steps
1. On the target laptop: pick Qwen checkpoint, check licence, pin sha256, run `evaluation.benchmark_runner`, replace placeholder module costs with measurements (finishes Phase 0).
2. Fix F-002 (false conflicts), build a more realistic AMA dataset including useful unverified items, then calibrate weights.
3. Phase 4 follow-ups: same-key conflict test, a semantic-generalisation task with a real encoder, then Phase 5 (DPF + CAGE) only if the memory earns a place.
See `research/failures.md` for known problems.
