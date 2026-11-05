# EXP-016 - Bounded concurrency, reload, restart and 80-turn soak

Date: 2026-11-05. Status: **F-046 closed for the bounded scope below; F-047 opened here and later
fixed for a bounded scope by EXP-019.**

## Hypothesis and baseline

Hypothesis: four concurrent ASHURA client processes can complete 80 mixed turns without client
failures; one forced `tony:7b` unload/reload works; a record written by one ASHURA process survives a
fresh process.

Baseline: EXP-015 single-client cold-start language p50 5.52 s over 24 general turns.

## Implementation and configuration

- Runner: `experiments/runtime/real_soak.py`
- Model: `tony:7b`, digest `0455603ff430`, `config/ashura.ollama.toml`
- Four client processes, each with an isolated SQLite database; shared local Ollama server
- 80 turns: 60 synthetic free-form general prompts, 20 exact arithmetic prompts
- Phase 1: 28 turns; one forced unload/reload; phase 2: 52 turns
- One fresh-process persistence check
- Windows 11, Python 3.13.14, i7-1165G7 class, 8 logical CPUs, 16 GB RAM
- Runtime budget: 15-20 minutes; actual ~455 s

## Dataset and separation

The prompts are synthetic runtime probes. There are no gold answers, no held-out capability set and
no train/test capability claim. This experiment measures runtime, persistence and failure behaviour,
not answer quality or learning.

## Results

| Measurement | Result |
|---|---|
| Cold load | 13.32 s wall; 7.05 s Ollama load |
| Forced unload/reload | 22.41 s wall; 9.11 s Ollama load |
| Phase 1 (28 turns) | general p50 19.88 s / p95 36.89 s; arithmetic p50 5.56 ms; 0 failures |
| Phase 2 (52 turns) | general p50 27.23 s / p95 33.55 s; arithmetic p50 3.67 ms; 0 failures |
| All 80 turns | general p50 25.80 s / p95 35.23 s / p99 38.05 s; arithmetic p50 4.43 ms / p95 6.67 ms |
| Availability | 0 failures, 0 empty answers, 60/60 language steps |
| Tokens | 2,047 generated; 28,081 prompt |
| Client RSS | max 97.0 MB |
| Inference process RSS | ~5.27 GB |
| Model footprint | 4,635.9 MB (Ollama-reported) |
| System CPU / RAM | max 65% / 83.9% |
| Temperature / throttling | temperature unavailable from OS; CPU frequency constant 1690 MHz, so throttling not established |
| Process restart | write PID 1552, verify PID 12164; arithmetic and memory records found; controller retrieval "2 hits"; DB 120/204 KB |
| Total wall time | ~455 s |

## Accuracy and generalisation

Not applicable. The free-form prompts have no reference answers, and no capability test was run.
The restart check proves that stored records are readable after a process restart; it does not prove
that a capability was learned or generalised.

## Regression and rollback

No learning promotion or model update occurred. There was no stable checkpoint to regress. The
persistence check wrote only to an isolated test database.

## Failure analysis

- Four concurrent clients did not produce parallel throughput. General p50 rose from 5.52 s
  single-client to 25.80 s with four clients (~4.7x), with server CPU utilisation around 0.31.
  The local model appears to queue requests. This is a negative result, recorded as F-047.
- Forced reload (22.41 s) was slower than cold load (13.32 s); Ollama load time rose from 7.05 s to
  9.11 s. Residual load/thermal state is the likely cause, but temperature telemetry was unavailable.
- System RAM reached 83.9%. This is within the guard threshold but leaves limited headroom.
- No thermal guard triggered; no abnormal client behaviour or request failures occurred.

## Conclusion

**Supported** for the bounded F-046 scope: client lifecycle, database persistence, forced model
unload/reload and application restart. **Rejected** for parallel inference throughput (F-047).
**Inconclusive** for thermal throttling and production endurance.

F-045 (durable worker jobs, crash recovery and job persistence) remains separate and open.

Raw data: `experiments/runtime/real_soak.json`.
