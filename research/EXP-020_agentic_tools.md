# EXP-020 - Native tool-use benchmark: `tony:7b-agentic3` vs `tony:7b-gpa3`

Date: 2026-11-06. Status: **negative result; agentic3 does not displace gpa3 for tool use.**

## Hypothesis and baseline

Hypothesis: the `tony:7b-agentic3` fine-tune improves native tool selection, multi-step chaining
and error recovery over the general tutor `tony:7b-gpa3`. Baseline: gpa3 on the same frozen suite,
same decoding, same tools, one model resident at a time. Both are Qwen2 7.6B Q4_K_M tags.

## Suite and tools

`evaluation/benchmarks/agentic_tools_v1.jsonl`, 12 author-written items, frozen before either run
(sha256 `ed3a5345db8a94e0d2f2fe3b32a57143dd8212a1e041a22888a54c43334e4980`). Categories: 3 calc,
2 lookup, 2 text, 2 multi-step, 1 recovery, 2 direct/no-tool controls. Tools are Ollama-native
`/api/chat` functions: `calc` (exact AST arithmetic), `lookup` (fictional local catalog), and
`text_stats` (word/character count). Tool execution is deterministic and local.

Pre-registered decision: adopt agentic3 for tool use only if it wins at least 3 more items on
`agentic_success`, loses at most 1, and its clean rate is at least gpa3's. Otherwise keep gpa3 and
record the negative result.

## Configuration

- Ollama 0.40.14, temperature 0, seed 0, top_p 0.9, `num_ctx` 4096, `num_predict` 240.
- `tony:7b-gpa3` digest `2a86766287cf`; `tony:7b-agentic3` digest `0efe3817d5c1`.
- One model per run; every loaded model was unloaded before the next run. Total measured runtime
  171.03 s. No external API.

## Results

| model | answer | tool | agentic | clean | recovery | p50 ms | p95 ms | steps | calls | tok/s | load s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tony:7b-gpa3` | 0.917 (11/12) | 1.000 | **0.917 (11/12)** | 1.000 | 1.000 | 5844 | 12024 | 2.25 | 1.25 | 9.92 | 5.1 |
| `tony:7b-agentic3` | 0.917 (11/12) | 1.000 | **0.917 (11/12)** | 1.000 | 1.000 | 6333 | 10422 | 2.17 | 1.17 | 9.74 | 7.1 |

Paired comparison: 0 wins, 0 losses, 12 ties (sign test p=1.000). `agentic_success` requires the
correct final answer, the required/allowed tool set and call count, no turn-limit, and successful
recovery where expected. Both models used the calculator on `calc-03` and returned 512, fixing the
`2 ** 3 ** 2` error seen in the subject suite. Both passed the recovery item by trying
`missing-key`, receiving an error, then looking up `fallback-key`. Both left tools unused on the
two direct controls.

## Failure analysis

Both models failed the same item, `lookup-01` ("launch code for project ORION"). Each called
`lookup` with the natural-language string `"project ORION launch code"` instead of the catalog key
`"orion"`, received `key not found`, and reported the error instead of retrying with the short key.
This is a shared entity-to-key mapping failure, not an agentic3 regression. The suite therefore has
one item on which both models fail, and no item that distinguishes them.

## Decision

Keep `tony:7b-gpa3` as the tool-use / general model. `tony:7b-agentic3` shows no measurable tool-use
advantage on this suite, is slower at p50 (6.33 s vs 5.84 s) and loaded more slowly (7.1 s vs 5.1 s).
It is not promoted. This is a retained negative result (D-060).

## Limitations

- 12 author-written items, one run per model; the suite is not an independent capability estimate.
- Synthetic catalog and hand-written tools; results may not transfer to real APIs or longer plans.
- Lookup-01's failure is a prompt/key-design weakness shared by both models; it was not changed
  after the run.
- Latency is a single run on a laptop whose 4.7 GB model exceeds the 2 GB dedicated GPU; Ollama's
  4755 MB report is not credible as dedicated VRAM residency.
- No privacy, safety or general agentic-intelligence claim.

Data: `experiments/foundation/agentic_tools.json` (tracked); raw runs in gitignored `results/`.
Harness: `evaluation/agentic_bench.py`.
