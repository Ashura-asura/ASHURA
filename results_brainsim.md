# BrainSim Results — B1 to B6

**Project:** BrainSim, the independent tiny-neural research subproject of ASHURA  
**Report date:** 2026-11-05  
**Measured code and result JSONs:** commit `d3c7695`  
**Scope:** B1–B6 of the v2 blueprint (`spec/New_approach_2.txt`, Part II)  
**Status:** all six milestones implemented, measured, tested and documented.

This report is deliberately conservative. It separates what was measured from what the measurement
does and does not support. Several headline numbers look strong because the tasks are small,
author-designed and sometimes fully observable. Those numbers are not evidence of general
intelligence, language ability, or a recurrent advantage.

---

## 1. Executive summary

| Milestone | Question | Result | Honest verdict |
|---|---|---|---|
| B1 | Can a small recurrent model learn synthetic rules and use fast memory? | Train-rule 0.957; frozen unseen 0.085; token memory 0.771 | Supported on this task |
| B2 | Does recurrence help delayed recall? | GRU and fixed MLP both 1.000 at every delay | Capability check only; no recurrent advantage |
| B3 | Does task-scoped memory prevent overwrite? | Shared 0.104 vs gated 1.000 after a switch | Supported only with externally supplied task IDs |
| B4 | Can replay reduce forgetting during fine-tuning? | Old drop 49.3 points → 1.18 points | Supported in the tested setting; extra data cost |
| B5 | Can a model choose actions under a budget? | 5.574 vs oracle 5.5745 utility | Supervised imitation of a DP oracle on a toy task |
| B6 | Which mechanisms help on held-out rules? | Gated 1.000; fast 0.771; fixed 0.327; GRU 0.083 | Gated 1.000 is consistent with full-coverage lookup, not intelligence |

**Strongest supported claims**

1. A 206k-parameter GRU can learn the eight training permutation rules to 0.957 accuracy.
2. An isolated, resettable fast associative memory raises unseen-rule next-token accuracy from
   0.085 to 0.771 and survives save/load exactly.
3. Task-scoped memory prevents the observed cross-task overwrite when the task ID is supplied.
4. Replay-augmented fine-tuning reduces old-rule forgetting from 49.3 to 1.18 points while keeping
   new-rule accuracy within one point of new-only.
5. A small supervised policy can imitate a finite-horizon DP oracle on a synthetic budgeted-choice
   task almost exactly.

**Claims that are not supported**

- Recurrence being necessary for delayed recall (B2 falsified this).
- Learned task identification or learned gating (B3/B6 supply the task ID externally).
- General rule induction from partial observations (B6's gated 1.000 is consistent with
  full-coverage lookup).
- Reinforcement learning, latent need inference or general resource management (B5 is supervised
  imitation on a fully observed task).
- Language ability, general reasoning, or ASHURA-level cognition.
- Any benefit to ASHURA's response path. BrainSim is not integrated.

---

## 2. Method and reporting rules

- **No external model or API.** Every experiment runs locally with PyTorch or NumPy. BrainSim does
  not call Qwen, Ollama, Tesseract or any cloud service.
- **CPU-first.** All reported runs used CPU. The target laptop is an Intel i7-1165G7, 16 GB RAM,
  MX350 2 GB. GPU support exists in PyTorch but was not used.
- **Seeds.** B1–B6 use three seeds (0, 1, 2) unless stated otherwise. Accuracy is deterministic for
  a given seed; wall-clock time is not.
- **Baselines.** Each experiment has a non-adaptive, fixed, shared or simple-policy control. B2 and
  B6 include parameter-matched non-recurrent models. B5 includes four non-learned policies.
- **Retention tolerance.** B1 and B4 use a pre-declared 2% tolerance for old-task degradation.
- **Checkpoints.** Saved with `torch.save`, reloaded and re-evaluated for B4. Checkpoint files are
  git-ignored; the result JSONs are tracked.
- **Statistics.** Results are descriptive means and population standard deviations over three
  seeds. No confidence intervals, significance tests or multiple-comparison correction were used.
  Do not read a small difference as statistically established.
- **Reporting.** Training time is machine- and load-dependent; treat it as an order-of-magnitude
  cost, not a benchmark. Accuracy comparisons are the primary evidence.

### Environment

| Item | Value |
|---|---|
| OS | Windows 11 (10.0.26300) |
| Python | 3.13.14 |
| PyTorch | 2.6.0+cu124, CPU execution |
| CPU threads | 4 |
| NumPy / psutil | used for data generation and memory reporting |
| External services | none |

