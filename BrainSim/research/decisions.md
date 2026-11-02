# BrainSim decisions

- **D-BS-001 — BrainSim is a subproject of the ASHURA repository, not a replacement for ASHURA.**
  It has its own package (`brainsim`), tests, checkpoints and results under `BrainSim/`. ASHURA's
  128 tests and runtime are unchanged; ASHURA does not import BrainSim. This follows the v2
  blueprint's "parallel development, independent validation" rule.

- **D-BS-002 — B1 uses a 2-layer GRU with 128 hidden units as the default, despite the blueprint's
  1–5M parameter target.** The measured 128-hidden model has 206k parameters and matched the
  1.8M-parameter 384-hidden model on the first task (BS-EXP-001). The target range is an initial
  engineering guide, not a requirement; scale only when a task needs it. Larger configurations can
  still be selected with `--sizes`.

- **D-BS-003 — Fast memory is an isolated matrix, never a change to the recurrent weights during
  the first experiment.** Online adaptation writes `M`; the GRU is frozen. This isolates the
  central claim and makes reset/persistence tests meaningful. Persistent parameter updates remain
  a later, NGR-style slow-consolidation step (B4), not part of B1.

- **D-BS-004 — Fast memory is task-scoped: reset at episode/task boundaries.** The measured
  operating mode resets memory before each study sequence. Cross-task application was tested and
  failed the 2% retention tolerance for both token and pair keys (F-BS-001, F-BS-002). Do not wire
  cross-task memory into ASHURA without a gate and a retention evaluation.

- **D-BS-005 — Use pair keys as the better retention/adaptation tradeoff for now, not as a solved
  design.** Pair keys scored 0.686 adapted with a 0.053 retention drop; token keys scored 0.775
  with a 0.647 drop. Pair keys are preferable when old-task safety matters, but neither is
  acceptable for unrestricted cross-task use. This is a measured tradeoff, not a claim that pair
  keys are generally superior.

- **D-BS-006 — Do not integrate BrainSim into ASHURA yet.** The v2 blueprint says integration
  begins only after BrainSim independently demonstrates useful learning. B1/fast memory now does so
  on a narrow synthetic task, but the integration surface (prediction/confidence/need) and the
  safety gate are not built. The next milestone is B2/B3, not ASHURA wiring.
