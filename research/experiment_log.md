# Experiment log

**Hardware:** early entries below were measured in a sandbox container (1 vCPU, ~4 GB RAM, Linux,
Python 3.12, SQLite 3.45.1), not the target laptop (i7-1165G7 / 16 GB), so their latency and RAM
numbers are only relative. EXP-014, EXP-015 and EXP-016 were run on the target Windows laptop and
record their own environment. Phase 0 real-model numbers remain scoped to the machine named in their entry.

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
| AMA + FTS5, **verified** evidence (1.0) over trusted_material (0.8) | 1.00 | 0.00 | history kept 100% |
| AMA + FTS5, **user-provided correction** (0.6) over trusted_material (0.8) | 0.00 | 1.00 | history kept 100% |
| AMA + FTS5, **unverified** evidence (0.2) over trusted_material | 0.00 | 1.00 | history kept 100% |

- **Finding:** the neural memory always lets the newest write win; it cannot tell a correction from a wrong claim. AMA + FTS5 can. Another reason D-009 stands: the adaptive memory must stay behind AMA's reliability gate. Phase 1 (P06) lowered user-provided material to 0.6, so a user correction is now stored as review evidence and does **not** override a trusted 0.8 fact or a verified 1.0 fact. Only independently verified evidence supersedes trusted material. The verified-correction path (CAGE -> bounded update -> candidate -> NGR) is Phase 3.
- **Limits:** synthetic, 3 seeds, linear memory only, single conflict per key.

---
## EXP-000b - Baseline harness after the judge fix
- Echo stub: 18.75% (old substring judge) -> **0.0%** lenient and strict (new judge, v1 and v2 suites). Still no real-model baseline: run `python -m evaluation.ollama_baseline` on the target laptop. Its output (results/baseline_*.md) belongs here as EXP-000c.

---
## EXP-006 - DREAM consolidation arms (H-DREAM, Phase 6; four-arm update in Phase 1)
- **Hypothesis:** H-DREAM. **Baseline:** candidate trained only on the new capability. **Proposed:** DREAM replay + NGR.
- **Setup:** synthetic, 20 old + 20 new facts (plus reordered held-out variants), dim 256 linear adaptive memory; every arm uses the same stable old-capability artifact and the same NGR policy; `experiments/dream/run.py`. Single seed, author-written. **Not** the target hardware. The Phase 1 update measures all four arms required by P12, fixes the answer vocabulary from the training split (P13), and uses the real stable artifact as the baseline (P14).
- **Results:**

| arm | new capability | old retention | NGR | promoted |
|---|---|---|---|---|
| stable + new | 1.00 | **1.00** | all conditions met | yes |
| stable + replay | 1.00 | **1.00** | all conditions met | yes |
| fresh + new | 1.00 | **0.00** | rejected: old 1.00 -> 0.00 | no |
| fresh + replay | 1.00 | **1.00** | all conditions met | yes |

- **Supports:** fresh initialization without replay causes catastrophic interference in this task; replay prevents it; the NGR rejects the forgetful candidate; starting from the stable memory also retains the old capability; candidate promotion and stable retention are real (files + manifest).
- **Does not support:** a general replay advantage. stable+new and stable+replay tie at 1.00 in this small, single-seed task where all facts fit the memory. It also does not generalise beyond reordered lexical variants, and the memory is still the Phase 4 NumPy module, not a language-model adapter. Replay proportions are uncalibrated. **Decision:** keep the pipeline and the four-arm measurement; treat the result as a pipeline demonstration, not evidence that DREAM improves Qwen or that replay is always required. See F-033.

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

