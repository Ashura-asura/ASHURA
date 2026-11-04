# BrainSim experiment log

All experiments run locally on the target laptop (Windows 11, Intel i7-1165G7, 16 GB RAM,
MX350 2 GB). No external LLM or cloud API is used. BrainSim is a subproject of ASHURA and is
tested independently.

---

## BS-EXP-001 — B1 tiny recurrent baseline + first fast-memory experiment

**Date:** 2026-11-02 (rerun 2026-11-05 after deterministic seeding)
**Code:** `experiments/b1_sequence.py`
**Results:** `experiments/results/b1_sequence.json`
**Environment:** Python 3.13.14, PyTorch 2.6.0+cu124, CPU (4 threads), Windows 11.

### Hypotheses

- **H-B1:** the recurrent core learns hidden permutation rules from training sequences and predicts
  held-out starts from those rules.
- **H-FM:** an isolated fast associative memory, updated on a study sequence from an *unseen* rule,
  improves next-token prediction on a later sequence with the same rule.
- **H-KEY:** context keys `(previous token, current token)` reduce interference with previously
  learned rules compared with token-only keys.

### Setup

Synthetic single-cycle permutations over 16 symbols. 8 training rules and 8 disjoint held-out rules
(3 seeds). A sequence is a walk `x_{t+1} = rule[x_t]`. Offline training used 32 walks per rule,
24 tokens each, batch 32, AdamW, cross-entropy, 30 epochs. Two model sizes were compared:
hidden 128 (206,493 parameters) and hidden 384 (1,799,069 parameters).

Each held-out episode has a 12-transition study walk and a separate 16-transition test walk from the
same rule. The study covers 12 of 16 transitions, so token-keyed memory can cover at most 75% of
test positions. The model weights are frozen during adaptation. Memory is reset per episode.

Arms:

1. **frozen** — no adaptation; test starts from a zero recurrent state.
2. **recurrent carry** — the study hidden state is carried into the test; no memory.
3. **token memory** — delta-Hebbian matrix keyed by the current token.
4. **pair memory** — delta-Hebbian matrix keyed by `(previous token, current token)`.

Memory update: `M[k] = decay * M[k] + eta * (onehot(v) - M[k])`, with `decay=1`, `eta=1`,
`blend=0.9`, `logit_scale=20`. These values are engineering choices, not calibrated.

### Results

Means over seeds 0–2 (standard deviation in parentheses):

| hidden | params | train-rule acc | frozen unseen | recurrent carry | token adapted | pair adapted |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 206,493 | 0.957 (0.002) | 0.085 (0.013) | 0.081 (0.011) | **0.771 (0.003)** | **0.681 (0.010)** |
| 384 | 1,799,069 | 0.957 (0.002) | 0.096 (0.019) | 0.094 (0.017) | **0.777 (0.007)** | **0.688 (0.008)** |

Chance on unseen rules is 1/16 = 0.0625. The frozen and recurrent-carry baselines are near chance;
neither the study context nor extra recurrence solves the unseen rule.

Persistence and retention (means over all runs):

| arm | adapted | persisted after save/load | old-rule active | old-rule after reset | drop (active) |
|---|---:|---:|---:|---:|---:|
| token (128) | 0.771 | 0.771 | 0.309 | 0.957 | 0.648 |
| pair (128) | 0.681 | 0.681 | 0.904 | 0.957 | 0.053 |
| token (384) | 0.777 | 0.777 | 0.309 | 0.957 | 0.648 |
| pair (384) | 0.688 | 0.688 | 0.904 | 0.957 | 0.053 |

- The 2% retention tolerance was **not met** by either memory while the new-rule memory was left
  active across a task switch. Pair keys reduced the interference from 64.8 to 5.3 percentage
  points, but did not eliminate it.
- With an explicit reset (the task-scoped operating mode), old-rule accuracy returned to the
  pre-adaptation value (0.957). Model parameters were never modified.
- Save/load reproduced the adapted accuracy exactly for every episode, so the improvement is
  persistent state, not a transient in-process artefact.

Cost (128/384 means):