### Code and result locations

| Milestone | Code | Result JSON |
|---|---|---|
| B1 | `BrainSim/experiments/b1_sequence.py` | `BrainSim/experiments/results/b1_sequence.json` |
| B2 | `BrainSim/experiments/b2_delayed_copy.py` | `BrainSim/experiments/results/b2_delayed_copy.json` |
| B3 | `BrainSim/experiments/b3_gated_memory.py` | `BrainSim/experiments/results/b3_gated_memory.json` |
| B4 | `BrainSim/experiments/b4_consolidation.py` | `BrainSim/experiments/results/b4_consolidation.json` |
| B5 | `BrainSim/experiments/b5_control.py` | `BrainSim/experiments/results/b5_control.json` |
| B6 | `BrainSim/experiments/b6_validation.py` | `BrainSim/experiments/results/b6_validation.json` |

All commands assume the working directory is `BrainSim/`:

```bash
cd BrainSim
python -m pytest -q
python -m experiments.b1_sequence
python -m experiments.b2_delayed_copy
python -m experiments.b3_gated_memory
python -m experiments.b4_consolidation
python -m experiments.b5_control
python -m experiments.b6_validation
```

`--quick` produces smoke runs and writes `*_quick.json`; those files are not results and are
git-ignored.

---

## 3. B1 — permutation sequences and fast memory

### Question

Can a small recurrent core learn hidden permutation rules from sequence prediction, and can an
isolated fast memory improve prediction on a later sequence from an unseen rule?

### Task

- 16 symbols.
- A hidden rule is a single-cycle permutation: `x_{t+1} = rule[x_t]`.
- 8 training rules, 8 disjoint held-out rules.
- Offline training uses 32 walks per rule, 24 tokens each.
- Each held-out episode has a 12-transition study walk and a later 16-transition test walk from the
  same rule.
- The GRU weights are frozen during adaptation. Memory is reset per episode in the measured mode.
- Three seeds, 30 epochs, hidden sizes 128 and 384.

### Arms

| Arm | Description |
|---|---|
| frozen | No adaptation; test starts from a zero recurrent state |
| recurrent carry | Study hidden state carried into the test; no memory |
| token memory | Delta-Hebbian matrix keyed by the current token |
| pair memory | Delta-Hebbian matrix keyed by `(previous token, current token)` |

Memory update: `M[k] = decay * M[k] + eta * (onehot(v) - M[k])`, with `decay=1`, `eta=1`,
`blend=0.9`, `logit_scale=20`. These are engineering choices, not calibrated values.

### Results

Means over seeds 0–2; standard deviations in parentheses.

| Hidden | Parameters | Train-rule acc | Frozen unseen | Recurrent carry | Token memory | Pair memory |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 206,493 | 0.957 (0.002) | 0.085 (0.013) | 0.081 (0.011) | **0.771 (0.003)** | **0.681 (0.010)** |
| 384 | 1,799,069 | 0.957 (0.002) | 0.096 (0.019) | 0.094 (0.017) | **0.777 (0.007)** | **0.688 (0.008)** |

Chance on unseen rules is `1/16 = 0.0625`. Both frozen and recurrent-carry are near chance.

### Retention and persistence

| Arm | Adapted | After save/load | Old-rule active | Old after reset | Drop while active |
|---|---:|---:|---:|---:|---:|
| token, 128 | 0.771 | 0.771 | 0.309 | 0.957 | 0.648 |
| pair, 128 | 0.681 | 0.681 | 0.904 | 0.957 | 0.053 |
| token, 384 | 0.777 | 0.777 | 0.309 | 0.957 | 0.648 |
| pair, 384 | 0.688 | 0.688 | 0.904 | 0.957 | 0.053 |

- While new-rule memory stayed active, both key modes failed the 2% tolerance.
- Pair keys reduced interference from 64.8 to 5.3 points but did not eliminate it.
- An explicit reset restored old-rule accuracy to the pre-adaptation value. Model parameters were
  never modified during adaptation.
- Save/load reproduced the adapted accuracy exactly in every run.

### Cost

| Metric | Hidden 128 | Hidden 384 |
|---|---:|---:|
| Training time, median (range) | 20.6 s (15.2–23.5) | 49.6 s (43.5–95.4) |
| RSS after run | ~476 MB | ~525 MB |
| In-process inference, p50 | 0.49 ms | 0.41 ms |
| Memory update, p50 | ~3 ms | ~3 ms |
| Fast-memory state | 1.1 KB token / 18 KB pair | same |

### Verdict

Supported:

- The GRU learns the training rules and predicts unseen starts from them.
- Fast memory improves later related prediction from 0.085 to 0.771 (token) or 0.681 (pair), with
  exact persistence across save/load.
- Pair keys trade adapted accuracy for lower interference.

Not supported:

- Rule induction. The memory stores observed transitions; token coverage is at most 12/16 of the
  test positions, and the measured 0.771 includes a small model fallback.
- Safe unrestricted cross-task memory. Both key modes exceed the 2% retention tolerance while the
  new-rule memory remains active.
- A benefit from scaling. Hidden 384 adds 8.7× parameters with no accuracy gain.

---

## 4. B2 — delayed recall: recurrent vs fixed baseline

### Question

Can the recurrent core use earlier cue information to solve a later recall task, and does it
generalize to longer delays better than a parameter-matched non-recurrent model?

### Task

- 8 symbols; 3 cue symbols.
- Sequence: cue → blank delay → GO token → reproduce the cue.
- Maximum delay 20; total length 27.
- Training delays: 2, 4, 6, 8.
- Evaluation delays: 1, 2, 4, 6, 8, 12, 16, 20; delays 1, 12, 16 and 20 are held out.
- 4,096 sequences per seed, 30 epochs, batch 64, three seeds.
- GRU: hidden 128, 204,183 parameters.
- Fixed MLP: flattens the cue/blank/GO prefix and predicts all three cues at once, 217,560
  parameters (6.6% more than the GRU).

The fixed MLP input stops at the GO token, so the answer block does not leak.

### Results

Means over three seeds. Every standard deviation was 0.000.

| Delay | Trained? | GRU token | Fixed token | GRU full recall | Fixed full recall |
|---:|:---:|---:|---:|---:|---:|
| 1 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 2 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 4 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 6 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 8 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 12 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 16 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 20 | no | 1.000 | 1.000 | 1.000 | 1.000 |

| Arm | Parameters | Training time per seed | RSS |
|---|---:|---:|---:|
| GRU | 204,183 | 112.5–144.2 s (mean 130.0) | 519–526 MB |
| Fixed MLP | 217,560 | 9.0–18.1 s (mean 14.2) | same process |

The fixed MLP trained 6–16× faster.

### Verdict

Supported:

- The GRU uses cue information from up to 20 steps earlier and reproduces it exactly, including
  delays four times longer than any training delay.

Not supported:

- **A recurrent advantage.** The fixed MLP also scored 1.000 at every delay and trained much faster.
- An internal memory strategy, delay counting, or generalization to variable cue counts and
  relational queries.
- Any claim that recurrence is unnecessary in general. The correct conclusion is narrower: this
  fixed-length copy task cannot distinguish the architectures.

### Failure analysis

The task saturates. The delay carries no task-relevant information; the model only needs to copy a
fixed cue block, and the MLP can read that block directly from its flattened input. A harder test
would use variable-length cues, distractors that must be filtered, or a query whose answer depends
on the delay. That is optional B2b, not a completed milestone.

---

## 5. B3 — task-scoped memory vs shared memory

### Question

Does isolating memory by task ID prevent a new rule from overwriting an old rule?

### Task

- Two disjoint single-cycle permutation rules over 16 symbols.
- Every transition of each rule is written with `verified=True`.
- Shared arm: one token-keyed `FastAssociativeMemory`.
- Gated arm: `TaskScopedMemory` with task IDs `old` and `new`, `max_tasks=4`, token keys.
- Three seeds. Query every key of each rule.

### Results

Means over three seeds:

| Arm | Old before switch | Old after switch | New |
|---|---:|---:|---:|
| Shared token memory | 1.000 | **0.104** | 1.000 |
| Task-scoped gate | 1.000 | **1.000** | 1.000 |

Shared old-rule accuracy after the switch ranged from 0.0625 to 0.125. The gated arm was exactly
1.000 on every seed.

### Verdict

Supported:

- Isolating memory by task ID prevents cross-task overwrite in this lookup task.
- The gate is bounded (LRU eviction), supports save/load, and can require verification or a
  surprise threshold before admission.

Not supported:

- **Learned task identification.** The task ID is supplied externally.
- **General cross-task safety.** All writes are verified, so the surprise gate is bypassed. The
  experiment does not test whether surprise-gated admission can detect task boundaries.
- Rule induction or language. The task is a synthetic lookup table with full coverage.

### Failure analysis

This is almost tautological about task identity: if the caller already knows which rule is active,
separate tables trivially prevent overwrite. It is a useful baseline for isolation, not a solution
to interference in an open task stream.

