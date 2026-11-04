# BrainSim

BrainSim is the independent tiny-neural research project from the v2 blueprint
(`spec/New_approach_2.txt`, Part II). It is **not** another chatbot and it does not call Qwen or any
external model. It learns small structured tasks so that claims about prediction, memory and
online adaptation can be tested with measured baselines.

Status: **B1–B6 baselines complete.** B1 learns hidden permutation rules. B2 solves fixed-length
delayed recall but does **not** show a recurrent advantage over a parameter-matched fixed MLP. B3
shows that task-scoped memory prevents cross-task overwrite when the task ID is supplied
externally. B4 shows replay-augmented fine-tuning reduces old-rule forgetting from 49.3 to 1.18
points. B5 trains a small policy that matches a finite-horizon DP oracle on a synthetic
budgeted-choice task. B6 compares fixed, recurrent, fast-memory and gated-memory arms on disjoint
held-out rules. **46 BrainSim tests pass.** ASHURA does not import BrainSim.

Detailed cross-milestone results, limits and validity threats:
[`../results_brainsim.md`](../results_brainsim.md).

## Quickstart

```bash
cd BrainSim
python -m pytest -q                         # 46 tests
python -m experiments.b1_sequence           # full B1 experiment (6 runs, CPU)
python -m experiments.b2_delayed_copy       # full B2 experiment (3 seeds, CPU)
python -m experiments.b3_gated_memory        # B3 gate baseline (3 seeds, CPU)
python -m experiments.b4_consolidation       # B4 replay vs new-only fine-tuning
python -m experiments.b5_control             # B5 budgeted need/action control
python -m experiments.b6_validation          # B6 four-arm held-out validation
# add --quick to any experiment for a smoke run (not a result)
```

Results are written to `experiments/results/`. Model checkpoints go to `checkpoints/` and are
intentionally git-ignored. Accuracy is deterministic for a given seed; training time is not.

## What is implemented

| Component | File | State |
|---|---|---|
| Structured encoder | `brainsim/core/encoder.py` | one-hot current + previous token + resource scalar |
| Recurrent core | `brainsim/core/model.py` | 2-layer GRU, prediction / need / action / confidence heads |
| Fixed baseline | `brainsim/core/fixed_baseline.py` | parameter-matched non-recurrent MLPs for B2 and B6 |
| Offline training | `brainsim/learning/train.py` | PyTorch, AdamW, cross-entropy, checkpoints |
| B2 training/eval | `brainsim/learning/delayed_copy_train.py` | masked recall loss for GRU and fixed MLP |
| B4 replay / fine-tune | `brainsim/learning/replay.py`, `finetune.py` | bounded token replay buffer, persistent fine-tuning, checkpoints |
| B5 control task | `brainsim/environment/control_tasks.py` | needs, actions, costs, finite-horizon DP oracle, budget simulation |
| B5 training/eval | `brainsim/learning/control_train.py` | supervised action/need/confidence training, open- and closed-loop evaluation |
| B6 episode training | `brainsim/learning/episode_train.py` | fixed in-context baseline training/evaluation |
| Sequence environment | `brainsim/environment/sequence_tasks.py` | hidden single-cycle permutations, disjoint train/held-out rules |
| Delayed-copy environment | `brainsim/environment/delayed_copy.py` | cue → blank delay → GO → reproduce cue |
| Fast associative memory | `brainsim/memory/fast_memory.py` | isolated delta-Hebbian matrix, token or pair keys, reset, save/load |
| Task-scoped gate | `brainsim/memory/gated_memory.py` | per-task memory, verification/surprise admission, bounded LRU cache, save/load |
| Experiments | `experiments/b1_sequence.py` … `b6_validation.py` | measured results + JSON |
| Independent API | not adopted yet | integration is deferred until a task needs it |

The need and action heads are trained only for the B5 control task; they are not used by the
sequence experiments. The B5 confidence head is trained against action correctness.

## B1 — permutation sequences + fast memory

Each episode hides a permutation of 16 symbols with exactly one cycle. The model trains on 8 rules
and is tested on 8 disjoint rules. Study covers 12 of 16 transitions, then a later 16-transition
test sequence uses the same rule. Means over seeds 0–2, 30 epochs, CPU:

| hidden | params | train-rule acc | frozen unseen | recurrent carry | token memory | pair memory |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 206,493 | 0.957 | 0.085 | 0.081 | **0.771** | **0.681** |
| 384 | 1,799,069 | 0.957 | 0.096 | 0.094 | **0.777** | **0.688** |

