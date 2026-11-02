"""Execution trace (needed by CAGE later, and for overhead measurement now)."""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TraceStep:
    module: str
    input: Any
    output: Any
    ms: float
    ok: bool = True
    note: str = ""


@dataclass
class ExecutionTrace:
    task: str
    steps: list[TraceStep] = field(default_factory=list)
    routing: dict = field(default_factory=dict)
    routing_ms: float = 0.0
    total_ms: float = 0.0
    started: float = field(default_factory=time.time)

    def add(self, step: TraceStep) -> None:
        self.steps.append(step)

    def step(self, module: str):
        for s in self.steps:
            if s.module == module:
                return s
        return None

    def to_json(self) -> str:
        return json.dumps(asdict(self), default=str, indent=2)