---

## 6. B4 — slow consolidation: new-only vs replay

### Question

Does persistent fine-tuning on a disjoint new rule family forget the old rules, and does mixing
replayed old sequences reduce that forgetting without losing the new capability?

### Setup

- 8 old and 8 disjoint new single-cycle permutation rules over 16 symbols.
- Base model: 30 epochs on 256 old-rule walks; hidden 128; batch 32.
- Both arms start from the same base checkpoint.
- Fine-tuning: 15 epochs on 64 new-rule walks, AdamW, lr 3e-3, batch 32.
- Replay arm: 50% of each batch comes from a bounded 512-sequence buffer containing old walks.
- Three seeds.
- Old and new retention measured on fresh walks from the respective rule sets.
- Every fine-tuned checkpoint saved, reloaded and re-evaluated.

### Results

Means over seeds 0–2:

| Arm | Old accuracy | Old drop | New accuracy | Within 2% |
|---|---:|---:|---:|---:|
| Base checkpoint | 0.9566 | — | 0.0821 | — |
| New-only fine-tune | 0.4632 | **0.4934** | 0.9408 | 0/3 |
| Replay fine-tune | 0.9449 | **0.0118** | 0.9314 | 3/3 |

Per-seed old accuracy:

| Seed | Base old | New-only old | Replay old |
|---:|---:|---:|---:|
| 0 | 0.9565 | 0.4806 | 0.9446 |
| 1 | 0.9565 | 0.4416 | 0.9460 |
| 2 | 0.9569 | 0.4674 | 0.9440 |

- Replay cut the old-rule loss from 49.3 to 1.18 percentage points.
- New-rule accuracy fell by 0.94 points relative to new-only, inside the pre-declared 1-point
  comparison band.
- Fine-tuning took 0.66 s (new-only) and 0.92 s (replay) per seed, about 38% longer for replay.
- All six fine-tuned checkpoints round-tripped exactly.

### Verdict

Supported:

- **H-B4:** persistent updates on the new rules alone cause severe forgetting, far beyond the 2%
  tolerance.
- **H-REPLAY:** replay is a simple, measured mitigation that brought every seed inside the
  tolerance while retaining the new-rule gain.

Not supported:

- General continual learning. The domain, rule split, buffer capacity and replay ratio are
  author-designed.
- Equal-cost superiority. The replay arm sees more examples: 960 new samples plus 960 replayed
  sample draws versus 960 new samples for new-only. This is a method comparison, not equal FLOPs.
- Retention on a different domain. Old-rule retention is measured on new walks from the same old
  rules.
- A guarantee for transitions absent from the buffer.

### Failure analysis

New-only fine-tuning overwrites the recurrent weights that encoded the old cycle. Replay keeps
old-rule gradients in the same batches, but it protects only what the buffer contains. A larger or
shifting domain would require coverage analysis and probably a larger or prioritized buffer. The
buffer stores raw token sequences only, not gradients or logits.

---

## 7. B5 — need and resource control

### Question

Can a recurrent core choose actions from observed needs and budgets, and can it match a
finite-horizon planner rather than a short-sighted greedy rule?

### Task

- 4 need types: `predict`, `retrieve`, `verify`, `adapt`.
- 6 actions: `predict`, `retrieve`, `verify`, `adapt`, `store`, `wait`.
- Action costs: `(1, 2, 3, 4, 2, 0)`.
- Episode length 8.
- Maximum budget 12; initial budgets `(2, 5, 9, 12)`; recovery 1 per step.

Utility table (rows = needs, columns = actions):

| need \ action | predict | retrieve | verify | adapt | store | wait |
|---|---:|---:|---:|---:|---:|---:|
| predict | 0.90 | 0.30 | 0.20 | 0.10 | 0.25 | 0.05 |
| retrieve | 0.20 | 0.90 | 0.35 | 0.10 | 0.25 | 0.05 |
| verify | 0.15 | 0.30 | 0.90 | 0.20 | 0.25 | 0.05 |
| adapt | 0.10 | 0.20 | 0.30 | 0.90 | 0.45 | 0.05 |

The target is a **finite-horizon dynamic-programming oracle**. It values future budget, so waiting
can be optimal. Example: with need=retrieve and budget=1 at step 0, the greedy action is `predict`
(0.20 utility), but the DP oracle waits (0.05 now) to recover budget and use `retrieve` (0.90)
later. An earlier greedy target was replaced for this reason.

### Setup