---
## EXP-008 - Phase 1 trust repair (P01-P14, 2026-11-05)
- **Question:** can an unverified answer be treated as verified or promoted merely because it passed through the response pipeline?
- **Changes:** tri-state verification (`VERIFIED` / `FAILED` / `UNAVAILABLE`), reliability-aware retrieval with provenance labels, separate `user_provided` records at 0.6, `verified`-only semantic/DREAM admission, NGR non-finite/range/required-capability/performance validation, four-arm DREAM measurement with stable initialization, training-only answer vocabulary, and a real cold-start baseline requirement.
- **Evidence:** ASHURA **204 passed** (Windows/Python 3.13); BrainSim **46 passed** (unchanged). 12 dedicated Phase 1 trust tests plus NGR, DREAM and CAGE regression tests. DREAM results in EXP-006; conflict results in EXP-005.
- **Supported:** the response path no longer marks `None`/unavailable verification as success; a language-generated reply cannot borrow an arithmetic verification result; unverified FTS records are not retrieved by default; user corrections are stored separately and are not counted as verified; NGR rejects NaN/inf, out-of-range scores, missing capabilities and (when required) missing performance measurements; DREAM refuses a fabricated zero baseline.
- **Not supported:** the full CAGE -> candidate -> NGR learning loop, independent natural-language correction verification, calibrated AMA weights, a general replay advantage, or any real-model accuracy improvement from these safety changes. This is an engineering/trust result, not a capability result.
- **Decision:** keep the Phase 1 changes; proceed to Phase 2 (memory reliability) before claiming the learning loop is complete. Details and remaining limits: `research/phase1_trust.md`.

---
## EXP-009 - AMA calibration, admission cost and storage (P15-P17, 2026-11-05)
- **Setup:** synthetic project stream, 3 seeds, labelled useful/repeated/contradictory/unverified/noise records; threshold sweep 0.0-2.0; `experiments/ama/calibrate.py`. Target laptop is not used.
- **Results:** at the default 0.45, precision 0.350 / recall 1.000 (294 negatives admitted); at 1.4, 0.994/1.000; at 1.6, 1.000/1.000. On the original EXP-001 stream admission fell to 1.40 ms/item vs 1.13 ms store-everything (1.24x, previously ~6x); DB size 1184 KB vs 931 KB (+27%).
- **Storage breakdown:** `admission_log` ~308 KB, `facts` ~99 KB, `conflicts` ~18 KB. This is audit and derived evidence; semantic fact text is no longer duplicated when identical to its source episode.
- **Decision:** keep 0.45 as the default because it preserves unverified audit records; 1.6 is documented as the precision-maximising setting for deployments that prefer to discard them. Do not describe the synthetic threshold as truth calibration. Details: `research/phase2_memory.md`, `experiments/ama/calibration.json`.

---
## EXP-010 - Structured answer comparison and contradiction benchmark (P19/P20/P26, 2026-11-05)
- **Setup:** 28 author-written pairs (14 equivalent, 14 contradictory), covering units, dates, number words, entity ids, negation, hedges and swaps; compared with the previous lexical/parity comparator. `evaluation/contradiction_bench.py`.
- **Results:** structured comparator accuracy 1.000, Brier 0.013; lexical baseline accuracy 0.643, Brier 0.381.
- **Does not support:** general semantic understanding, synonymy, entailment or long paraphrases. Same-author data is optimistic; unknown cases are stored as conflicts, not merged.
- **Decision:** keep the rule-based comparator; do not add a local encoder without a held-out win. Details: `evaluation/contradiction_results.json`.

---
## EXP-011 - Adaptive-memory stress and long-run interference (P22/P24/P25, 2026-11-05)
- **Setup:** 100 facts, dim 256, 3 seeds; partial cues, 0/2/5/10 distractor tokens, capacity 50-400, IDF on/off; a single-seed long run of 8 x 250 writes across three task families plus 100 contradictory writes. `experiments/adaptive_memory/stress.py`.
- **Results:** exact 0.997; related 0.880 at 400 facts; noisy recall 0.95/0.77/0.41 at 2/5/10 distractors; FTS5 1.00 throughout. IDF exact 0.997 vs 0.010 without. Long run: old-task accuracy 0.84 -> 0.33 -> 0.04 across switches, ~0.90 after retraining; 5% of direct contradictory writes overwrote the old answer.
- **Supports:** IDF is essential for hashed-token keys; the adaptive memory can recall a partial cue on this synthetic task.
- **Does not support:** any advantage over FTS5, semantic generalisation, or safe task-switch retention. FTS5 remains the default; adaptive memory stays out of the response path.
- **Decision:** keep the queue gate and experimental status; do not integrate. Details: `experiments/adaptive_memory/stress.json`.