- Fast memory raises unseen-rule accuracy from ~0.09 to 0.68–0.78; save/load reproduces the
  adapted accuracy exactly.
- Leaving memory active across a task switch drops old-rule accuracy from 0.957 to 0.309 (token)
  or 0.904 (pair): drops of 64.8 and 5.3 points, both above the 2% tolerance. After an explicit
  reset, old-rule accuracy returns to 0.957.
- 128 is the default: 384 adds 8.7× parameters with no accuracy gain.
- Median training time: 20.6 s (128), 49.6 s (384); RSS ~476–540 MB; inference ~0.4–0.5 ms per
  16-token sequence; memory state 1.1 KB (token) / 18 KB (pair).

## B2 — delayed recall: recurrent vs fixed baseline

Task: three random cue symbols, a blank delay, a GO token, then reproduce the cues. Delays 2, 4, 6
and 8 are trained; 1, 12, 16 and 20 are held out. 4,096 sequences, 30 epochs, 3 seeds.

| arm | params | train time (s) | token acc, all delays | full recall, all delays |
|---|---:|---:|---:|---:|
| GRU (BrainSim core) | 204,183 | 112–144 | 1.000 | 1.000 |
| fixed MLP | 217,560 | 9–18 | 1.000 | 1.000 |

- **H-B2 supported:** the recurrent core uses earlier cue information to solve a later recall
  task, including delays four times longer than any training delay.
- **H-DELAY falsified:** the non-recurrent MLP also scored 1.000 on every delay and trained
  6–16× faster. This fixed-length copy task does not require recurrence; the MLP can read the cue
  block directly from its flattened input.
- The MLP is a strong upper-bound baseline, not a memoryless one. A memoryless baseline is at
  chance (1/8 per token, 1/512 for all three).
- A real test of recurrence needs variable-length cues, relational operations, or a task where
  the delay content matters. That is B2b, not claimed here.

## B3 — task-scoped gate vs shared memory

Two disjoint permutation rules are written to memory. Shared token memory overwrites the old rule;
a task-scoped memory with an externally supplied task ID does not. Means over 3 seeds:

| arm | old before switch | old after switch | new |
|---|---:|---:|---:|
| shared token memory | 1.000 | 0.104 | 1.000 |
| task-scoped gate | 1.000 | 1.000 | 1.000 |

- This is a **baseline for isolation**, not learned gating: the task ID is supplied by the caller,
  and the measured updates are verified, so the surprise threshold is not exercised.
- It confirms the B1 conclusion: task-scoped reset is the only currently safe operating mode.
  Learned task identification and cross-task gating remain unbuilt.

## B4 — slow consolidation: new-only vs replay

Starting from the same B1 checkpoint, both arms fine-tune on 8 disjoint new rules for 15 epochs.
The replay arm mixes 50% old-rule sequences from a bounded 512-sequence buffer. Means over 3 seeds:

| arm | old-rule accuracy | old drop | new-rule accuracy |
|---|---:|---:|---:|
| base checkpoint | 0.957 | — | 0.082 |
| new-only fine-tune | 0.463 | **49.3 pts** | 0.941 |
| replay fine-tune | 0.945 | **1.18 pts** | 0.931 |

- **H-B4 supported:** persistent updates on new rules alone cause severe forgetting, far beyond
  the 2% tolerance.
- **H-REPLAY supported:** replay brought every seed inside the tolerance while keeping new-rule
  accuracy within 1 point of new-only. All checkpoints round-trip exactly.
- The replay arm sees more examples and takes ~38% longer (0.92 s vs 0.66 s per seed). This is a
  method comparison, not an equal-FLOPs comparison.
- Retention is measured on new walks from the old rules, not a separate domain.

## B5 — need and resource control

A 128-hidden GRU sees a need type and the current budget at every step, chooses one of six actions
with fixed costs, and is trained by supervised imitation of a finite-horizon DP oracle. The oracle
is not greedy: waiting can restore budget for a better action later. Means over 3 seeds, 20 epochs:

| policy | total utility / episode | action accuracy | cost / episode |
|---|---:|---:|---:|
| learned (closed loop) | **5.574** | 0.9998 | 13.41 |
| DP oracle | 5.5745 | 1.000 | 13.42 |
| need-match, cost-blind | 5.406 | 0.871 | 12.81 |
| always highest-mean action | 2.160 | 0.345 | 13.63 |
| random feasible | 2.271 | 0.247 | 12.35 |
| always wait | 0.400 | 0.059 | 0.00 |

