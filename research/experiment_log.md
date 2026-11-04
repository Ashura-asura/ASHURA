# Experiment log

**Hardware for ALL entries below:** a sandbox container (1 vCPU, ~4 GB RAM, Linux, Python 3.12, SQLite 3.45.1).
This is **not** the target laptop (i7-1165G7 / 16 GB). Latency and RAM numbers are only relative; Phase 0 requires re-running on the target machine.

---
## EXP-001 - AMA vs store-everything
- **Hypothesis:** H-AMA
- **Baseline:** `StoreEverything` (episodic + FTS5 for every item)
- **Proposed change:** `learning/ama.py` with default weights, and a discard-threshold sweep (0.45 / 0.8 / 1.0 / 1.2)
- **Dataset:** synthetic, seeded (seeds 1-3, results averaged), ~1,200 items/seed: 200 verified facts, 0-3 formatting-noise repeats each, 20% reworded restatements, 30% contradicting unverified claims, 600 noise chit-chat items. Author-written, same author as AMA.
- **Evaluation:** for each fact question, FTS5 top-3: hit@3, acc@1, top-1 returned the *wrong* code ("false memory"); rows, DB size, retrieval ms, admission ms/item
- **Weights:** uncalibrated defaults (config/ashura.toml)

| system | episodic rows | fts rows | DB KB | hit@3 | acc@1 | false-memory@1 | retrieval ms | noise kept | admit ms/item |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 1203 | 1203 | 768 | 1.00 | 0.90 | 0.10 | 1.53 | 100% | 0.64 |
| AMA @0.45 (default) | 900 | 800 | **967** | 1.00 | 1.00 | 0.00 | 1.07 | 100% | 3.56 |
| AMA @0.8 | 850 | 769 | 965 | 1.00 | 1.00 | 0.00 | 0.97 | 95% | 3.43 |
| AMA @1.0 | 439 | 358 | 699 | 1.00 | 1.00 | 0.00 | 0.66 | 26% | 2.20 |
| AMA @1.2 | 288 | 208 | 619 | 1.00 | 1.00 | 0.00 | 0.54 | 1% | 1.82 |

- **What the data supports:** On this stream, contradiction handling removed the baseline's 10% false-memory-at-rank-1 rate; rows and retrieval latency dropped with the threshold, with no loss of hit@3.
- **What it does not support:**
  - "Noise" was defined by me as worthless, so discarding it is rewarded by construction. There are no *useful unverified* items in the stream; a high threshold would likely discard those (untested, and the likeliest real-world failure).
  - At the **default** threshold AMA stores only ~25% fewer rows and the DB is **larger** than baseline (extra tables: facts, admission_log, dream_queue) and admission is ~5x slower per item.
  - 63% of reworded-but-true restatements were flagged `REVIEW_REQUIRED` (false conflicts) - see failures F-002.
  - The accuracy gain mostly comes from conflict handling, not from the admission score itself. An ablation (conflict handling only, no scoring) has not been run.
- **Update after F-002 fix (see EXP-001b below):** the 63% false-conflict figure no longer holds.
- **Decision:** **modify.** Keep conflict handling + logging; do not adopt any discard threshold until calibrated on realistic data with useful-unverified items; fix F-002 first.

---
## EXP-002 - FTS5 retrieval latency vs corpus size (Phase 1 / Step 3)
- 30-word documents, 4-term OR queries, limit 5, 200 queries each, same sandbox.

| rows | p50 ms | p95 ms | DB MB |
|---|---|---|---|
| 1,000 | 0.063 | 0.099 | 0.5 |
| 10,000 | 0.342 | 0.437 | 3.9 |
| 50,000 | 1.108 | 2.075 | 18.9 |
| 200,000 | 4.316 | 4.772 | 75.1 |

