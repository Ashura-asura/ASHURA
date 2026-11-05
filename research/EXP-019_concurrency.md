# EXP-019 - Concurrent inference configuration and throughput (F-047)

Date: 2026-11-06. Status: **F-047 fixed for a bounded scope; no linear-scaling claim.**

## Hypothesis and baseline

Hypothesis: the target laptop's local Ollama server serializes concurrent requests by default
(`OLLAMA_NUM_PARALLEL=1`), so four clients queue instead of increasing throughput. Raising the
server's parallel-slot count might buy some throughput, but on a 7.6B Q4_K_M model with a 2 GB
dedicated GPU it may also increase memory pressure and latency.

Baseline: EXP-016 measured four ASHURA client processes against `tony:7b` and found general p50
25.80 s with four clients versus 5.52 s single-client, with server CPU utilisation around 0.31. That
was a negative result for parallel throughput (F-047), not a measurement of the server's settings.

## Configuration and method

- Model: `tony:7b-gpa3`, digest `2a86766287cf`. Only this model was loaded; the desktop server on
  11434 remained idle, and a dedicated server on 11435 was started and stopped for each setting.
- Server matrix: `OLLAMA_NUM_PARALLEL` = 1, 2, 4; `OLLAMA_MAX_QUEUE` = 8;
  `OLLAMA_MAX_LOADED_MODELS` = 1; `OLLAMA_KEEP_ALIVE` = 5m.
- Client matrix: 1, 2 and 4 simultaneous requests. Every round started its clients from a
  `threading.Barrier`; 3 measured rounds plus 1 discarded warmup round per level. That is 63
  measured requests per sweep (3 rounds x (1+2+4) clients x 3 server settings).
- Fixed decoding: temperature 0, seed 0, top_p 0.9, `num_predict` 32, `num_ctx` 2048. The prompt is
  a short counting task, so every request generated exactly 32 tokens; this removes output-length
  differences from the throughput comparison.
- Runner: `experiments/runtime/concurrency_sweep.py` (private-server lifecycle) and
  `evaluation/concurrency_bench.py` (measurement). Raw data:
  `experiments/runtime/concurrency_sweep.json`.
- Client-side policy: `foundation/concurrency.py` adds a bounded gate; the shipped Ollama profiles
  set `max_inflight = 1`, `max_queue = 8`, `queue_timeout_s = 60`. The server still owns the real
  parallel slots; the gate only prevents one ASHURA process from adding an unbounded queue.

The benchmark measures serving behaviour, not answer quality. No ASHURA memory or learning path was
involved.

## Results

### Server and resource cost

| `OLLAMA_NUM_PARALLEL` | Runtime s | Ollama model MB | Server-tree RSS MB | System RAM max | CPU max | Failures |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 191.71 | 4,635.9 | 5,227.5 | 80.2% | 69.3% | 0 |
| 2 | 141.77 | 4,753.3 | 5,672.8 | 83.6% | 100.0% | 0 |
| 4 | 211.32 | 5,136.1 | 6,092.6 | 87.7% | 100.0% | 0 |

RSS is the sum of the dedicated server process and its `llama-server` child. The model column is
Ollama's reported footprint, not proof of dedicated 2 GB MX350 residency.

### Latency and throughput

| Server slots | Clients | p50 ms | p95 ms | Tokens/s | Throughput x1 | Latency x1 | Failures |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 1 | 6,565 | 6,593 | 4.93 | 1.00 | 1.00 | 0 |
| 1 | 2 | 8,828 | 12,004 | 5.43 | 1.10 | 1.34 | 0 |
| 1 | 4 | 13,528 | 21,762 | 5.95 | 1.21 | 2.06 | 0 |
| 2 | 1 | 5,011 | 5,125 | 6.37 | 1.00 | 1.00 | 0 |
| 2 | 2 | 6,855 | 7,197 | 9.21 | **1.45** | 1.37 | 0 |
| 2 | 4 | 11,192 | 22,377 | 7.55 | **1.19** | 2.23 | 0 |
| 4 | 1 | 9,817 | 10,023 | 3.32 | 1.00 | 1.00 | 0 |
| 4 | 2 | 13,274 | 14,218 | 4.89 | 1.47 | 1.35 | 0 |
| 4 | 4 | 14,817 | 16,973 | 8.26 | 2.48 | 1.51 | 0 |