- The learned policy matches the oracle's measured utility and stays feasible in closed loop
  (0.0 infeasible actions after masking; the raw policy also chose no infeasible action).
- Confidence ECE is 0.0002 and expected-cost MAE is 0.0002 on the evaluation set.
- **Limits:** supervised imitation of a known oracle, small fully observed task, need and budget
  supplied as inputs. This is not reinforcement learning, not latent need inference, and not
  general resource management.

## B6 — independent validation on held-out rules

Four arms are evaluated on 8 disjoint held-out rules after training only on the 8 old rules.
Study/test episodes are author-designed; means over 3 seeds:

| arm | test token acc | test full recall | revisit token acc | memory |
|---|---:|---:|---:|---:|
| fixed in-context MLP | 0.327 | 0.000 | — | 0 |
| frozen GRU | 0.083 | 0.000 | 0.083 | 0 |
| GRU + fast memory, reset per episode | **0.771** | 0.000 | 0.083 | 1.2 KB |
| GRU + per-rule gated memory | **1.000** | **1.000** | **1.000** | 9.2 KB |

- The fixed MLP (207,496 parameters) and GRU (206,493) are parameter-matched. The fixed MLP is a
  strong in-context baseline and beats the frozen GRU, but neither generalizes the held-out rule.
- Fast memory helps only while the current episode is active; after the B1-style reset, revisit
  falls back to the frozen GRU. Per-rule gated memory retains 1.000 across the revisit because it
  keeps the verified study transitions.
- **The 1.000 is lookup, not intelligence.** Eight study walks per rule cover every transition;
  the gated arm receives the correct rule ID and verified writes. It does not infer the rule, learn
  task boundaries, or generalize to unobserved transitions.
- The gated arm's revisit accuracy equals its first-pass accuracy (retention gap 0.0) but it uses
  8× the memory of the single-episode fast memory.

## Interpretation

Supported: a small recurrent model learns synthetic permutation rules; an isolated fast memory
changes later behaviour and survives serialization; task-scoped memory prevents overwrite; the
recurrent core solves fixed-length delayed recall; replay-augmented fine-tuning preserves old-rule
accuracy within 2% while learning new rules; a small supervised policy matches a finite-horizon DP
oracle on a synthetic budgeted-choice task; and per-rule memory retains verified transitions across
a revisit.

Not supported: general rule induction, recurrence being necessary for delayed copy, language
ability, learned task identification, safe cross-task memory without a gate, reinforcement
learning, latent need inference, general resource management, rule inference from partial
observations, or ASHURA-level reasoning. The tasks and data are author-designed and synthetic;
all experiments use 3 seeds. B6's 1.000 is lookup with an externally supplied rule ID, not
intelligence.

## Design decisions

- CPU-first (blueprint 3.1); CUDA is available but not used for these runs.
- Fast memory is separate state, never a change to GRU parameters.
- Memory is reset at task boundaries in the measured operating mode; B3 isolates tasks by ID
  rather than solving general interference.
- The fast memory's `logit_scale`, `blend`, `decay`, `eta` and the B3 surprise threshold are
  engineering choices, not calibrated values.
- B4 updates persistent weights only on the candidate arm; the safe default remains frozen weights
  plus task-scoped memory. Replay is a bounded mitigation, not a guarantee.
- B5's target is a finite-horizon DP oracle, not a hand-written greedy rule. The learned policy is
  supervised imitation and is not trained by reinforcement.
- B6 reports the fixed in-context MLP and the frozen GRU as first-class baselines. The gated memory
  receives task IDs and verified writes; those inputs are not learned.

## Layout

```
BrainSim/
  brainsim/
    core/           encoder + GRU model + fixed B2/B6 baselines
    environment/    permutation, delayed-copy and budgeted-control tasks
    memory/         fast associative memory + task-scoped gate
    learning/       offline training, recall, replay/fine-tune, control, episode helpers
    evaluation/     reserved for shared B6 metrics
  experiments/      runnable experiments and saved JSON
  tests/            independent unit tests
  research/         experiment log, failures, decisions
  checkpoints/      local checkpoints (git-ignored)
```

## Relation to ASHURA

BrainSim is a subproject of the ASHURA repository but has its own package, tests, checkpoints and
results. ASHURA's runtime does not import BrainSim. The v2 blueprint requires BrainSim to be
useful and testable on its own before integration; B1–B6 now satisfy that condition on narrow
synthetic tasks. Integration is still deferred because BrainSim has no measured benefit for
ASHURA's response path.