- **Conclusion:** FTS5 latency is negligible next to LLM inference at these sizes, supporting the spec's "no vector DB until measured need". Latency grows roughly linearly with rows (OR queries scan every posting list). Retrieval *quality* is not measured here (synthetic random words). **Decision:** keep.

---
## EXP-003 - NFD routing vs always-run pipeline
- **Hypothesis:** H-NFD. **Baseline:** `always_all` (every *available* module). **Dataset:** 14 hand-written prompts (chat, arithmetic, memory, image, reasoning) with hand-assigned required modules. Same-author caveat applies.
- Result: always-all = 4 modules/request; NFD mean = 1.43. Required-and-available modules missed: 0. Unneeded modules activated: 0. Routing overhead: mean 0.084 ms, max 0.109 ms.
- **Process note:** my first run reported 4 "unneeded" activations. Cause was a labelling error in my ground truth (I omitted `verification` for arithmetic prompts, which the spec requires). I corrected the label, not the router.
- **Limits:** only 4 modules exist yet (OCR, reasoning, learning, semantic retrieval are placeholders), module costs are placeholder estimates, and the prompts were written alongside the keyword rules. This shows the plumbing works, not that NFD generalises. **Decision:** keep, revisit when more modules exist.

---
## EXP-000 - Baseline benchmark harness (Phase 0, partial)
- `evaluation/benchmarks/baseline_v1.jsonl` has 16 items. The Echo stub scores 18.75%: it repeats the question, and some accepted answers (e.g. "6", "yes") occur in the prompt text. So the substring judge is gameable and the score is only a floor for plumbing. **No real Qwen baseline exists yet.** Phase 0 is incomplete until one is run on the target laptop.

---
## EXP-004 - Titans-inspired adaptive memory (Phase 4)
- **Hypothesis:** H-ADAPT. **Baselines:** no memory (chance = 1/1,000+ codebook entries, ~0.001) and FTS5 retrieval on the same questions.
- **Proposed change:** `memory/adaptive_memory.py` - linear associative memory M (dim_v x dim_k), surprise-driven delta update with optional momentum, decay, surprise gate, IDF-weighted hashed-token keys. 65,536 parameters at dim 256 (0.26 MB float32, same again for the momentum buffer); size does **not** grow with experience.
- **Hardware:** sandbox (1 vCPU, ~4 GB). NumPy, not PyTorch (PyTorch was not installable here; the linear-memory gradient is analytic).
- **Dataset:** synthetic, seeded (1-3 averaged), author-written. Question -> 4-digit code. "Related" = 3 unseen paraphrases per fact (different wording, same entity token). Decoding = nearest codebook entry (facts + 1,000 distractors). lr tuned per variant on a separate validation seed (100); lr plateau checked down to 0.01.
- **Results (dim 256, N=100, single pass):**

| variant | exact | related (unseen paraphrases) |
|---|---|---|
| plain delta, no IDF | 0.010 | 0.027 (<= 0.06 at any lr) |
| + IDF | 0.997 | 0.992 |
| + IDF + momentum .5 | 0.997 | 0.993 |
| + IDF + decay .01 | 0.823 | 0.933 |
| + IDF + surprise gate .1 | 0.997 | 0.992 |
| + IDF, 3 passes | 0.997 | 0.992 |
| **FTS5** | **1.000** | **1.000** |

  Capacity (related accuracy, +IDF): dim 128: 0.93 / 0.79 / 0.69 / 0.50 / 0.23 at N = 100 / 200 / 400 / 800 / 1600; dim 256: 0.99 / 0.98 / 0.93 / 0.86 / 0.69; dim 512 (262k params): 0.998 ... 0.977 at N=1600. FTS5 = 1.000 throughout.

  Interference (learn A=100 facts, then a second 100-fact task, re-test A exact): unrelated wording 0.997 -> 0.987; **same wording, new entities** 0.993 -> 0.993; with decay .01 the same-wording case falls 0.840 -> 0.453. After `reset()` A accuracy = 0.000 (chance level).

  Cost: write ~0.23 ms, read+decode over 1,100 candidates ~0.07 ms per item at dim 256.
