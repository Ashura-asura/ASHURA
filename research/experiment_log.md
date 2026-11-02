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
