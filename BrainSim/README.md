# BrainSim

BrainSim is the independent tiny-neural research project from the v2 blueprint
(`New_approach_2.txt`, Part II). It is **not** another chatbot and it does not call Qwen or any
external model. It learns small structured tasks so that claims about prediction, memory and
online adaptation can be tested with measured baselines.

Status: **B1 (tiny neural baseline) complete; first fast-memory experiment complete.** 19 BrainSim
tests pass. ASHURA does not depend on BrainSim yet; integration starts only after independent
learning is demonstrated (blueprint section 21).

## Quickstart

```bash
cd BrainSim
python -m pytest -q                         # 19 tests
python -m experiments.b1_sequence           # full experiment (6 runs, CPU)
python -m experiments.b1_sequence --quick   # smoke run, not a result
```

Results are written to `experiments/results/b1_sequence.json`. Model checkpoints go to
`checkpoints/` and are intentionally git-ignored. The full run takes roughly 1–4 minutes on the
target laptop depending on CPU contention; accuracy is deterministic for a given seed, training
time is not.

## What is implemented

| Component | File | State |
|---|---|---|
| Structured encoder | `brainsim/core/encoder.py` | one-hot current + previous token + resource scalar |
| Recurrent core | `brainsim/core/model.py` | 2-layer GRU, prediction / need / action / confidence heads |
| Offline training | `brainsim/learning/train.py` | PyTorch, AdamW, cross-entropy, checkpoints |
| Sequence environment | `brainsim/environment/sequence_tasks.py` | hidden single-cycle permutations, disjoint train/held-out rules |
| Fast associative memory | `brainsim/memory/fast_memory.py` | isolated delta-Hebbian matrix, token or (previous, current) keys, reset, save/load |
| First experiment | `experiments/b1_sequence.py` | frozen vs token-key vs pair-key fast memory; persistence; retention |

The need/action/confidence heads exist as outputs but are **untrained** in B1. They belong to B5
(need and resource control) and are not used by the current results.

## Task

Each episode hides a permutation of 16 symbols with exactly one cycle. The next token is
`rule[current]`. The model trains on 8 rules and is tested on 8 disjoint rules.

- Offline training: 32 walks per training rule, 24 tokens each, 30 epochs.
- Adaptation: a 12-transition study walk from an unseen rule, then a later 16-transition test walk
  from the same rule.
- Study covers 12 of the 16 token transitions, so a perfect token-keyed memory can cover at most
  75% of the test positions; the rest fall back to the model.

## Results (3 seeds, CPU, 30 epochs)

Means over seeds 0–2; full per-run data in `experiments/results/b1_sequence.json`.

| hidden | params | train-rule acc | frozen unseen | recur. carry | token memory | pair memory |
|---:|---:|---:|---:|---:|---:|---:|
| 128 | 206,493 | 0.956 | 0.095 | 0.089 | **0.775** | **0.686** |
| 384 | 1,799,069 | 0.956 | 0.090 | 0.087 | **0.773** | **0.682** |

- **B1 learning:** both sizes learn the training rules and predict unseen starts from them
  (0.956 vs chance 1/16 = 0.0625).
- **Fast memory:** after a study walk from an unseen rule, token-keyed memory raises accuracy from
  0.095 to 0.775; pair-keyed memory raises it to 0.686. Persistence is exact: save/load reproduces
  the adapted accuracy (0.775 / 0.686).
- **Retention:** after a task switch without reset, token memory collapses old-rule accuracy to
  0.309 (drop 0.647); pair keys reduce the damage to 0.903 (drop 0.053). Both exceed the 2%
  tolerance while the new-rule memory is active. After an explicit reset, old-rule accuracy returns
  to 0.956. **The safe operating mode is task-scoped memory; cross-task use needs a gate.**
- **Size:** 384 has 8.7× the parameters and no accuracy gain. 128 is the better default for this
  task.
- **Cost:** 0.4–0.5 ms median in-process inference per 16-token test sequence; ~475–538 MB RSS;
  memory state is 1.1 KB (token keys) or 18 KB (pair keys).

## Interpretation

Supported: a small recurrent model can learn the synthetic rules; an isolated fast memory changes
later behaviour on a related unseen-rule sequence; the improvement survives serialization; context
keys reduce interference compared with token-only keys.

Not supported: inference of an unobserved transition, general rule induction, language ability,
or safe cross-task memory without a gate. The memory is a lookup on observed transitions; its
coverage ceiling (0.75 token, ~0.65 pair) explains most of the adaptation result. The task and
data are author-designed and synthetic. There are 3 seeds and one task family.

## Design decisions

- The model is CPU-first (blueprint 3.1); CUDA is available but not used for these runs.
- The fast memory is a separate state, never a change to GRU parameters. Online learning means
  writing the matrix, not fine-tuning the network.
- Memory is reset at task/episode boundaries in the measured operating mode. The experiment also
  reports the interference that occurs when it is left active.
- The fast memory's `logit_scale`, `blend`, `decay` and `eta` are engineering choices, not
  calibrated values. See `research/experiment_log.md`.

## Layout

```
BrainSim/
  brainsim/
    core/           encoder + GRU model
    environment/    synthetic sequence tasks
    memory/         fast associative memory
    learning/       offline training and evaluation helpers
    evaluation/     reserved for B6 metrics
  experiments/      runnable experiments and saved JSON
  tests/            independent unit tests
  research/         experiment log, failures, decisions
  checkpoints/      local checkpoints (git-ignored)
```

## Relation to ASHURA

BrainSim is a subproject of the ASHURA repository but has its own package, tests, checkpoints and
results. ASHURA's 128 tests are unchanged and the ASHURA runtime does not import BrainSim. The v2
blueprint requires BrainSim to be useful and testable on its own before any integration; that
condition is now met only for the narrow B1/fast-memory task, not for ASHURA's reasoning path.