- **What the data supports:**
  - The module learns from a single exposure, improves on later unseen related examples far above chance, and resets independently (Phase 4 completion criteria are met **against the no-memory baseline**).
  - IDF-style down-weighting of common tokens is essential: raw hashed-token keys share ~87% of their content, and without weighting the memory is near chance.
  - Momentum gave no measurable benefit here; the surprise gate saved nothing measurable here (no accuracy loss); decay hurt retention by design.
  - Capacity is bounded by dimension (dim 256 degrades past ~400 facts), as expected for a linear associative memory.
- **What it does NOT support:**
  - **No advantage over FTS5.** FTS5 was perfect on every task and has no capacity limit at these sizes. On lexically-overlapping lookups the neural memory can at best tie.
  - "Related" here means sharing the entity token, which FTS5 also exploits. Semantic generalisation (no word overlap) is untested, and hashed-token keys cannot provide it; that would need learned embeddings.
  - The low interference is largely because distinct entity tokens give near-orthogonal IDF-weighted keys. Genuinely conflicting updates (same key, new value) were not tested; they are expected to overwrite.
  - Synthetic data, single template family, three seeds, same author.
- **Decision:** **keep as an experimental component; do not adopt into the response path.** No claim that adaptive memory improves ASHURA. Next valid test needs a task where lexical retrieval fails (semantic/compositional recall) with a learned or pretrained encoder, plus a same-key conflict test.

---
## EXP-001b - AMA re-run after the F-002 fix (answer comparison by value, not token overlap)
- Same stream, seeds 1-3, same weights as EXP-001. Only `answers_agree` changed.

| metric (AMA @0.45) | before | after |
|---|---|---|
| reworded-true restatements flagged REVIEW_REQUIRED | 63.1% | **0.0%** |
| episodic rows (baseline 1203) | 900 | 858 |
| DB KB (baseline 768) | 967 | 951 |
| acc@1 / false-memory@1 | 1.00 / 0.00 | 1.00 / 0.00 |
| wrong claims kept out of the index | 66.3% | 66.3% |
| admit ms/item (baseline 0.53) | 3.56 | 3.32 |

- **What it supports:** the false-conflict problem on this stream is gone with no loss of contradiction detection (8/8 adversarial pairs in tests/test_ama.py still flagged). Merging rewordings also removed ~42 redundant rows.
- **What it does not support:** the rewordings are the author's own (`"code is N"` vs `"The access code for project P is N"`). Real paraphrases without shared values or content words are not understood and fall back to "conflict". The DB is still larger than store-everything and admission still ~6x slower (F-004). **Decision:** keep.

---
## EXP-005 - Same-key conflicting updates (F-009)
- 100 facts learned, then 40 of the same questions receive a different answer. Seeds 1-3. `experiments/adaptive_memory/conflict.py`.

| system | new value returned | old value returned | untouched facts still right |
|---|---|---|---|
| adaptive memory, lr 0.3 / 0.6 / 1.0, 1 pass | 1.00 | 0.00 | 1.00 |
| adaptive memory, lr 0.3, 3 passes | 1.00 | 0.00 | 0.93 |
| AMA + FTS5, **stronger** evidence (user_corrected over trusted_material) | 1.00 | 0.00 | history kept 100% |
| AMA + FTS5, **weaker** evidence (unverified over trusted_material) | 0.00 | 1.00 | history kept 100% |

- **Finding:** the neural memory always lets the newest write win; it cannot tell a correction from a wrong claim. AMA + FTS5 can. Another reason D-009 stands: the adaptive memory must stay behind AMA's reliability gate. (Note: a `user_corrected` 0.9 answer does not override a `verified` 1.0 fact; it is flagged for review - by design.)
- **Limits:** synthetic, 3 seeds, linear memory only, single conflict per key.

