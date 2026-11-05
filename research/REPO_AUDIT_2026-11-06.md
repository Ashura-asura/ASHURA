# ASHURA repository audit and hardening — 2026-11-06

## Scope and method

Reviewed the repository tree on `main` (244 tracked entries), both authoritative specifications (`spec/New_approach.txt` and `spec/New_approach_2.txt`), the completion audit, open-problem register, evidence standard, phase repair records, CI workflow, and the implementation paths most directly responsible for trust, persistence, routing, memory, learning promotion, specialist execution, and BrainSim's independent B1–B6 track.

This is a source-level engineering audit with targeted fixes and regression tests. It is not a formal security audit, and this environment did not execute the Python test suite locally. GitHub Actions is the validation authority for this branch.

## Specification invariants preserved

- Frozen language foundation; no base-model weight edits.
- BrainSim remains an independent research subproject and is not imported by ASHURA.
- FIRE and PACE remain non-critical-path research.
- SQLite/FTS5 remain the default memory path; adaptive memory stays experimental and out of response routing absent a measured win.
- Verified evidence, candidate training, NGR promotion, and rollback remain separate stages.
- No unsupported claim that NumPy-memory persistence demonstrates language-model learning.

## Hardening changes in this branch

1. **NGR policy validation** — reject empty targets, non-finite/negative target gains and tolerances, invalid performance ratios, and invalid per-capability epsilon values. This closes a promotion-gate weakness where NaN policy thresholds could make comparisons silently pass.
2. **BrainSim fast memory** — validate finite/stable hyperparameters, token dtypes/ranges, finite logits, and checkpoint config/tensor integrity; support CPU-stored memory when blending with model logits on another device; save checkpoints atomically.
3. **BrainSim training** — validate training configuration and sequence tensors before training; atomically publish model checkpoints.
4. **Checkpoint store** — atomically stage candidate artifacts and write manifests using unique same-directory temporary files.
5. **SQLite** — explicitly enable and verify per-connection foreign-key enforcement, validate busy-timeout configuration, and read the schema as UTF-8.
6. **Retrieval API** — reject invalid FTS/AMA limits and invalid reliability thresholds.
7. Added focused regression tests under `tests/test_*_hardening.py` and `BrainSim/tests/test_hardening.py`.

## Current evidence and CI

- The latest `main` CI run at baseline commit `42374298` passed; repository evidence records 284 ASHURA tests and 46 BrainSim tests on Windows/Python 3.13.
- PR #1 runs the full configured matrix, including ASHURA on Ubuntu/Windows with Python 3.11–3.13 and BrainSim on Ubuntu/Windows with Python 3.12.
- Branch CI status must be checked on PR #1 before merging. No local test execution is claimed here.

## Important unresolved work (not silently marked fixed)

- **Language-model learning:** 0/4 capability-learning tests demonstrated for the Qwen/Tony foundation. ASHURA's candidate is the NumPy associative memory; no ASHURA-trained LoRA/adapter exists.
- **Live learning loop:** opt-in only; no shipped replay corpus/stable checkpoint and no live real-model learning run.
- **Independent evaluation:** correction corpus and BrainSim tasks remain authored/synthetic; independent authorship and broader distributions are needed.
- **Adaptive-memory advantage:** no demonstrated advantage over FTS5; interference under task switching remains documented. Keep it out of the response path.
- **OCR:** local Tesseract pipeline exists, but held-out real-document CER/WER evidence is missing.
- **Concurrency:** four clients completed a bounded test, but Ollama queued requests; no parallel throughput claim. Production endurance, shared-database concurrency and thermal telemetry remain open.
- **Verification coverage:** exact arithmetic is narrow; general factual claims and irrational/non-integer arithmetic remain unverified.
- **Reviewer workflow:** conflict CLI exists; no UI/notification or prioritised review queue.
- **Packaging/runtime:** actual local model, Tesseract installation, hardware-specific performance, and Windows/Linux operational behavior must be tested on the user's machine.

## Decision

Keep the changes on the hardening branch until CI passes and the diff is reviewed. Do not merge automatically. The research prototype is substantially implemented, but the project should not be described as production-ready or as a self-improving language model.