- Model: 128 hidden, 2 layers, 201,615 parameters.
- Training: 20 epochs, 4,096 episodes, batch 64, three seeds.
- Supervised action and need targets, plus a detached confidence target.
- Evaluation: 512 fresh episodes, open-loop and closed-loop.
- Three seeds. Training took 20.3–24.8 s per seed; RSS 508–513 MB.

### Results

Means over seeds 0–2, closed loop:

| Policy | Total utility / episode | Action accuracy | Cost / episode |
|---|---:|---:|---:|
| Learned | **5.5740** | 0.9998 | 13.41 |
| DP oracle | 5.5745 | 1.0000 | 13.42 |
| Need-match, cost-blind | 5.4059 | 0.8705 | 12.81 |
| Always highest-mean action | 2.1598 | 0.3452 | 13.63 |
| Random feasible | 2.2706 | 0.2472 | 12.35 |
| Always wait | 0.4000 | 0.0592 | 0.00 |

Per-seed total utility:

| Seed | Learned | Oracle |
|---:|---:|---:|
| 0 | 5.62988 | 5.62988 |
| 1 | 5.49346 | 5.49521 |
| 2 | 5.59854 | 5.59854 |

The learned policy matched the per-seed oracle exactly on two seeds and was 0.00175 lower on one.
The pooled means differ by 0.00059 utility.

Other measurements:

- Open-loop action accuracy: 0.9998.
- Open-loop raw infeasible rate: 0.0; closed-loop infeasible rate: 0.0. The raw unmasked policy also
  chose no infeasible action, so feasibility masking was not exercised much.
- Confidence ECE: 0.0002.
- Confidence Brier score: 0.00016.
- Expected-cost MAE: 0.00018.

### Verdict

Supported:

- The core maps observed needs and budgets to near-oracle actions on this small task.
- A finite-horizon target produces sensible waiting behaviour that a greedy target would miss.
- Confidence and expected cost track action correctness and realised cost.

Not supported:

- **Reinforcement learning.** The policy is supervised imitation of a known oracle. There is no
  exploration, reward learning, or credit assignment through time.
- **Latent need inference.** Needs and budgets are inputs.
- **General resource management.** The task is a small, fully observed, deterministic toy with a
  fixed utility table.
- **A dedicated cost-prediction mechanism.** Expected cost is derived from the action distribution
  and the known cost table.
- **ASHURA router integration.** No response-path task or baseline was tested.

### Failure analysis

The near-perfect score mostly confirms that the training signal, masking and target are correct. It
does not show that the model would discover needs, estimate costs, or behave sensibly under noisy
or delayed feedback. The task is small enough for a DP table; a learned model is not necessary to
solve it.

---

## 8. B6 — independent validation on held-out rules

### Question

On disjoint held-out permutation rules, which mechanisms actually help: a fixed in-context model, a
frozen recurrent model, fast memory, or per-rule gated memory?

### Setup

- Train on 8 rules; evaluate on 8 disjoint rules.
- 8 study/test episodes per held-out rule.
- Study walk: 12 transitions (13 tokens).
- Test walk: 16 transitions (17 tokens).
- Three seeds.

Four arms:

1. **Fixed in-context MLP** — 207,496 parameters. Flattens the 13-token study walk and the
   16-token test prefix (29 tokens × 16 symbols = 464 inputs) and predicts the 16 next test
   tokens. No recurrence, no memory.
2. **Frozen GRU** — the B1 core, 206,493 parameters. Trained only on old rules; no adaptation.
3. **Fast memory** — GRU + token-keyed fast memory, reset before every held-out episode (B1 mode).
4. **Gated memory** — GRU + `TaskScopedMemory`, one task per rule, verified writes, task ID
   supplied externally (B3 mode).

The fixed arm trained for 30 epochs on old-rule study/test pairs. The GRU trained for 30 epochs on
old walks. Evaluation is zero-shot on held-out rules. The “revisit” phase evaluates the same
held-out test walks a second time without a new study walk; it measures retention, not transfer to
new sequences.

### Results

Means over seeds 0–2:

| Arm | Test token acc | Test full recall | Revisit token acc | Memory |
|---|---:|---:|---:|---:|
| Fixed in-context MLP | 0.3275 | 0.0000 | — | 0 B |
| Frozen GRU | 0.0833 | 0.0000 | 0.0833 | 0 B |
| Fast memory, reset per episode | **0.7705** | 0.0000 | 0.0833 | 1,152 B |
| Per-rule gated memory | **1.0000** | **1.0000** | **1.0000** | 9,216 B |

Per-seed test token accuracy:

| Seed | Fixed | Frozen GRU | Fast memory | Gated memory |
|---:|---:|---:|---:|---:|
| 0 | 0.2979 | 0.0703 | 0.7715 | 1.0000 |
| 1 | 0.3730 | 0.1074 | 0.7754 | 1.0000 |
| 2 | 0.3115 | 0.0723 | 0.7646 | 1.0000 |

Other measurements:

- Gated revisit retention gap: exactly 0.0 on every seed.
- Fixed training time: 0.49–0.66 s (mean 0.56 s).
- GRU training time: 5.51–6.51 s (mean 5.85 s).
- Fast memory: 16 rows (token-keyed), 1,152 bytes.
- Gated memory: 8 tasks, 9,216 bytes.
- Fast-memory revisit falls back to the frozen GRU because the B1 mode resets at the episode
  boundary.
- The fixed MLP has zero full recall: it matches some local patterns but never reproduces a whole
  held-out sequence.

### Why the gated arm reaches 1.000

This is the most important honesty point in the report.

Eight study walks per rule are enough to cover every transition of a 16-cycle. The gated arm
receives the correct rule ID, stores verified transitions, and is queried with the same task ID.
Coverage was not instrumented directly, but the 1.000 token and full-recall result is consistent
with **full-coverage verified lookup**, not rule induction, not learned task segmentation, and not
generalization to unobserved transitions. The frozen GRU's 0.083 accuracy makes it very unlikely
that the model itself supplied the missing transitions.

The fast-memory arm sees only one study walk per episode, covering roughly 12 of 16 transitions.
Its 0.771 is close to the 0.75 coverage ceiling plus a small model fallback.

### Verdict

Supported:

- Fast memory is the mechanism that improves held-out-rule prediction for the frozen core.
- Per-rule memory retains verified transitions across a revisit without new study data.
- The fixed MLP is a stronger in-context baseline than the frozen GRU on this task (0.327 vs
  0.083), so recurrence is not supported as the source of the held-out gain.

Not supported:

- **Rule inference or general intelligence.** The gated 1.000 is consistent with lookup under full
  coverage.
- **Learned task segmentation or learned gating.** The task ID is external.
- **Generalization to unobserved transitions.** The fixed baseline reaches 0.327 token accuracy but
  zero full recall; the frozen GRU is near chance.
- **A recurrent advantage.** The fixed model beats the frozen GRU.
- **Cheap per-rule memory.** It uses 8× the memory of the single-episode fast memory in this
  configuration.

### Failure analysis

The held-out-rule setup measures adaptation, not induction: a single-cycle permutation has a unique
next token per key, so a complete lookup table is sufficient. The fixed MLP can match parts of the
study/test window but cannot represent the unseen permutation. The gated arm's perfect score is an
upper bound created by full coverage and external task identity.

---

## 9. Cross-milestone findings

### What the evidence supports

1. **Small recurrent sequence learning works on synthetic rules.** The GRU reaches 0.957 on
   training rules.
2. **Fast associative memory is useful when it is scoped.** It raises unseen-rule accuracy from
   0.085 to 0.771 in B1 and 0.771 in B6, and it persists exactly.
3. **Isolation matters.** Shared memory overwrites old rules; per-task memory does not, when the
   task boundary is supplied.
4. **Replay reduces catastrophic forgetting in a controlled setting.** The old-rule drop falls from
   49.3 to 1.18 points.
5. **A finite-horizon target matters for control.** A learned policy can imitate a DP oracle
   closely on a small budgeted task; a greedy target would have taught different behaviour.
6. **Fixed baselines are essential.** B2's fixed MLP matches the GRU; B6's fixed MLP beats the
   frozen GRU. Without these controls, both results could have been misread as recurrent
   advantages.

### What the evidence does not support

- General rule induction from partial observations.
- Recurrence being necessary for delayed recall or sequence learning.
- Learned task identification, boundary detection or gating.
- Safe cross-task memory without external IDs.
- Reinforcement learning, exploration, reward optimization or credit assignment.
- Latent need inference, cost learning or general resource management.
- Language understanding, reasoning, planning or ASHURA-level cognition.
- Any improvement to ASHURA's response path.
- Scaling benefits: the 384-hidden model was 8.7× larger with no accuracy gain.

### Headline-number warnings