| metric | 128 | 384 |
|---|---:|---:|
| training time, median (range) | 20.6 s (15.2–23.5) | 49.6 s (43.5–95.4) |
| RSS after run | 476 MB | 525 MB (median 539) |
| in-process inference, p50 | 0.49 ms | 0.41 ms |
| memory update, p50 | ~3 ms | ~3 ms |
| fast-memory state | 1.1 KB token / 18 KB pair | same |

Training-time variance is large on the laptop; the median is more informative than the mean.
Inference is in-process only.

### Supports

- **H-B1:** both sizes learn the training rules and predict unseen starts (0.957 vs 0.0625 chance).
- **H-FM:** after a study sequence from an unseen rule, fast memory improves a later related
  sequence from 0.085 to 0.771 (token) or 0.681 (pair), with exact persistence across save/load.
- **H-KEY:** pair keys cut old-rule interference from 64.8 to 5.3 points, at the cost of 9.0 points
  of adapted accuracy and lower coverage.
- **Size:** 128 is sufficient for this task; 384 adds 8.7× parameters with no accuracy gain.

### Does not support

- **No rule induction.** The memory stores transitions it observed; coverage ceiling is 0.75
  (token) and about 0.65 (pair).
- **No safe cross-task application.** Both arms exceed the 2% tolerance while new-rule memory
  remains active. A gate or task identifier is required.
- **No language or broad cognitive claim.** 3 seeds, one task family, author-designed data.
- **No evidence that recurrent state solves unseen rules.** Carrying the study state scored 0.081.
- **No calibrated plasticity.** Decay, eta, blend, scale and study length are author choices.

### Failure analysis

- Token keys conflate the same symbol in different rules; applying new-rule memory to old-rule
  sequences overwrites correct predictions.
- Pair keys reduce collisions but not enough: a pair from the new rule can occur in an old rule,
  and the first test position uses a self-pair `(x, x)`.
- The memory is an exact lookup; it does not infer the permutation from partial observations.
- Larger hidden size did not improve the learned rule policy; the task is limited by data
  structure and memory coverage, not capacity.

---

## BS-EXP-002 — B2 delayed recall: recurrent core vs fixed MLP

**Date:** 2026-11-05
**Code:** `experiments/b2_delayed_copy.py`
**Results:** `experiments/results/b2_delayed_copy.json`
**Environment:** Python 3.13.14, PyTorch 2.6.0+cu124, CPU.

### Hypotheses

- **H-B2:** the recurrent core solves delayed recall on delays seen during training.
- **H-DELAY:** the GRU generalizes to longer delays better than a non-recurrent MLP that receives
  the same cue/blank/GO window.
- **H-COST:** any advantage is reported against parameters, training time and per-delay accuracy.

### Setup

Eight symbols, three cue symbols, a blank delay, a GO token, then the same three cues. Maximum
delay 20; total sequence length 27. Training delays 2, 4, 6, 8. Evaluation delays 1, 2, 4, 6, 8,
12, 16, 20; 1, 12, 16 and 20 are held out. 4,096 sequences per seed, 30 epochs, batch 64, seeds
0–2. The GRU is the B1 core (hidden 128, 204,183 parameters). The fixed MLP flattens the
cue/blank/GO prefix and predicts all three cues at once (217,560 parameters).

Both arms use the same recall objective. The GRU loss is taken only on the three recalled tokens;
the MLP loss is cross-entropy over its three output slots. The MLP input stops at GO, so the answer
block never leaks.

### Results

Means over 3 seeds; standard deviation was 0.000 for every cell.

| delay | trained? | GRU token | fixed token | GRU full recall | fixed full recall |
|---:|:---:|---:|---:|---:|---:|
| 1 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 2 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 4 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 6 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 8 | yes | 1.000 | 1.000 | 1.000 | 1.000 |
| 12 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 16 | no | 1.000 | 1.000 | 1.000 | 1.000 |
| 20 | no | 1.000 | 1.000 | 1.000 | 1.000 |

Cost:

| arm | parameters | training time per seed | RSS |
|---|---:|---:|---:|
| GRU | 204,183 | 112–144 s | ~519–526 MB |
| fixed MLP | 217,560 | 9–18 s | same process |

### Supports

- **H-B2:** the recurrent core uses cue information from up to 20 steps earlier and reproduces it
  exactly, including delays four times longer than any training delay.
- **H-COST:** the comparison is parameter-matched (within 6.6%) and reports training cost.

