# Hypotheses

Each proposed algorithm is a hypothesis, not a feature. Status: `untested` | `partial` | `supported` | `rejected`.

| ID | Hypothesis | Baseline | Status |
|----|-----------|----------|--------|
| H-AMA | Admitting experiences by A(x) retains the information needed for retrieval with fewer stored rows, and fewer false memories, than storing everything. | StoreEverything | **partial** - see EXP-001 |
| H-NFD | Scoring needs by P = aE + bU + cR + dI - eK activates fewer modules than a fixed pipeline without skipping required ones. | always-all | **partial** - see EXP-003 (toy prompt set) |
| H-ADAPT | A small Titans-inspired neural memory improves later related examples vs. no adaptive memory, with bounded interference. | no adaptive memory / FTS5 | **partial** - beats no-memory; does **not** beat FTS5 on lexical tasks (EXP-004) |
| H-DPF | Separate fast (resettable) and slow (versioned) plasticity avoids interference vs. a single update path. | no online adaptation | **partial** - mechanism + bounds implemented, no interference experiment yet |
| H-CAGE | Attribution of failures to one component reduces regression vs. updating the whole selected subsystem. | update whole subsystem | **partial** - attribution tested on synthetic traces; no causal ablation experiment yet |
| H-DREAM | Replay + filtering retains old capability better than ordinary fine-tuning. | plain fine-tuning | **partial/negative on the narrow claim** - EXP-006 four arms: fresh+new 0.00 old retention (rejected), fresh+replay 1.00 (promoted), but stable+new and stable+replay both 1.00. Replay is not uniquely necessary when starting from stable on this small task. |
| H-HARN | A neural arithmetic expert shows a measurable advantage in its intended role. | exact CPU arithmetic | untested (Phase 7) |
| H-PACE | Dynamic capacity beats a fixed-capacity network per unit resource. | fixed capacity | untested (Phase 10) |

NGR is an engineering control, not a hypothesis.