| Number | What it actually means |
|---|---|
| B5 0.9998 action accuracy | Imitation of a known DP oracle on a fully observed toy task |
| B5 5.574 vs 5.5745 utility | Near-exact imitation; the task is small enough for a DP table |
| B6 gated 1.000 | Full-coverage lookup with external task IDs and verified writes |
| B1 token memory 0.771 | 12/16 transition coverage plus a small model fallback |
| B4 1.18-point drop | Replay with extra old samples in the same rule family |
| B2 1.000 at delay 20 | Fixed-length copy that a non-recurrent MLP also solves |

---

## 10. Threats to validity

1. **Synthetic, author-designed tasks.** Every environment was written for these experiments. The
   tasks may contain shortcuts that do not exist in real problems.
2. **Three seeds.** Accuracy is deterministic per seed, but three seeds are too few for strong
   statistical claims. No confidence intervals or significance tests were computed.
3. **No external validation.** There is no independent dataset, no held-out corpus from another
   source, and no cross-machine replication.
4. **Timing is noisy.** Wall-clock comparisons are indicative only. The B1 384-hidden training time
   ranged widely, and CPU load affects every timing table.
5. **Small model and hyperparameter search.** Hidden sizes, learning rates, replay ratios and
   memory settings were chosen by hand. A different configuration might change the magnitudes,
   though probably not the qualitative B2/B6 conclusions.
6. **Task coverage creates ceilings.** B1's fast memory cannot exceed its observed-transition
   coverage. B6's gated memory reaches 1.000 in a setting where eight study walks per rule are
   enough to cover the whole cycle; coverage was not instrumented directly.
7. **External task IDs.** B3 and B6 do not test learned task identification. Their retention
   results depend on the caller knowing the correct task.
8. **Supervised control target.** B5 measures imitation of a known oracle, not learning from
   outcomes. The utility table and budget dynamics are fixed and fully observed.
9. **Replay is not equal-cost.** B4's replay arm sees more samples and takes longer. The comparison
   is about method behaviour, not efficiency.
10. **One hardware target.** All results are from the target laptop's CPU. GPU or other CPU
    behaviour was not characterized.
11. **Checkpoints are not tracked.** The JSON results are tracked, but exact checkpoint artifacts
    are local and git-ignored. Re-running the commands reproduces the measurements for a given
    seed.
12. **No integration test.** BrainSim is not imported by ASHURA. Nothing here measures a
    response-path benefit.

---

## 11. Failure log summary

| ID | Finding |
|---|---|
| F-BS-001 | Token-keyed memory caused severe cross-task interference (old accuracy 0.957 → 0.309) |
| F-BS-002 | Pair keys reduced but did not eliminate interference (5.3-point drop, still above 2%) |
| F-BS-003 | Fast memory cannot predict unobserved transitions; it is a lookup, not rule inference |
| F-BS-004 | A 8.7× larger recurrent core gave no accuracy gain |
| F-BS-005 | Laptop training time is highly variable; use medians and repeated runs |
| F-BS-006 | B2 delayed copy is too easy and does not distinguish architectures |
| F-BS-007 | B3 gating is tautological about task identity; IDs are external and writes verified |
| F-BS-008 | B4 replay is a mitigation, not free retention; extra samples and time |
| F-BS-009 | B5 is supervised imitation on a fully observed toy task, not RL |
| F-BS-010 | B6 gated 1.000 is full-coverage lookup, not intelligence |
| F-BS-011 | B6 fixed baseline is strong but not a rule learner; zero full recall |

---

## 12. Decisions

- **D-BS-001:** BrainSim is an independent subproject; ASHURA does not import it.
- **D-BS-002:** 128 hidden is the default; scale only when a task needs it.
- **D-BS-003:** Fast memory is separate state, never an online change to GRU weights.
- **D-BS-004:** Fast memory is task-scoped; reset at episode/task boundaries.
- **D-BS-005:** Pair keys are the better retention/adaptation tradeoff for now, not a solved design.
- **D-BS-006:** Do not integrate BrainSim into ASHURA yet.
- **D-BS-007:** B2 is a capability baseline, not evidence that recurrence is necessary.
- **D-BS-008:** Task-scoped memory is the safe default, but task identity is external.
- **D-BS-009:** Do not adopt a BrainSim runtime API yet.
- **D-BS-010:** Replay is the B4 candidate; frozen weights plus task-scoped memory remains the safe
  default.
- **D-BS-011:** B5 uses a finite-horizon DP oracle and supervised imitation; not RL.
- **D-BS-012:** B6's four arms are the standing validation protocol; the fixed baseline must stay.
- **D-BS-013:** B1–B6 are complete on synthetic tasks; ASHURA integration is still deferred.

---

## 13. Reproducibility and verification