---
## EXP-012 - Retention, replay ratio and semantic provenance (P27-P29, 2026-11-05)
- **Retention:** 100 intended unverified records forgotten; 0 verified/trusted/user/recently-used/reinforced records forgotten; 0 stale FTS/fact rows; kept facts still retrievable. Utility feedback changed usefulness (0.60 accepted vs 0.00 rejected) without changing reliability 1.00. `experiments/memory/retention_bench.py`.
- **Replay:** ratios 0.25/0.5/0.75/1.0 and random/recent sampling all scored 1.00 new / 1.00 old retention on the EXP-006 buffer. The task cannot distinguish them; the default 0.5 is not a calibrated optimum. `experiments/dream/replay_sweep.py`.
- **Provenance:** semantic facts now require a verified source episode and store verification method, provenance JSON, derivation and source id; deleting the source removes the fact. Legacy facts are migrated with a legacy derivation.
- **Decision:** keep the retention policy, feedback path, replay-policy option and provenance checks. Do not claim replay calibration or fact understanding. Details: `research/phase2_memory.md`.

---
## EXP-013 - Verified-correction loop through CAGE, DREAM and NGR (P07/P75/A01-A03, 2026-11-05)
- **Setup:** synthetic old capability (20 facts, train/held-out) and corrected capability `6*7 -> 42` with two held-out wordings; a per-seed stable checkpoint trained on old facts only; dim 128, seeds 0-4, NumPy adaptive memory. `experiments/learning/loop_e2e.py`.
- **Verified + stable + replay:** CAGE attributed the failing `language` step, the fast update made `6*7` recall return `42` in 5/5 seeds, the candidate scored 1.00 old / 1.00 corrected, and NGR promoted 4/5 seeds. The stable pointer moved only on promotion.
- **Verified + fresh + no replay:** fast recall also reached `42`, but old retention fell to 0.02 mean; NGR rejected all 5 candidates on old-capability regression and the stable pointer never changed.
- **Refused arms:** an unverifiable factual correction, a false arithmetic correction and a verified correction without a trace were refused in 5/5 seeds before training; no fast update and no new stable candidate. The raw user sentences remain `user_provided`.
- **Unexpected measurement result:** the stable baseline already scored 1.00 on the corrected held-out items in seed 3 and 0.50 in seeds 1/4 (mean 0.40) through accidental associative recall. Seed 3 was therefore rejected for zero target gain, not regression. The two-item held-out set is too small for a stable estimate.
- **Supports:** the control flow is connected end to end, the controller can attribute a correction to the previous trace, CAGE refuses unattributable failures, and NGR remains the only promotion path.
- **Does not support:** language-model fine-tuning, general corrections, or long-term consolidation. Exact arithmetic (`+ - * / %`, integer powers, perfect-square roots) is the only independently verified correction type; the CLI does not configure the loop automatically. Details: `research/phase3_learning.md`, `experiments/learning/loop.json`.

---
## EXP-014 - Larger frozen verified-correction benchmark (F-044, 2026-11-05)
- **Setup:** frozen `experiments/learning/corrections_v1.json`; 10 arithmetic correction cases (multiplication, addition, subtraction, division, integer power, modulo, perfect-square root, decimal, parentheses), 3 held-out wordings per case, 20-word old capability with train/held-out split, dim 128, seeds 0-4, two arms and 5 control probes. Each case gets a fresh stable checkpoint trained on the old capability only. `experiments/learning/correction_bench.py`.
- **Corpus check:** every arithmetic correction is re-evaluated by `skills.arithmetic.exact` before the run; a mismatch would abort the benchmark. This is integrity checking, not independent authorship.
- **Verified + stable + replay:** 50/50 promoted (95% Wilson CI 0.929-1.000); target score 1.00, old score 1.00, stable target 0.00, 0 accidental stable hits; 150/150 held-out wording predictions correct; fast recall correct 50/50.
- **Verified + fresh + no replay:** 0/50 promoted; target 1.00, old 0.029 mean; stable pointer unchanged in 50/50.
- **Controls:** false arithmetic, unverified fact, irrational root, verified-but-no-trace and verified-but-unattributable were refused 25/25 with 0 fast updates, 0 new candidates and 0 stable changes.
- **Supports:** the refusal gates remain intact over a broader arithmetic set; replay + stable initialization preserves the old capability while the candidate learns each correction; NGR remains the only promotion path.
- **Does not support:** generalisation to unseen distributions, independent task difficulty, language understanding or language-model learning. The corpus is author-written and the held-out wordings share the expression tokens with the trained key, so 150/150 is an easy paraphrase check, not a natural-language benchmark. The 50/50 promotion result must not be read as a capability estimate.
- **Decision:** keep as the larger frozen non-regression/control-flow benchmark. F-044 remains partly open because independent authorship and an independent distribution are still missing. Details: `experiments/learning/correction_bench.json`, `research/phase3_learning.md`.

