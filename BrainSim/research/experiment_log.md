# BrainSim experiment log

All experiments run locally on the target laptop (Windows 11, Intel i7-1165G7, 16 GB RAM,
MX350 2 GB). No external LLM or cloud API is used. BrainSim is a subproject of ASHURA and is
tested independently.

---

## BS-EXP-001 — B1 tiny recurrent baseline + first fast-memory experiment

**Date:** 2026-11-02
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

Means over seeds 0–2 (standard deviation in parentheses where useful):

| hidden | params | train-rule acc | frozen unseen | recurrent carry | token adapted | pair adapted |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 206,493 | 0.956 (0.002) | 0.095 (0.034) | 0.089 (0.032) | **0.775 (0.008)** | **0.686 (0.013)** |
| 384 | 1,799,069 | 0.956 (0.002) | 0.090 (0.017) | 0.087 (0.010) | **0.773 (0.005)** | **0.682 (0.008)** |

Chance on unseen rules is 1/16 = 0.0625. The frozen and recurrent-carry baselines are near chance;
neither the study context nor extra recurrence solves the unseen rule.

Persistence and retention (means over all runs):

| arm | adapted | persisted after save/load | old-rule active | old-rule after reset | drop (active) |
|---|---:|---:|---:|---:|---:|
| token (128) | 0.775 | 0.775 | 0.309 | 0.956 | 0.647 |
| pair (128) | 0.686 | 0.686 | 0.903 | 0.956 | 0.053 |
| token (384) | 0.773 | 0.773 | 0.309 | 0.956 | 0.647 |
| pair (384) | 0.682 | 0.682 | 0.904 | 0.956 | 0.053 |

- The 2% retention tolerance was **not met** by either memory while the new-rule memory was left
  active across a task switch. Pair keys reduced the interference from 64.7 to 5.3 percentage
  points, but did not eliminate it.
- With an explicit reset (the task-scoped operating mode), old-rule accuracy returned exactly to
  the pre-adaptation value (0.956). Model parameters were never modified.
- Save/load reproduced the adapted accuracy exactly for every episode, so the improvement is
  persistent state, not a transient in-process artefact.

Cost (128/384 means):

| metric | 128 | 384 |
|---|---:|---:|
| training time, median | 23.7 s | 36.1 s |
| training time, range | 14.0–24.0 s | 31.9–97.6 s |
| RSS after run | 475 MB | 538 MB |
| in-process inference, p50 | 0.47 ms | 0.40 ms |
| memory update, p50 | ~3.3 ms | ~2.8 ms |
| fast-memory state | 1.1 KB token / 18 KB pair | same |

Training-time variance is large on the laptop (one 384 run took 97.6 s while another took 31.9 s);
the median is more informative than the mean. Inference is in-process only; it excludes any
service or UI overhead.

### Supports

- **H-B1:** both sizes learn the training rules and predict unseen starts (0.956 vs 0.0625 chance).
- **H-FM:** after a study sequence from an unseen rule, fast memory improves a later related
  sequence from 0.095 to 0.775 (token) or 0.686 (pair), with exact persistence across save/load.
- **H-KEY:** pair keys cut old-rule interference from 64.7 to 5.3 percentage points relative to
  token keys, at the cost of 8.9 points of adapted accuracy and lower coverage.
- **Size:** 128 is sufficient for this task; 384 adds 8.7× parameters with no accuracy gain.

### Does not support

- **No rule induction.** The memory stores transitions it observed. It cannot predict a transition
  that was not in the study sequence; the coverage ceiling is 0.75 (token) and about 0.65 (pair).
- **No safe cross-task application.** Pair keys reduce but do not remove interference; both arms
  exceed the 2% tolerance while the new-rule memory remains active. A gate or task identifier is
  required before this could be used across tasks.
- **No language or broad cognitive claim.** The task is 16 symbols and a synthetic permutation.
  There are 3 seeds, one task family, and the data are author-designed.
- **No evidence that the GRU's recurrent state solves unseen rules.** Carrying the study state
  into the test scored 0.089, essentially the frozen baseline.
- **No calibrated plasticity.** `decay`, `eta`, `blend`, `logit_scale` and the 12-transition study
  length were chosen by the author and not tuned against a validation protocol.

### Failure analysis

- Token keys conflate the same symbol in different rules, so applying new-rule memory to old-rule
  sequences overwrites correct predictions.
- Pair keys reduce collisions but not enough: a pair from the new rule can occur in an old rule,
  and the first test position uses a self-pair `(x, x)` that is weakly identifying.
- The memory is an exact lookup; it does not infer the permutation from partial observations.
- Larger hidden size did not improve the learned rule policy; the task is limited by data
  structure and the memory coverage, not capacity.

### Decision

Keep BrainSim as an independent subproject. Do **not** integrate this memory into ASHURA's response
path yet. The next BrainSim work is B2 (working memory and delayed recall) and B3 (gated/surprise
plasticity), with an explicit task-boundary reset as the only currently safe operating mode. The
first integration candidate remains prediction/confidence, not memory writes. See
`research/decisions.md` and `research/failures.md`.