`Throughput x1` is aggregate tokens/s divided by that server configuration's one-client value;
`Latency x1` is p50 divided by that configuration's one-client p50. Every row completed with 0
failures; every measured request generated 32 tokens. Maximum recorded load time was 59 ms, so no
request paid a model reload.

## Reading the result

- **One slot is a queue.** Throughput stayed essentially flat from 1 to 4 clients (4.93 to 5.95
  tokens/s, 1.21x) while p50 rose from 6.57 s to 13.53 s. The small throughput movement is within
  the run-to-run noise seen on this laptop; it is not evidence of parallel serving.
- **Two slots help two clients, not four.** Two slots produced 9.21 tokens/s at 2 clients (1.45x
  over their own 6.37 single-client value) with p50 6.86 s. At 4 clients the gain fell to 1.19x
  (7.55 vs 6.37) and p95
  reached 22.4 s because two requests waited for the second wave. Effective parallelism is roughly
  1.5 slots, not 2.
- **Four slots are counterproductive on this laptop.** Single-client p50 rose to 9.82 s and
  throughput fell to 3.32 tokens/s, below both one slot (4.93) and two slots (6.37). At 4 clients
  it reached 8.26 tokens/s with p50 14.82 s, but the server-tree RSS rose to 6.09 GB and system RAM
  peaked at 87.7%.
  The extra slot memory is the likely cause; 4-way serving is not a good trade for an interactive
  personal tutor.
- **Run-to-run variance is material.** An earlier exploratory pass (not the saved run) showed the
  same shape with different absolute numbers: one slot at 7.08 tokens/s single-client, two slots at
  10.72 tokens/s with 2 clients, and four slots at 3.60 tokens/s single-client. At four clients that
  pass gave 6.85 tokens/s for four slots versus 9.66 for two, so the four-slot four-client advantage
  in the saved run did not replicate. The direction of the decision is stable; fine-grained
  differences between 2 and 4 clients are not.

## Decision

1. Keep **`OLLAMA_NUM_PARALLEL=1`** as the safe default for single-user interactive use. It has the
   lowest memory footprint and the best single-client latency.
2. If concurrent serving is explicitly wanted, use **`OLLAMA_NUM_PARALLEL=2` at most**. Expect about
   1.45x aggregate throughput at two clients, little or no reliable gain at four, and a larger tail
   (p95 22.4 s at four clients). Do **not** use four slots on the target laptop: it cuts
   single-client throughput to 3.32 tokens/s and raises RAM to 87.7%.
3. Keep the per-process client policy at `max_inflight=1`, `max_queue=8`,
   `queue_timeout_s=60`. A single ASHURA CLI process is interactive and should not flood the server.
   If one process is deliberately serving two concurrent requests, raise `max_inflight` to 2 only
   when the server has two slots; do not set it to 4.
4. Do not claim linear 4-way scaling, production multi-tenant serving, or 4-way GPU parallelism.
   This experiment demonstrates bounded queueing and a measured two-slot improvement on one laptop.

## Limitations

- One model, one prompt family, one machine, one saved sweep. The prompt always generates 32 tokens
  and the first token/prefill cost is included in latency.
- Temperature telemetry was unavailable; thermal state and background Windows activity can explain
  part of the run-to-run spread.
- The client gate is per process. Four independent ASHURA processes each with `max_inflight=1` can
  still put four requests in the server's queue; only the server setting and `OLLAMA_MAX_QUEUE`
  bound that. No cross-process shared queue or multi-worker scheduler is claimed.
- The 2 GB MX350 cannot hold the 4.7 GB model exclusively; Ollama's reported footprint is not
  dedicated VRAM, and the four-slot result is consistent with shared-memory pressure rather than a
  clean GPU-parallelism measurement.

## Evidence

- `experiments/runtime/concurrency_sweep.json` - saved sweep (server env, resources, per-request rows).
- `evaluation/concurrency_bench.py` - benchmark implementation.
- `experiments/runtime/concurrency_sweep.py` - private-server orchestration.
- `foundation/concurrency.py`, `foundation/ollama_model.py` - bounded client gate and wiring.
- `tests/test_concurrency.py` - queue-full, timeout, release and Ollama integration tests.