---
## EXP-015 - Measured module costs, sustained mix and real-model mixed load (P61-P63/P69, 2026-11-05)
- **Environment:** Windows 11, Python 3.13.14, Intel64 Family 6 Model 140 (i7-1165G7 class), 8 logical CPUs, single process, no concurrent clients. `experiments/runtime/load_bench.py`.
- **Exact arithmetic:** slowest evaluate p50 0.015 ms; Decimal(60) cross-check p50 0.007-0.012 ms across small/large multiplication, fraction chain, sqrt, modulo, power and decimal cases.
- **Memory:** 200 synthetic verified records; AMA admission p50 1.35 ms / p95 1.72 ms; FTS5 search p50 0.29 ms; AMA retrieve p50 0.35 ms; 420 KB database; process RSS 44.6 -> 46.0 MB during the memory run.
- **Controller:** `EchoModel` stub, 40 arithmetic + 20 general turns; arithmetic p50 1.21 ms / p95 1.38 ms, general p50 1.12 ms / p95 1.72 ms; 40/40 arithmetic turns exact-verified, 0 errors.
- **Learning loop and worker:** full NumPy correction job p50 24.4 ms / p95 28.7 ms, 5/5 promoted. Worker submit p50 0.004 ms; 100 no-op jobs drained in ~2 ms. The no-op job measures queue/thread overhead only, not training.
- **Sustained load:** 300 turns, 240 arithmetic; p50 1.39 ms / p95 1.78 ms / p99 2.87 ms, 0 errors, 240/240 arithmetic steps ok, ~690 turns/s, CPU utilisation 0.86, peak RSS ~95 MB (+~1 MB), DB 548 KB, first/last-quartile p50 ~1.25 / ~1.46 ms.
- **Real model (optional cold start):** `--real-model --real-cold` loads pinned `tony:7b` (digest `0455603ff430`), runs 24 free-form general turns and 8 exact arithmetic turns. Language p50 5.52 s / p95 8.06 s / p99 11.54 s; 7.4 generated tokens/s; 954 generated and 11,030 prompt tokens; median answer 182 characters; 24/24 language steps, 0 empty answers, 0 errors. Arithmetic p50 2.42 ms (bypasses the model). Ollama load 6.81 s, first turn 12.74 s; client RSS 97.0 -> 97.5 MB; client CPU utilisation 0.001 because inference runs in the server. Ollama reported 4,635.9 MB model footprint. A warm rerun measured language p50 4.76 s / p95 6.62 s.
- **Supports:** exact arithmetic, FTS5 retrieval, AMA admission and the NumPy loop are milliseconds-scale on this laptop; the sustained synthetic mix showed no error or large memory/database growth; a short cold-start `tony:7b` mixed load completes without client errors and arithmetic stays on the fast exact path while the model is loaded.
- **Does not support:** production-sustained `tony:7b` latency, concurrency, restart recovery, model reload, production database growth, answer quality, GPU residency or routing. The real-model run is 24 general turns, single process, and the free-form answers are longer than the short-answer EXP-000d baseline; the p50 values are not directly comparable. The controller's default path still uses a deterministic echo stub. Full data: `experiments/runtime/results.json`.
- **Decision:** record these as measured non-language costs plus one short real-model mixed load; keep the language row from `config/module_costs.json` separate. Do not replace routing estimates without a routing experiment. F-046 remained open at this point and was later closed for a bounded scope by EXP-016.