---
## EXP-000b - Baseline harness after the judge fix
- Echo stub: 18.75% (old substring judge) -> **0.0%** lenient and strict (new judge, v1 and v2 suites). Still no real-model baseline: run `python -m evaluation.ollama_baseline` on the target laptop. Its output (results/baseline_*.md) belongs here as EXP-000c.

---
## EXP-006 - DREAM replay vs new-only training (H-DREAM, Phase 6)
- **Hypothesis:** H-DREAM. **Baseline:** candidate trained only on the new capability. **Proposed:** DREAM replay + NGR.
- **Setup:** synthetic, 20 old + 20 new facts (plus reordered held-out variants), dim 256 linear adaptive memory; both arms start from the same stable old-capability memory; `experiments/dream/run.py`. Single seed, author-written. **Not** the target hardware.
- **Results:**

| arm | new capability | old retention | NGR | promoted |
|---|---|---|---|---|
| new-only | 1.00 | **0.00** | rejected: old 1.00 -> 0.00 | no |
| DREAM replay | 1.00 | **1.00** | all conditions met | yes |

- **Supports:** in this task, replay prevents catastrophic interference and the NGR rejects the candidate that forgets. Candidate promotion and stable retention are real (files + manifest).
- **Does not support:** generalisation beyond reordered lexical variants; the memory is still the Phase 4 NumPy module, not a language-model adapter. Single seed, same-author data. Replay proportions are uncalibrated. **Decision:** keep the pipeline; treat the result as a pipeline demonstration, not evidence that DREAM improves Qwen.

---
## EXP-000c - Real Phase 0 baseline on the target laptop (Windows 11, i7-1165G7, 16.9 GB, MX350 2 GB)
- **Suite:** `baseline_v2.jsonl` (16 items, hash de09e3c57acd647d), greedy, `think=false` for Qwen3.5.
- **Hardware:** target laptop, Python 3.13, Ollama local server. Results: `results/baseline_20261102_*.md/.json`.

| model | quant | strict | lenient | p50 ms | p95 ms | tok/s | server MB | verdict |
|---|---|---|---|---|---|---|---|---|
| tony_control:7b (Qwen2 7.6B fine-tune) | Q4_K_M | **0.94** | 0.94 | **50,717** | 90,331 | 7.3 | 4,636 | accurate but unusable interactively |
| qwen3.5:2b (Qwen3.5 1.9B, vision) | Q8_0 | 0.56 | 0.69 | **4,497** | 4,566 | 16.5 | 2,341 | selected fast foundation |
| lfm3:latest (1.7B) | Q4_K_M | 0.12 | 0.12 | 3,226 | 4,002 | 22.2 | 1,404 | not a foundation candidate |

- Qwen3.5 per-category strict: arithmetic 0.20, factual 0.80, instruction 0.75, reasoning 0.50.
- **Finding:** the 7B model does not fit the 2 GB MX350; `server_vram_mb` reported 4,636 and latency was dominated by CPU/GPU thrashing, not generation (19.5 generated tokens at 7.3 tok/s). The 2B model fits the budget and is the only measured model that is both usable and non-trivial.
- **Limits:** 16 author-written questions; Wilson CIs are wide (Qwen3.5 0.33-0.77). `tony_control:7b` was deleted after measurement, so its row is not reproducible without re-pulling. Qwen3.5 arithmetic is weak; ASHURA's exact-arithmetic route answers those without the LLM (smoke test: verified 391 in 1.1 ms).
- **Decision:** pin `qwen3.5:2b` as the Phase 0 stable foundation. Keep the 7B result as the quality baseline; re-pull only for offline adapter experiments.

