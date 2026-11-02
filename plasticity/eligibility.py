"""CAGE attribution from an execution trace (spec 9). EXPERIMENTAL.

The output is a hypothesis, not proof. Only the first independently failing component is marked
eligible; downstream failures are treated as propagated unless their own verifier failed first.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from brain.execution_trace import ExecutionTrace


@dataclass(frozen=True)
class Attribution:
    module: str | None
    confidence: float
    reason: str
    eligible: tuple[str, ...]


Verifiers = dict[str, Callable[[Any], bool]]


def attribute(trace: ExecutionTrace, expected: Any = None, verifiers: Verifiers | None = None) -> Attribution:
    """Find the first verifiable divergence and assign eligibility.

    Order of evidence:
    1. a step already marked `ok=False` (direct failure signal), confidence 1.0;
    2. a step whose output fails its registered verifier, confidence 0.9;
    3. final output != expected with no intermediate evidence: NOT attributable, confidence 0.3.
    """
    for step in trace.steps:
        if not step.ok:
            return Attribution(step.module, 1.0, f"step {step.module!r} failed: {step.note or 'no note'}",
                               (step.module,))
    if verifiers:
        for step in trace.steps:
            check = verifiers.get(step.module)
            if check is not None and not check(step.output):
                return Attribution(step.module, 0.9, f"verifier rejected {step.module!r} output", (step.module,))
    if expected is not None and trace.steps:
        last = trace.steps[-1]
        if last.output != expected:
            return Attribution(None, 0.3,
                               f"final output diverged at {last.module!r} but no intermediate verifier "
                               "identified the cause; refusing to attribute", ())
    return Attribution(None, 1.0, "no divergence found", ())