- **BrainSim tests:** 46 passing.
- **ASHURA tests:** 139 passing, confirming the subproject does not break the parent repository.
- **Measured commit:** `d3c7695` on `origin/main`.
- **Result JSONs:** tracked under `BrainSim/experiments/results/`.
- **Checkpoints:** local under `BrainSim/checkpoints/`, git-ignored.
- **No external API calls:** confirmed by code paths and experiment design.

### Blueprint completion criteria

The v2 blueprint defines BrainSim as complete when it has the following. Each item is met only on
the synthetic tasks in this report.

| Criterion | Evidence | Status |
|---|---|---|
| Documented trainable neural architecture | `brainsim/core/model.py`, B1 | Met |
| Maintains internal recurrent state | B1/B2 | Met |
| Learns from sequential experience | B1 train-rule 0.957 | Met |
| Working prediction mechanism | B1 next-token prediction | Met |
| Temporary adaptive memory | B1 fast memory; B3 task-scoped memory | Met |
| Improves on unseen related examples | B1 0.085 → 0.771; B6 0.771 | Met |
| Consolidates learning persistently | B4 checkpointed fine-tuning | Met |
| Measures retention and interference | B1 2% tolerance; B4 49.3 → 1.18 points | Met |
| Repeatable experiments | 46 tests; result JSONs | Met |
| Runs within target resource budget | CPU-only; peak RSS ~526 MB; no GPU required | Met |

This means BrainSim is complete **as a first validated research platform**. It does not mean
BrainSim is a useful ASHURA component, and it does not satisfy ASHURA's own completion criteria.

Run the full suite:

```bash
cd BrainSim
python -m pytest -q
```

Expected: `46 passed`.

Run each experiment:

```bash
python -m experiments.b1_sequence
python -m experiments.b2_delayed_copy
python -m experiments.b3_gated_memory
python -m experiments.b4_consolidation
python -m experiments.b5_control
python -m experiments.b6_validation
```

Approximate full-run costs on the target laptop:

| Experiment | Time | Notes |
|---|---:|---|
| B1 | several minutes | 6 runs (2 sizes × 3 seeds) |
| B2 | several minutes | 112–144 s per GRU seed, 9–18 s per fixed seed |
| B3 | seconds | memory-only |
| B4 | ~25 s | 3 seeds |
| B5 | ~70 s | 3 seeds |
| B6 | ~21 s | 3 seeds |

Exact times vary with CPU load.

---

## 14. What would change these conclusions

The current results are useful because they are bounded. The following experiments would test
whether the conclusions generalize:

1. **A harder delayed-recall task** with variable cue counts, distractors, or a relational query
   whose answer depends on the delay. If the GRU then beats the fixed MLP, B2's negative result
   would not generalize.
2. **A task with learned task boundaries.** If surprise-gated admission can infer task switches and
   retain old rules without external IDs, B3/B6's dependence on external IDs could be reduced.
3. **A domain where replay coverage is incomplete.** This would test whether B4's 1.18-point drop
   survives distribution shift and buffer eviction.
4. **A control task with latent needs or noisy costs.** This would test whether B5's imitation
   result survives when the need and cost are not directly observed.
5. **A real ASHURA response-path task** where BrainSim must beat a deterministic or retrieval
   baseline. Without this, integration has no measured justification.
6. **More seeds and confidence intervals.** This would separate real effects from run-to-run noise,
   especially for small differences such as B4's 0.94-point new-rule gap.
7. **A memory-coverage analysis** that reports which transitions are observed, not just aggregate
   token accuracy. This would make B1/B6 coverage ceilings explicit per episode.

---

## 15. Bottom line

BrainSim B1–B6 now form a complete, repeatable, CPU-only research platform for small synthetic
tasks. The experiments have baselines, controlled comparisons, measured results, failure analyses
and decisions. The strongest defensible claim is:

> A small recurrent model can learn synthetic permutation rules; a scoped fast associative memory
> can improve later related prediction; replay can reduce catastrophic forgetting in a controlled
> fine-tuning setting; and a supervised policy can imitate a finite-horizon planner on a small
> budgeted task.

The equally important negative claims are:

> This work does not show a recurrent advantage, learned task segmentation, general rule induction,
> reinforcement learning, general resource management, language ability, or a benefit to ASHURA's
> response path. The gated 1.000 in B6 is consistent with full-coverage lookup with an externally
> supplied task ID, not intelligence.

BrainSim is complete against the v2 blueprint's definition of a first validated research platform.
It is not yet a useful ASHURA component; that requires a real task, a strong baseline, and an
integration measurement that does not yet exist.