---
## EXP-000d - Reference re-measurement after model-tag drift (2026-11-05)
- **Why:** `ref-base:7b` and the earlier `tony_control:7b` are no longer installed. `DEFAULT_REFERENCE` now points at `tony:7b` (Qwen2 7.6B, Q4_K_M, digest `0455603ff430`). This is not the historical 7B artifact (`c20c7b08841f`), so the two are not interchangeable.
- **Setup:** same suite `baseline_v2.jsonl` (16 items, hash `de09e3c57acd647d`), greedy (`temperature=0`, `seed=0`), `think=false`, target laptop, Python 3.13. Results: local `results/baseline_20261105_044047.{md,json}` (the `results/` directory is git-ignored by design).

| model | digest | strict | lenient | p50 ms | p95 ms | tok/s | load s | server MB | vs tony:7b |
|---|---|---|---|---|---|---|---|---|---|
| tony:7b | 0455603ff430 | **0.94** | 0.94 | **2,351** | 4,481 | 10.4 | 10.1 | 4,636 | reference |
| qwen3.5:2b | 0689d44085e0 | 0.56 | 0.69 | 3,899 | 3,964 | 19.1 | 8.2 | 2,341 | 1 win / 7 losses, p=0.07 |
| lfm3:latest | b36a103fe2f8 | 0.56 | 0.75 | 3,460 | 5,072 | 19.5 | 12.4 | 1,404 | 1 win / 7 losses, p=0.07 |

- Per-category strict (arithmetic/factual/instruction/reasoning): tony 1.00/0.80/1.00/1.00; qwen 0.20/0.80/0.75/0.50; lfm3 0.20/1.00/0.75/0.00.
- **Finding:** tony:7b keeps the historical 0.94 strict accuracy but measured 2.35 s p50 here, not the 50.7 s recorded for `tony_control:7b`; because the digests differ, the old latency result is not evidence about this artifact (and vice versa). The current build still reports a 4.6 GB footprint, above the 2 GB MX350 budget.
- **Statistics:** raw accuracy differs by 6/16, but only 8 pairs are discordant, so the exact sign test gives p=0.07. At alpha=0.05 the suite cannot declare tony:7b better; this is a power limit, not parity.
- **Reproducibility caveat:** lfm3 (same digest) scored 0.125 strict on 2026-11-02 18:21 and 0.56 on 2026-11-02 21:50 and 2026-11-05; the first run returned empty responses, consistent with a thinking/`num_predict` interaction. Single runs of thinking models are not stable until that path is pinned.
- **Decision:** use `tony:7b` as the default comparison reference and the live foundation (D-025, supersedes D-017); `qwen3.5:2b` remains the 2.3 GB fallback. `config/module_costs.json` is recalibrated from the tony:7b row of this run.

---
## EXP-B1 - BrainSim tiny baseline + first fast-memory experiment (v2 blueprint)
- **Hypotheses:** H-B1 (a small GRU learns hidden permutation rules), H-FM (an isolated fast memory improves a later related unseen-rule sequence), H-KEY (context keys reduce old-task interference).
- **Setup:** independent `BrainSim/` subproject; 16 symbols, 8 training + 8 disjoint held-out single-cycle permutations, 3 seeds; hidden 128 (206k params) vs 384 (1.8M); 30 epochs on CPU. Study 12 transitions, test 16 from the same held-out rule. Arms: frozen, recurrent-state carry, token-keyed memory, pair-keyed memory. Full report: `BrainSim/research/experiment_log.md`.
- **Results (means):**

| arm | train-rule acc | frozen unseen | adapted unseen | old-rule active | old-rule after reset |
|---|---:|---:|---:|---:|---:|
| hidden 128 | 0.957 | 0.085 | token **0.771** / pair **0.681** | token 0.309 / pair 0.904 | 0.957 |
| hidden 384 | 0.957 | 0.096 | token **0.777** / pair **0.688** | token 0.309 / pair 0.904 | 0.957 |

