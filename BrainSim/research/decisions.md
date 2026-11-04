# BrainSim decisions

- **D-BS-001 â€” BrainSim is a subproject of the ASHURA repository, not a replacement for ASHURA.**
  It has its own package (`brainsim`), tests, checkpoints and results under `BrainSim/`. ASHURA's
  runtime and test suite are unchanged; ASHURA does not import BrainSim. This follows the v2
  blueprint's "parallel development, independent validation" rule.

- **D-BS-002 â€” B1 uses a 2-layer GRU with 128 hidden units as the default, despite the blueprint's
  1â€“5M parameter target.** The measured 128-hidden model has 206k parameters and matched the
  1.8M-parameter 384-hidden model on the first task (BS-EXP-001). The target range is an initial
  engineering guide, not a requirement; scale only when a task needs it. Larger configurations can
  still be selected with `--sizes`.

- **D-BS-003 â€” Fast memory is an isolated matrix, never a change to the recurrent weights during
  the first experiment.** Online adaptation writes `M`; the GRU is frozen. This isolates the
  central claim and makes reset/persistence tests meaningful. Persistent parameter updates remain
  a later, NGR-style slow-consolidation step (B4), not part of B1.

- **D-BS-004 â€” Fast memory is task-scoped: reset at episode/task boundaries.** The measured
  operating mode resets memory before each study sequence. Cross-task application was tested and
  failed the 2% retention tolerance for both token and pair keys (F-BS-001, F-BS-002). Do not wire
  cross-task memory into ASHURA without a gate and a retention evaluation.

- **D-BS-005 â€” Use pair keys as the better retention/adaptation tradeoff for now, not as a solved
  design.** Pair keys scored 0.681 adapted with a 0.053 retention drop; token keys scored 0.771
  with a 0.648 drop. Pair keys are preferable when old-task safety matters, but neither is
  acceptable for unrestricted cross-task use. This is a measured tradeoff, not a claim that pair
  keys are generally superior.

- **D-BS-006 â€” Do not integrate BrainSim into ASHURA yet.** The v2 blueprint says integration
  begins only after BrainSim independently demonstrates useful learning. B1/fast memory now does so
  on a narrow synthetic task, but the integration surface (prediction/confidence/need) and the
  safety gate are not built. B2 and B3 are now measured baselines, but the integration surface and safety gate are still
  missing. The next milestone is B2b/B4, not ASHURA wiring.


- **D-BS-007 — B2 is a capability baseline, not evidence that recurrence is necessary.**
  The GRU solved delayed recall at every delay, but a parameter-matched fixed MLP also reached
  1.000 and trained 6–16× faster. The task saturates and the delay carries no task-relevant
  information. Keep the GRU as the BrainSim core, but do not cite B2 as a recurrent advantage.
  A harder B2b must use variable-length or relational recall before that claim can be tested.

- **D-BS-008 — Task-scoped memory is the safe default, but task identity is external.**
  B3 showed 1.000 old-task retention with per-task memory versus 0.104 for a shared token table.
  The result depends on the caller supplying a correct task ID and on verified writes bypassing
  the surprise gate. Do not claim learned task segmentation or general cross-task safety.

- **D-BS-009 — Do not adopt the BrainSim runtime API yet.**
  A versioned wrapper and corpus generator were considered, but ASHURA has no response-path use
  case that has passed an independent experiment. Keep the package small and integration
  deferred until B2b/B4 produce a measured signal worth wiring.
