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