---
## EXP-016 - Bounded concurrency, reload, restart and 80-turn soak (F-046, 2026-11-05)
- **Hypothesis:** four concurrent ASHURA clients can complete 80 mixed turns without failures; one forced `tony:7b` unload/reload works; a record written by one ASHURA process survives a fresh process.
- **Baseline:** EXP-015 single-client cold-start language p50 5.52 s (24 general turns). **Implementation:** `experiments/runtime/real_soak.py`; four client processes with isolated SQLite databases, shared local Ollama server; pinned digest `0455603ff430`.
- **Dataset and separation:** 60 synthetic free-form general prompts and 20 exact arithmetic prompts. No gold labels, no held-out capability set and no train/test capability claim. This is a runtime and persistence test, not an accuracy benchmark.
- **Configuration:** Windows 11, Python 3.13.14, i7-1165G7 class, 8 logical CPUs, 16 GB RAM; 4 clients; phase 1 = 28 turns, phase 2 = 52 turns; one forced reload between phases; one fresh-process restart check.
- **Latency:** cold load 13.32 s wall / 7.05 s Ollama load; forced reload 22.41 s wall / 9.11 s Ollama load. Phase 1 general p50 19.88 s / p95 36.89 s, arithmetic p50 5.56 ms. Phase 2 general p50 27.23 s / p95 33.55 s, arithmetic p50 3.67 ms. All 80 turns: general p50 25.80 s / p95 35.23 s / p99 38.05 s; arithmetic p50 4.43 ms / p95 6.67 ms.
- **Resources and failures:** 0 failures, 0 empty answers, 60/60 language steps; 2,047 generated and 28,081 prompt tokens. Client RSS max 97.0 MB; inference process RSS ~5.27 GB; model footprint 4,635.9 MB; system CPU max 65%; RAM max 83.9%; ~455 s total. Temperature was unavailable from the OS; CPU frequency stayed at 1690 MHz, so throttling is not established.
- **Restart/persistence:** write PID 1552, verify PID 12164. A verified arithmetic record and a user-provided memory record were both found by the fresh process; controller retrieval returned "2 hits"; DB 120/204 KB. This proves SQLite/ASHURA memory persistence across a process restart, not a capability change.
- **Supports:** four concurrent clients coexist and complete 80 turns without client failures; forced model reload works; a fresh ASHURA process reads prior records; exact arithmetic stays milliseconds-scale while the model is loaded.
- **Rejects / negative result:** concurrency did not produce parallel throughput. General p50 rose from 5.52 s single-client to 25.80 s with four clients (~4.7x), and server CPU utilisation was ~0.31. The local model appears to queue requests; recorded as F-047, not counted as a success.
- **Does not support:** production endurance, thermal throttling measurements, shared-database concurrency (clients used isolated DBs), answer quality, language-model capability learning or durable worker jobs (F-045).
- **Conclusion:** **supported** for the bounded F-046 scope (client lifecycle, database persistence, model unload/reload, application restart); **rejected** for parallel inference throughput (F-047); **inconclusive** for thermal behaviour and production endurance.
- **Decision:** close F-046 as bounded; keep F-045 and F-047 open. Full data: `experiments/runtime/real_soak.json`; report: `research/EXP-016_real_soak.md`; evidence standard: `research/evidence_standard.md`.

