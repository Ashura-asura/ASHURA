# ASHURA Workbench — Phase 1 Design Package

Status: **design approved and implemented 2026-11-06** (D-062/D-063, extended by D-064). The five
workspaces, local math/table rendering, runtime-only Ollama model selector, document intake,
bounded tools and optional web review are in the production console. Verification: 367 tests
(2 skipped), 40 web tests, 19 browser baselines, one real model-switch sequence and a live
two-process token-restart check — see `research/EXP-021_local_ui.md`,
`research/EXP-022_documents_tools_web.md` and `EXP-021_model_switch_verification.json`. The audit,
spec, plan and prototype below are retained as the design record; their earlier test counts and
"awaiting approval" status describe the pre-implementation state.

This directory contains the Phase 1 deliverables for the ASHURA interface redesign:

| File | Purpose |
| --- | --- |
| [`PHASE1_UI_AUDIT.md`](PHASE1_UI_AUDIT.md) | Source-level audit of the current console, capability matrix and list of unsupported or misleading claims. |
| [`PHASE1_WORKBENCH_SPEC.md`](PHASE1_WORKBENCH_SPEC.md) | Revised architecture, five workspaces, component hierarchy, state semantics, design tokens, responsive and accessibility rules. |
| [`PHASE1_IMPLEMENTATION_PLAN.md`](PHASE1_IMPLEMENTATION_PLAN.md) | File-by-file Phases 2–5 plan, additive API exposures, compatibility constraints, risks and test strategy. |
| [`mockups/workbench.html`](mockups/workbench.html) | High-fidelity interactive design prototype, dark theme by default. |
| [`mockups/tokens.css`](mockups/tokens.css) | The proposed design-token source of truth. |
| [`mockups/screenshots/`](mockups/screenshots/) | Before/after screenshots at review and test widths. |

## View the prototype

The prototype is a static file and needs no server:

```powershell
start design\mockups\workbench.html
```

Use the left rail to move between the five workspaces. The theme control cycles
dark/light; the Settings theme picker also exposes the system option. `Ctrl K`
focuses search. On narrow widths, the sessions, inspector, operations and
memory-list panels become drawers.

The prototype contains **sample data and fake model responses**. It is a visual
and interaction specification, not a measurement of this machine, this model or
the current database. Production views must render real values or an explicit
"not available" state.

## Screenshot index

Before the redesign (current console, seeded demo data):

- `before-command-1440.png`, `before-command-390.png`
- `before-command-light-1440.png`, `before-inspector-1440.png`

After (design prototype):

- `after-command-1440.png`, `after-command-1920.png`, `after-command-1024.png`
- `after-command-768.png`, `after-command-430.png`, `after-command-390.png`,
  `after-command-375.png`, `after-command-320.png`
- `after-command-light-1440.png`, `after-settings-light-1440.png`
- `after-execution-1440.png`, `after-knowledge-1440.png`,
  `after-system-1440.png`, `after-settings-1440.png`
- `after-execution-390.png`, `after-execution-operations-390.png`
- `after-system-390.png`, `after-settings-390.png`
- `after-knowledge-memories-390.png`

## Approval gate (passed)

The owner approved the scope, visual direction, honest-state rules and Phase 2-5 plan before
implementation. The checklist is retained as the design record; the items are marked done because
the implementation and its evidence now exist.

- [x] the five-workspace information architecture;
- [x] the honest-state rules (verified / failed / unavailable, health / readiness,
  measured / unavailable);
- [x] the visual direction and token set;
- [x] the additive read-only API exposures;
- [x] the Phase 2-5 scope and the Playwright CI job.

The production console is the implemented workbench described in `research/EXP-021_local_ui.md`
and `research/EXP-022_documents_tools_web.md`; the mockups remain the visual specification.