### Does not support

- **H-DELAY is falsified.** The fixed MLP also scores 1.000 at every delay and trains 6–16× faster.
  Fixed-length delayed copy does not require recurrence: the MLP can read the cue block directly
  from its flattened input.
- The MLP is a strong non-recurrent **upper bound**, not a memoryless baseline. A memoryless model
  is at chance (1/8 per token, 1/512 for all three).
- No claim that the GRU is the better architecture, that it learned an internal memory strategy,
  or that it would generalize to variable cue counts or relational tasks.

### Failure analysis

- The task saturates: both arms reach 100%, so the experiment cannot rank them.
- The delay length carries no task-relevant information. The model only needs to copy the cue
  block; it does not need to count blanks or maintain a decaying trace.
- A harder B2b should use variable-length cues, distractor content that must be filtered, or a
  relational query whose answer depends on the delay. Until then, B2 is a capability check, not
  evidence for recurrence.
- The fixed MLP receives an explicit prefix window and a positional GO token; this is a generous
  baseline by design.

### Decision

Keep B2 as the measured delayed-recall baseline. Do not use it to justify adding recurrence to
ASHURA. Next BrainSim task: B2b variable-length/relational recall, or B4 slow consolidation. B3
(task-scoped gate) was also run and is recorded below.

---

## BS-EXP-003 — B3 task-scoped gate vs shared token memory

**Date:** 2026-11-05
**Code:** `experiments/b3_gated_memory.py`
**Results:** `experiments/results/b3_gated_memory.json`

### Hypothesis

A per-task memory prevents a new rule from overwriting an old rule's associations, whereas one
shared token table loses the old rule.

### Setup

Two disjoint single-cycle permutation rules over 16 symbols. Every transition of each rule is
written (verified) into memory. Shared arm: one `FastAssociativeMemory` keyed by token. Gated arm:
`TaskScopedMemory` with task IDs `old` and `new`, `max_tasks=4`, token keys. Three seeds. Memory
is queried for every key of each rule.

### Results (means over 3 seeds)

| arm | old before switch | old after switch | new |
|---|---:|---:|---:|
| shared token memory | 1.000 | **0.104** | 1.000 |
| task-scoped gate | 1.000 | **1.000** | 1.000 |

Shared old-rule accuracy after the switch ranged 0.0625–0.125; the gated arm was exactly 1.000
for every seed.

### Supports

- Isolating memory by task ID prevents cross-task overwrite in this lookup task.
- The gate is bounded (LRU eviction), supports save/load, and can require verification or a
  surprise threshold before admission.

### Does not support

- **Learned task identification.** The task ID is supplied externally by the caller.
- **General cross-task safety.** The experiment writes verified updates, so the surprise threshold
  is bypassed; it does not test whether surprise-gated admission can infer task boundaries.
- **Rule induction or language.** The task is a synthetic lookup table with full coverage.

### Decision

Use task-scoped memory as the safe default for any future integration. Do not claim that the
gate solves interference without task IDs. A learned boundary detector is a separate experiment.

---

## BS-EXP-004 — B4 slow consolidation: new-only vs replay

**Date:** 2026-11-05
**Code:** `experiments/b4_consolidation.py`
**Results:** `experiments/results/b4_consolidation.json`
**Environment:** Python 3.13.14, PyTorch 2.6.0+cu124, CPU.

### Hypotheses

- **H-B4:** fine-tuning the persistent weights on a disjoint new rule family causes old-rule
  forgetting beyond the 2% retention tolerance.
- **H-REPLAY:** mixing replayed old-rule sequences into the same fine-tuning schedule reduces that
  forgetting while retaining most of the new-rule accuracy.

### Setup

Eight old and eight disjoint new single-cycle permutation rules over 16 symbols. The base model
was trained for 30 epochs on 256 old-rule walks. Both arms then started from the same checkpoint
and fine-tuned for 15 epochs on 64 new-rule walks, with AdamW, lr 3e-3, batch 32, hidden 128.
The replay arm mixed 50% samples from a bounded 512-sequence buffer containing old walks. Three
seeds. Old and new retention were measured on fresh walks from the respective rule sets; every
arm checkpoint was saved, reloaded and re-evaluated.

### Results

Means over seeds 0–2:

| arm | old accuracy | old drop | new accuracy | within 2% |
|---|---:|---:|---:|---:|
| base checkpoint | 0.9566 | — | 0.0821 | — |
| new-only fine-tune | 0.4632 | **0.4934** | 0.9408 | 0/3 |
| replay fine-tune | 0.9449 | **0.0118** | 0.9314 | 3/3 |

Replay cut the old-rule loss from 49.3 to 1.18 percentage points. New-rule accuracy fell by 0.94
points relative to new-only, inside the pre-declared 1-point comparison band. Fine-tuning took
0.66 s (new-only) and 0.92 s (replay) per seed. All six fine-tuned checkpoints round-tripped
exactly. Standard deviations were at most 1.7 points.

### Supports

- **H-B4:** persistent training on the new rules alone causes severe interference.
- **H-REPLAY:** replay is a simple, measured mitigation that keeps every seed inside the tolerance
  and retains the new-rule gain.

### Does not support

- General continual learning. The domain, rule split and replay ratio are author-designed, and
  retention is tested on new walks from the old rules rather than a separate task family.
- Equal-cost superiority. The replay arm sees more examples and takes about 38% longer, so this is
  a method comparison, not an equal-FLOPs result.
- A guarantee outside the tested capacity, ratio and learning rate.

### Failure analysis

New-only fine-tuning overwrites the recurrent weights that encoded the old cycle. Replay keeps
old-rule gradients in the same batches, but it does not protect transitions that are absent from
the buffer; a larger or shifting domain would need coverage analysis. The buffer stores raw token
sequences only, not gradients or logits.

### Decision

Keep replay-augmented fine-tuning as the candidate B4 consolidation mode. The safe default remains
frozen weights plus task-scoped fast memory (D-BS-004); persistent updates require retention
testing before use.

---

## BS-EXP-005 — B5 need and resource control

**Date:** 2026-11-05
**Code:** `experiments/b5_control.py`
**Results:** `experiments/results/b5_control.json`
**Environment:** Python 3.13.14, PyTorch 2.6.0+cu124, CPU (4 threads).

### Hypotheses

- **H-B5:** a recurrent core trained on need/budget contexts selects higher-utility actions than
  always-max, cost-blind need matching, always-wait and random baselines.
- **H-CONF:** the confidence head is calibrated against whether the selected action is optimal.
- **H-BUDGET:** masking unaffordable actions keeps the policy feasible; the raw violation rate is
  reported rather than hidden.

### Setup

Synthetic task with 4 observed need types (`predict`, `retrieve`, `verify`, `adapt`), 6 actions
(`predict`, `retrieve`, `verify`, `adapt`, `store`, `wait`), costs `(1, 2, 3, 4, 2, 0)`, episode
length 8, maximum budget 12, initial budgets `(2, 5, 9, 12)` and recovery 1 per step. The target is
a finite-horizon dynamic-programming oracle: it values future budget, so waiting can be optimal.
This replaced a myopic greedy oracle that ignored future utility.

A 128-hidden, 2-layer GRU (201,615 parameters) was trained for 20 epochs on 4,096 episodes with
supervised action and need targets, plus a detached confidence target. Evaluation used 512 fresh
episodes and closed-loop rollouts. Three seeds. Training took 20.3–24.8 s per seed; RSS was
508–513 MB.

### Results

Means over seeds 0–2, closed loop:

| policy | total utility / episode | action accuracy | cost / episode |
|---|---:|---:|---:|
| learned | **5.5740** | 0.9998 | 13.41 |
| DP oracle | 5.5745 | 1.0000 | 13.42 |
| need-match | 5.4059 | 0.8705 | 12.81 |
| always-max | 2.1598 | 0.3452 | 13.63 |
| random feasible | 2.2706 | 0.2472 | 12.35 |
| always-wait | 0.4000 | 0.0592 | 0.00 |

The learned policy was within 0.0006 utility (about 0.01%) of the oracle, beat all four simple
baselines, and never selected an infeasible action in closed loop (infeasible rate 0.0; the raw
unmasked policy also had zero violations). Open-loop action accuracy was 0.9998. Confidence ECE
was 0.0002, Brier score 0.00016 and expected-cost MAE 0.00018.

### Supports