---
## EXP-017 - Consolidation persistence and retention across a process restart (A02/A03, 2026-11-05)
- **Hypothesis:** a promoted NumPy candidate can be loaded by a fresh process, still solve the corrected held-out wordings, retain the old capability and roll back to its parent.
- **Baseline:** EXP-014 measured 50/50 replay promotions and 150/150 held-out predictions in one process. **Implementation:** `experiments/learning/persistence_bench.py`; `CheckpointStore` stable pointer and immutable artifact; one `--verify` child process per promoted candidate.
- **Dataset and separation:** `experiments/learning/corrections_v1.json`, 10 author-written arithmetic cases x 2 seeds; 3 held-out wordings per case and 20 old-capability held-out items per case. The held-out wordings share expression tokens with the key; this is not an independent capability set.
- **Configuration:** Windows 11, Python 3.13.14, CPU only; NumPy `AdaptiveMemory` dim 128; stable initialization; replay; `NGRPolicy("corrected", min_target_gain=0.5)`.
- **Accuracy:** 20/20 promotions; 20/20 fresh-process checks; 20/20 stable artifact name and SHA-256 matches; 60/60 corrected held-out predictions; 400/400 old-capability predictions; 20/20 rollbacks restored the parent. After rollback the parent scored old 20/20 and corrected 0/3 per run.
- **Resources:** stable artifact max 131.1 KB; write p50 48.219 ms; fresh-process verify p50 33.241 ms; ASHURA RSS max 41.2 MB; total wall 6.25 s.
- **Supports:** a promoted NumPy candidate persists across a process restart, retains the old capability on this set and can be rolled back by pointer change.
- **Does not support:** `tony:7b` weight learning, independent generalisation, power-loss durability, corrupt-manifest recovery, shared-database concurrency or production backup/restore. The candidate is the NumPy adaptive memory, not the language model.
- **Conclusion:** **supported** for NumPy consolidation persistence and retention; **not supported** for language-model capability change.
- **Decision:** record A02/A03 as measured for the NumPy candidate; keep F-043 open for any `tony:7b` adapter/fine-tune. Full data: `experiments/learning/persistence.json`; report: `research/EXP-017_persistence.md`; completion audit: `research/completion_audit.md`.

---
## EXP-018 - Frozen subject-tutor comparison: `tony:7b-gpa3` vs `tony:7b` (F-043, 2026-11-05)
- **Hypothesis:** `tony:7b-gpa3` is the general tutor and `tony:7b` the privacy tutor; gpa3 should be non-inferior on a frozen 42-item subject suite and should not lose more than one item in any subject.
- **Baseline:** `tony:7b`, digest `0455603ff430`, prior reference; EXP-000d 0.94 strict / 2.35 s p50 on the 16-item `baseline_v2`, which is not a subject-tutor suite. **Implementation:** `evaluation/subject_bench.py`; suite `evaluation/benchmarks/subject_tutor_v1.jsonl`, SHA-256 `efb3c2cb...`.
- **Dataset and separation:** 42 author-written items, six each in physics, maths, biology, programming, coding, DevOps and debugging; exact-answer accept lists plus three-term explanation rubrics. Frozen before either model ran; no training split. Not independently authored.
- **Configuration:** Windows 11, Python 3.13.14, Ollama 0.40.14, local only; Qwen2 7.6B Q4_K_M; temperature 0, seed 0, top_p 0.9, `num_predict` 160, `num_ctx` 4096; one run per model.
- **Accuracy:** raw gpa3 39/42 (0.929) vs tony:7b 37/42 (0.881). After fixing decimal padding and 6-word echo stripping, and adjudicating five valid paraphrases symmetrically, both are **41/42 (0.976)**. Both miss only `cod-03`: Python `2 ** 3 ** 2` answered 256 instead of 512. Per-subject adjudicated: both 6/6 except coding 5/6.
- **Rubric quality:** gpa3 0.000, tony:7b 0.048; the lexical rubric metric failed to discriminate because both models used formulas and synonyms. It is reported as a diagnostic, not used for the decision.
- **Latency/resources:** gpa3 p50 1860 ms / p95 4137 ms / 9.05 tok/s; tony:7b p50 3040 ms / p95 10173 ms / 6.45 tok/s. Both: load ~8.2 s, 4755 MB Ollama-reported footprint, 4755 MB reported VRAM (not credible as 2 GB dedicated MX350 residency; treat as shared/unknown). Total run 305.62 s.
- **Supports:** gpa3 is non-inferior on this suite, faster and more concise; tony:7b is more explanatory. Supports a role split: gpa3 general default, tony:7b privacy profile.
- **Does not support:** base-model superiority (user-reported prior result, not re-measured), independent capability, privacy preservation, GPU residency, or language-model learning. ASHURA trains neither checkpoint.
- **Conclusion:** **supported** for non-inferiority and speed on this frozen suite; **not supported** for a general capability or privacy claim.
- **Decision:** adopt gpa3 as general default, keep tony:7b as privacy profile (D-056). Full data: `experiments/foundation/subject_tutor.json`; report: `research/EXP-018_subject_tutor.md`.

