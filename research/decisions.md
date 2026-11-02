# Decisions

- D-001: Python 3.11+, stdlib `sqlite3` + FTS5, `tomllib`; psutil is the only runtime dependency so far.
- D-002: `EchoModel` stub backend so everything is testable without weights. `llama_cpp` backend is implemented but untested here (no weights/library in the sandbox).
- D-003: Language model is declared `resident` in the router (loaded once by the app).
- D-004: Exact arithmetic uses `Fraction` with an AST whitelist (no `eval`), caps result size, and refuses irrational sqrt rather than returning floats.
- D-005: Conflicts never delete history; stronger evidence de-indexes older records, weaker evidence is stored but not searchable.
- D-006: AMA runs synchronously after the answer for now; async/background deferred.
- D-007: AMA weights, NFD weights and thresholds stay at uncalibrated defaults and are labelled as such.
- D-008: Adaptive memory implemented in NumPy (analytic gradient of a linear memory); PyTorch was not installable in the dev sandbox. Port to PyTorch (safetensors checkpoints) when the memory becomes non-linear or on the target laptop.
- D-009: Adaptive memory stays OUT of the controller's response path until it shows an advantage over FTS5. It is fed only through AMA's `neural_memory` queue via `drain_neural_queue`.
- D-010: Hyper-parameters (lr) are tuned on a separate validation seed, never on the reported seeds.
- D-011: Ollama is a supported foundation backend (stdlib HTTP only). Pinning is by Ollama digest instead of GGUF sha256; a mismatch refuses to run. Greedy decoding (temperature 0, seed 0) for reproducibility.
- D-012: Server-side memory is read from `ollama ps`, never from this Python process's RSS (the model lives in the Ollama server).
- D-013: A model is only called better/worse than the reference if a two-sided exact sign test on paired strict results gives p < 0.05. Small differences are reported as "no detectable difference".
- D-014: Deletion integrity is enforced by SQL triggers (not only Python), so it cannot be bypassed by a future code path. admission_log is an audit trail and survives deletion.
- D-015: Forgetting never touches verified/corrected/trusted records, conflict evidence, reinforced records or queued items.
- D-016: The AMA answer comparator errs toward "conflict" when unsure (stored as evidence, not indexed) rather than toward silently merging two answers that might disagree.
- D-017: Phase 0 foundation is `qwen3.5:2b` (Qwen3.5 1.9B, Q8_0, Apache-2.0, digest 0689d44085e0). It fits the 2 GB VRAM budget at 2.3 GB and measured 0.56 strict / 4.5 s p50 on `baseline_v2` (EXP-000c). The 7B Qwen2 fine-tune scored 0.94 but took 50.7 s p50 and is not viable as the live model (F-014). Thinking is disabled on the fast path (`think=false`).
- D-018: DPF fast state wraps the existing adaptive memory and is bounded by `FastConfig.max_delta_norm`; slow state is a file-based `CheckpointStore` whose `promote()` requires a passing `NGRResult`. DREAM trains the same small NumPy memory, never Qwen, and held-out examples are isolated from training (adding a duplicate across splits raises).