- **Supports:** B1 learns the training rules; fast memory raises unseen-rule accuracy from ~0.09 to 0.68-0.78; save/load reproduces the adapted accuracy exactly; pair keys cut cross-task interference from 64.8 to 5.3 points.
- **Does not support:** rule induction (memory is a lookup; coverage 0.75 token / ~0.65 pair); safe cross-task use (both arms exceed the 2% retention tolerance while active); a benefit from 8.7x more parameters. Study-state carry alone scored 0.081, so the gain is the memory, not hidden-state context.
- **Decision:** keep BrainSim independent and task-scoped; no ASHURA integration yet. Next: B2 working memory/delayed recall and B3 gated/surprise plasticity. See `BrainSim/research/decisions.md`.

---
## EXP-B2 - Delayed recall: recurrent core vs fixed MLP (v2 blueprint B2/B6)
- **Hypotheses:** H-B2 (the GRU solves trained-delay recall), H-DELAY (the GRU generalizes to longer delays better than a fixed MLP), H-COST (compare parameters and training time).
- **Setup:** 3 cue symbols, blank delay, GO, reproduce cues. Train delays 2/4/6/8; evaluate 1/2/4/6/8/12/16/20. 4,096 sequences, 30 epochs, 3 seeds, CPU. GRU 204,183 params; parameter-matched MLP 217,560. Full report: `BrainSim/research/experiment_log.md` BS-EXP-002.
- **Results:** both arms scored 1.000 token and 1.000 full-recall at every delay, including unseen 12-20. GRU trained 112-144 s/seed; MLP 9-18 s/seed.
- **Supports:** the GRU can hold and reproduce cue information across a 20-step delay; B2's capability check is met.
- **Does not support:** a recurrent advantage. H-DELAY is falsified; the fixed MLP is equally accurate and much faster. The task only requires copying the cue block, so recurrence is not necessary. The MLP is a strong upper bound, not a memoryless baseline (memoryless is at chance: 1/8 token, 1/512 full).
- **Decision:** keep B2 as a capability baseline. Do not cite it as evidence for recurrence. Next: B2b with variable-length cues or a relational/delay-dependent query.

---
## EXP-B3 - Task-scoped gate vs shared memory (v2 blueprint B3)
- **Setup:** two disjoint 16-symbol permutation rules, full transition coverage, verified writes, 3 seeds. Shared arm uses one token-keyed fast memory; gated arm uses `TaskScopedMemory` with external task IDs. Full report: `BrainSim/research/experiment_log.md` BS-EXP-003.
- **Results (means):** shared old-rule accuracy 1.000 before switch -> **0.104** after; gated 1.000 -> **1.000**; new-rule accuracy 1.000 for both.
- **Supports:** per-task isolation prevents overwrite; bounded cache and save/load are implemented and tested.
- **Does not support:** learned task identification, boundary detection, or surprise-gated admission. The task ID is supplied externally and all writes are verified, so the gate's admission logic is bypassed in this experiment.
- **Decision:** task-scoped memory remains the only safe operating mode; do not integrate BrainSim into ASHURA yet.

---
## EXP-007 - HARN addition candidate vs exact arithmetic
- **Setup:** NumPy linear least-squares model `y = w1*a + w2*b + bias`, trained on 50,000 random integer pairs in [-1000, 1000], evaluated on 5,000 held-out pairs. Seed 0. `skills/arithmetic/train_addition.py`.
- **Results:** exact match 1.000, MAE 0.000, train time 0.016 s. The fitted weights are ~1.0/1.0 with bias ~0.
- **Supports:** the candidate plumbing works and agrees with exact arithmetic on this distribution.
- **Does not support:** neural arithmetic as a capability. This is a linear model on a linear function, not a deep network; it adds nothing over `skills/arithmetic/exact.py`. The exact path remains authoritative, and the candidate is logged only as agreeing/rejected.
- **Decision:** keep the candidate behind a checkpoint and the exact path as the answer source. Do not claim HARN success. A real HARN test needs a task where a learned model is competitive under held-out distribution shift (for example digit-string arithmetic), compared with exact evaluation.