---
## EXP-018b - `tony:7b-agentic3` on the same frozen subject suite (F-043/F-045 follow-up, 2026-11-06)
- **Hypothesis:** the merged agentic fine-tune may replace gpa3 as the general tutor if it is non-inferior on subject accuracy without a material latency or format regression.
- **Baseline:** the EXP-018 gpa3 and tony:7b rows on the same suite, SHA-256 `efb3c2cb...`; agentic3 digest `0efe3817d5c1`.
- **Configuration:** same frozen 42-item suite, greedy decoding, temperature 0, seed 0, top_p 0.9, `num_ctx` 4096, `num_predict` 160; one run, 304.19 s.
- **Accuracy:** raw 39/42 (0.929), tied with gpa3; after the same adjudication standard, 41/42 (0.976), tied with both. Only `cod-03` (`2 ** 3 ** 2`) was wrong. `dev-05` and `dbg-01` were valid paraphrases.
- **Format and latency:** format 0.881 (several answers put `Final answer:` mid-line, not on its own line); p50 2115 ms, p95 15052 ms, 8.36 tok/s. One 13-token answer took 154.7 s; a direct repeat took 12.3 s cold and 1.35 s warm, so the outlier was transient and the one-run p95 is unstable.
- **Supports:** agentic3 is accuracy-non-inferior on this subject suite.
- **Does not support:** replacing gpa3 as the general tutor, or any tool-use/agentic capability claim; the suite has no tool-use items.
- **Conclusion:** **tied on accuracy, worse on format and p50**; no justification to change the general default.
- **Decision:** keep gpa3 general tutor and tony:7b privacy; retain agentic3 as a candidate for a separate agentic/tool-use benchmark (D-057). Full data: `experiments/foundation/subject_tutor_agentic.json`; report: `research/EXP-018_subject_tutor.md`.

---
## EXP-019 - Concurrent inference configuration and throughput (F-047, 2026-11-06)
- **Hypothesis:** the default local Ollama server serializes concurrent requests; raising `OLLAMA_NUM_PARALLEL` may buy throughput but may cost latency and memory on the 16 GB / 2 GB-GPU laptop.
- **Baseline:** EXP-016's four-client queueing result; no explicit server parallel-slot measurement existed.
- **Configuration:** `tony:7b-gpa3` only, digest `2a86766287cf`; dedicated Ollama server on port 11435; `OLLAMA_NUM_PARALLEL` 1/2/4; `OLLAMA_MAX_QUEUE=8`; clients 1/2/4; 3 measured rounds + 1 warmup; temperature 0, seed 0, top_p 0.9, `num_predict` 32, `num_ctx` 2048; every request generated exactly 32 tokens.
- **Throughput/latency:** one slot 4.93/5.43/5.95 tok/s and p50 6.57/8.83/13.53 s at 1/2/4 clients; two slots 6.37/9.21/7.55 tok/s and p50 5.01/6.86/11.19 s; four slots 3.32/4.89/8.26 tok/s and p50 9.82/13.27/14.82 s. Two slots gave a repeatable ~1.45x at two clients; four slots cut single-client throughput to 3.32 tok/s.
- **Resources:** server-tree RSS 5.23/5.67/6.09 GB and system RAM max 80.2/83.6/87.7% for 1/2/4 slots; 0 failures in all 63 measured requests; no request paid a reload (max load 59 ms).
- **Supports:** explicit bounded concurrency works; two server slots are the maximum useful setting for this laptop; four slots are rejected for interactive use.
- **Does not support:** linear four-way scaling, production multi-tenant serving, or GPU-parallel claims. The client gate is per process and the server queue is not a cross-process scheduler.
- **Conclusion:** **F-047 fixed for a bounded scope**; keep the safe default at one slot, document two slots as the concurrent maximum, and reject four.
- **Decision:** adopt the per-process gate (`max_inflight=1`, `max_queue=8`, `queue_timeout_s=60`) and the one-slot default; document two slots as opt-in only (D-059). Full data: `experiments/runtime/concurrency_sweep.json`; report: `research/EXP-019_concurrency.md`.