- The core can map observed needs and budgets to near-oracle actions on this small task.
- Masking plus a finite-horizon target yields feasible closed-loop behaviour.
- Confidence and expected cost track action correctness and realised cost.

### Does not support

- Reinforcement learning. The policy is supervised imitation of a known oracle.
- Latent need inference, general resource management, or transfer to ASHURA's router.
- A dedicated cost-prediction mechanism; expected cost is derived from the action distribution and
  a fixed cost table.

### Failure analysis

The task is fully observable and small enough for a DP table. The model's near-perfect score
mostly confirms that the training signal and masking are correct; it does not show that the model
would discover needs or costs. An earlier greedy oracle produced a different target and would
have rewarded short-horizon behaviour, so the DP oracle is essential for a valid comparison.

### Decision

Use the DP oracle as the B5 control baseline. Do not wire this policy into ASHURA; the integration
surface and a non-synthetic task are still missing.

---

## BS-EXP-006 — B6 independent validation

**Date:** 2026-11-05
**Code:** `experiments/b6_validation.py`
**Results:** `experiments/results/b6_validation.json`
**Environment:** Python 3.13.14, PyTorch 2.6.0+cu124, CPU.

### Hypothesis

On disjoint held-out permutation rules, a fixed in-context baseline and a frozen GRU are weaker
than fast memory, and per-rule memory retains across task switches.

### Setup

Train on 8 rules, evaluate on 8 disjoint rules. Each held-out rule contributes 8 study/test
episodes; the study walk has 12 transitions and the test walk 16. Four arms:

1. **fixed** — non-recurrent MLP over the flattened study + test prefix (207,496 parameters).
2. **recurrent** — the frozen B1 GRU (206,493 parameters).
3. **fast_memory** — GRU + token-keyed fast memory, reset before every episode (B1 mode).
4. **gated_memory** — GRU + `TaskScopedMemory`, one task per rule, verified writes, task ID
   supplied externally (B3 mode).

The fixed arm was trained for 30 epochs on old-rule study/test pairs; the GRU for 30 epochs on old
walks. Evaluation is zero-shot on the held-out rules. Three seeds.

### Results

Means over seeds 0–2:

| arm | test token acc | test full recall | revisit token acc | memory |
|---|---:|---:|---:|---:|
| fixed in-context MLP | 0.3275 | 0.0000 | — | 0 B |
| frozen GRU | 0.0833 | 0.0000 | 0.0833 | 0 B |
| fast memory, reset per episode | **0.7705** | 0.0000 | 0.0833 | 1,152 B |
| per-rule gated memory | **1.0000** | **1.0000** | **1.0000** | 9,216 B |

The fixed MLP trained in 0.56 s versus 5.85 s for the GRU. The gated memory's revisit retention gap
was exactly 0.0. Fast memory's advantage disappeared after the B1-style reset, as designed.

### Supports

- Fast memory is the mechanism that improves held-out-rule prediction for the frozen core.
- Per-rule memory retains verified transitions across a revisit without new study data.
- The fixed MLP is a stronger in-context baseline than the frozen GRU on this task (0.327 vs
  0.083), so recurrence is not supported as the source of the held-out gain.

### Does not support

- Rule inference or general intelligence. Eight study walks per rule cover every transition of a
  16-cycle, and the task ID is supplied, so 1.000 is verified lookup with full coverage.
- Learned task segmentation or learned gating; the gated arm depends on external IDs.
- Generalization to unobserved transitions. The fixed baseline reaches 0.327 token accuracy but
  zero full recall, and the frozen GRU is near chance.
- A claim that per-rule memory is cheap: it uses 8× the memory of the single-episode fast memory
  in this configuration.

### Failure analysis

The held-out-rule setup measures adaptation, not induction: a single-cycle permutation has a
unique next token per key, so a complete lookup table is sufficient. The fixed MLP can match parts
of the study window but cannot represent the full unseen mapping, which explains partial token
accuracy with zero full recall. The gated arm's perfect score is an upper bound created by full
coverage and external task identity, not a learning result.

### Decision

B6 completes the BrainSim milestone sequence. Use these four arms as the standing comparison for
future BrainSim changes. Do not integrate BrainSim into ASHURA's response path without a task where
it beats the existing deterministic or retrieval baseline.