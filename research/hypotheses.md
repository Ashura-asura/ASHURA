# Hypotheses

Each proposed algorithm is a hypothesis, not a feature. Status: `untested` | `partial` | `supported` | `rejected`.

| ID | Hypothesis | Baseline | Status |
|----|-----------|----------|--------|
| H-AMA | Admitting experiences by A(x) retains the information needed for retrieval with fewer stored rows, and fewer false memories, than storing everything. | StoreEverything | **partial** - EXP-001: equal hit@3, higher acc@1, fewer rows, but 6.2x admission cost and +24% DB; Phase 2 cuts admission to 1.24x with +27% DB (audit/derived state) and calibrates the threshold on synthetic data (EXP-009). Utility is now measured but weights remain hand-set. |
| H-NFD | Scoring needs by P = aE + bU + cR + dI - eK activates fewer modules than a fixed pipeline without skipping required ones. | always-all | **partial** - see EXP-003 (toy prompt set) |
| H-ADAPT | A small Titans-inspired neural memory improves later related examples vs. no adaptive memory, with bounded interference. | no adaptive memory / FTS5 | **partial/negative** - beats no-memory with IDF, but FTS5 stays 1.00 while adaptive falls to 0.41 under noise, 0.88 related at 400 facts, and 0.04 after task switches (EXP-004/EXP-011). |
| H-DPF | Separate fast (resettable) and slow (versioned) plasticity avoids interference vs. a single update path. | no online adaptation | **partial** - mechanism, bounds and a temporary fast update are measured; a rejected slow candidate leaves the stable checkpoint unchanged (EXP-013), but no long-run interference experiment yet. |
| H-CAGE | Attribution of failures to one component reduces regression vs. updating the whole selected subsystem. | update whole subsystem | **partial** - attribution is connected to the candidate/NGR loop and an unattributed failure is refused (EXP-013); the causal ablation (attributed vs whole-subsystem update) is still not measured. |
| H-LOOP | A verified correction can produce a bounded fast update and a candidate that NGR promotes without losing the old capability, while unverified corrections produce no update. | direct unconditional update | **supported on one synthetic scenario** - verified+replay promoted (1.00 old / 1.00 corrected); no-replay candidate rejected; unverified/false/untraced corrections refused (EXP-013). Not evidence of language-model learning. |
| H-DREAM | Replay + filtering retains old capability better than ordinary fine-tuning. | plain fine-tuning | **partial/negative on the narrow claim** - EXP-006 four arms: fresh+new 0.00 old retention (rejected), fresh+replay 1.00 (promoted), but stable+new and stable+replay both 1.00. EXP-012 replay sweep: all ratios/policies tie at 1.00. Replay is not uniquely necessary on this small task. |
| H-COMPARE | Structured value/unit/date extraction plus scoped negation detects contradictions better than token overlap and parity. | lexical comparator | **supported on 28 author-written pairs** - accuracy 1.00 vs 0.64, Brier 0.013 vs 0.381 (EXP-010); not evidence of general semantic understanding. |
| H-HARN | A neural arithmetic expert shows a measurable advantage in its intended role. | exact CPU arithmetic | untested (Phase 7) |
| H-PACE | Dynamic capacity beats a fixed-capacity network per unit resource. | fixed capacity | untested (Phase 10) |

NGR is an engineering control, not a hypothesis.
