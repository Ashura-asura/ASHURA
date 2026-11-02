# ASHURA
Adaptive Self-modifying Hierarchical Unified Reasoning Architecture - built from `New_approach.txt`.

**Current status: Phase 0 baseline measured on the target laptop; Phases 1-6 implemented (Phase 6 uses a synthetic replay experiment), OCR/HARN-neural/LoRA/PACE not started.** The adaptive memory is experimental and is *not* wired into the response path; EXP-004 found no advantage over FTS5. **128 tests pass.**

## Run
```bash
pip install psutil numpy pytest
python -m pytest -q                       # 128 tests
python -m app.main --trace                # CLI (uses the echo stub model until a real GGUF is configured)
python -m experiments.ama.run             # EXP-001  AMA vs store-everything
python -m evaluation.retrieval_bench      # EXP-002  FTS5 latency vs size
python -m experiments.nfd.run             # EXP-003  NFD vs always-run
python -m experiments.adaptive_memory.run # EXP-004  neural adaptive memory vs FTS5 (needs numpy)
python -m experiments.adaptive_memory.conflict  # EXP-005  same-key conflicting updates
python -m experiments.dream.run           # EXP-006  DREAM replay vs new-only training
python -m evaluation.ollama_baseline      # PHASE 0   real-model baseline over every installed Ollama model
python -m memory.retention --db data/ashura.db   # forgetting policy (dry run; add --apply)
```
### Using your Ollama models (Windows PowerShell)
```powershell
cd path\to\ASHURA
pip install psutil numpy pytest
ollama serve                                   # if it is not already running as a service
# 1) Phase 0 baseline for the pinned foundation
python -m evaluation.ollama_baseline --models qwen3.5:2b --reference qwen3.5:2b --calibrate qwen3.5:2b
# 2) compare any other installed model (optional; --think allows reasoning before answering)
python -m evaluation.ollama_baseline --models qwen3.5:2b lfm3:latest --reference qwen3.5:2b
# 3) chat through ASHURA's controller with a real model
python -m app.main --config config/ashura.ollama.toml --trace
```
Results land in `results/baseline_<timestamp>.md/.json`. `--calibrate` writes `config/module_costs.json`, which replaces the router's placeholder cost for the language module. A model is only reported as better/worse than the reference when a sign test on the paired results gives p < 0.05.

To use a llama.cpp model instead: install `llama-cpp-python`, download a Qwen Instruct GGUF, and set `backend`, `path`, `checkpoint`, `quantization`, `licence`, `sha256` in `config/ashura.toml`. The loader refuses a file whose hash does not match.

## What exists
| Area | Files | State |
|---|---|---|
| Foundation | `foundation/*` | config, digest/read-only protection, real Ollama backend, **`qwen3.5:2b` pinned (Q8_0, Apache-2.0, digest `0689d44085e0`)**; Phase 0 baseline 0.56 strict / 4.5 s p50 (EXP-000c); llama.cpp backend (**untested**) |
| Memory (LAMS) | `memory/*`, `brain/working_memory.py` | SQLite episodic + semantic facts, FTS5 behind `MemoryIndex`, bounded/expiring working memory, persistence tested, **deletion cleans index + facts (F-010 fixed)**, conservative forgetting policy |
| AMA | `learning/ama.py` | duplicates, value-aware conflict detection (F-002 fixed), scoring, surprise (prediction error vs memory), queues, decision log (**weights uncalibrated**) |
| NFD + router | `brain/need_field.py`, `router.py`, `controller.py` | priority scoring, module registry, RAM- and CPU-aware selection, cheap-skill path, execution traces, measured costs when `config/module_costs.json` exists |
| Arithmetic | `skills/arithmetic/*` | exact path + independent Decimal verifier (neural HARN experts not started) |
| Adaptive memory | `memory/adaptive_memory.py` | Titans-inspired linear memory: surprise/momentum/decay/gate, reset, checkpoint, AMA-queue consumer; NumPy; **no advantage over FTS5 yet** |
| DPF + CAGE | `plasticity/*`, `learning/cage.py` | resettable bounded fast state, versioned stable/candidate/experimental checkpoints, NGR-only promotion + rollback, trace-based attribution; synthetic tests only |
| DREAM | `learning/dream.py`, `learning/replay.py` | verified-example replay, new-only vs replay experiment (**EXP-006: old retention 1.00 vs 0.00**), NGR promotion/rejection, JSONL decision log |
| NGR | `evaluation/ngr.py`, `plasticity/slow_weights.py` | promotion rule with frozen tolerances, mandatory gate on promotion, previous stable kept for rollback |
| Evaluation | `evaluation/*` | strict+lenient judge (echo-proof), 16-item suite v2, Ollama baseline with CIs and paired sign test, latency p50/p95, retrieval bench |
| Research record | `research/*` | hypotheses, experiment log, failures, decisions |

## Not started (by design, per spec section 23)
Neural HARN experts (7), OCR (8), LoRA adapters (9), PACE (10). Placeholder modules are registered as `available=False`, so the router reports them as "needed but not implemented" instead of silently pretending.

## Acceptance checklist (spec section 22) - honest status
- Foundation: locally running Ollama foundation pinned to `qwen3.5:2b` (digest, quantization, Apache-2.0); real 16-item baseline recorded on the target laptop; stable checkpoint protection implemented. The 7B quality reference was measured then deleted (F-014).
- Memory: working memory, SQLite episodic (delete verified), FTS5, forgetting policy done; admission evaluated on synthetic data only; vector retrieval not built (intentionally).
- Controller: intent/need analysis, routing, skipping and traces done (keyword-based heuristics), CAGE attribution on failed traces.
- Learning: fast adaptive memory works and resets; DREAM teaches a small candidate from verified examples; NGR rejects a forgetting candidate and the stable version is restored by pointer. Generalisation is lexical only.
- Resource efficiency: measured on the target laptop for three models (7B, 2B, 1.7B); consolidation is not yet asynchronous, so "background learning does not block responses" is only true for the small NumPy candidate.

## Next steps
1. Phase 7: build one neural HARN arithmetic expert and compare against the exact path; Phase 8: OCR via Qwen3.5 vision or Tesseract, with confidence + corrections.
2. Phase 9: LoRA on `qwen3.5:2b` (frozen base), NGR retention suite, then promote/reject.
3. Calibrate AMA/NFD weights on a realistic stream and test a semantic encoder before any claim that adaptive memory earns its place.
See `research/failures.md` for known problems.
