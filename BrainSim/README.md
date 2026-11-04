# BrainSim

BrainSim is the independent tiny-neural research project from the v2 blueprint
(`spec/New_approach_2.txt`, Part II). It is **not** another chatbot and it does not call Qwen or any
external model. It learns small structured tasks so that claims about prediction, memory and
online adaptation can be tested with measured baselines.

Status: **B1, B2 and B3 baselines complete.** B1 learns hidden permutation rules; B2 solves
fixed-length delayed recall but does **not** show a recurrent advantage over a parameter-matched
fixed MLP; B3 shows that task-scoped memory prevents cross-task overwrite when the task ID is
supplied externally. **28 BrainSim tests pass.** ASHURA does not import BrainSim.

## Quickstart

```bash
cd BrainSim
python -m pytest -q                         # 28 tests
python -m experiments.b1_sequence           # full B1 experiment (6 runs, CPU)
python -m experiments.b2_delayed_copy       # full B2 experiment (3 seeds, CPU)
python -m experiments.b3_gated_memory        # B3 gate baseline (3 seeds, CPU)
# add --quick to B1/B2 for a smoke run (not a result)
```

Results are written to `experiments/results/`. Model checkpoints go to `checkpoints/` and are
intentionally git-ignored. Accuracy is deterministic for a given seed; training time is not.

## What is implemented

| Component | File | State |
|---|---|---|
| Structured encoder | `brainsim/core/encoder.py` | one-hot current + previous token + resource scalar |
| Recurrent core | `brainsim/core/model.py` | 2-layer GRU, prediction / need / action / confidence heads |
| Fixed baseline | `brainsim/core/fixed_baseline.py` | parameter-matched non-recurrent MLP for B2 |
| Offline training | `brainsim/learning/train.py` | PyTorch, AdamW, cross-entropy, checkpoints |
| B2 training/eval | `brainsim/learning/delayed_copy_train.py` | masked recall loss for GRU and fixed MLP |
| Sequence environment | `brainsim/environment/sequence_tasks.py` | hidden single-cycle permutations, disjoint train/held-out rules |
| Delayed-copy environment | `brainsim/environment/delayed_copy.py` | cue → blank delay → GO → reproduce cue |
| Fast associative memory | `brainsim/memory/fast_memory.py` | isolated delta-Hebbian matrix, token or pair keys, reset, save/load |
| Task-scoped gate | `brainsim/memory/gated_memory.py` | per-task memory, verification/surprise admission, bounded LRU cache, save/load |
| Experiments | `experiments/b1_sequence.py`, `b2_delayed_copy.py`, `b3_gated_memory.py` | measured results + JSON |
| Independent API | not adopted yet | integration is deferred until a task needs it |

The need/action/confidence heads exist as outputs but are **untrained**. They belong to B5.

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

## Interpretation

Supported: a small recurrent model learns synthetic permutation rules; an isolated fast memory
changes later behaviour and survives serialization; task-scoped memory prevents overwrite; the
recurrent core solves fixed-length delayed recall.

Not supported: general rule induction, recurrence being necessary for delayed copy, language
ability, learned task identification, safe cross-task memory without a gate, or ASHURA-level
reasoning. The tasks and data are author-designed and synthetic; B1/B2 use 3 seeds.

## Design decisions

- CPU-first (blueprint 3.1); CUDA is available but not used for these runs.
- Fast memory is separate state, never a change to GRU parameters.
- Memory is reset at task boundaries in the measured operating mode; B3 isolates tasks by ID
  rather than solving general interference.
- The fast memory's `logit_scale`, `blend`, `decay`, `eta` and the B3 surprise threshold are
  engineering choices, not calibrated values.

## Layout

```
BrainSim/
  brainsim/
    core/           encoder + GRU model + fixed baseline
    environment/    permutation and delayed-copy tasks
    memory/         fast associative memory + task-scoped gate
    learning/       offline training and delayed-copy helpers
    evaluation/     reserved for B6 metrics
  experiments/      runnable experiments and saved JSON
  tests/            independent unit tests
  research/         experiment log, failures, decisions
  checkpoints/      local checkpoints (git-ignored)
```

## Relation to ASHURA

BrainSim is a subproject of the ASHURA repository but has its own package, tests, checkpoints and
results. ASHURA's runtime does not import BrainSim. The v2 blueprint requires BrainSim to be
useful and testable on its own before integration; that condition is met only for these narrow
synthetic tasks, not for ASHURA's reasoning path.
