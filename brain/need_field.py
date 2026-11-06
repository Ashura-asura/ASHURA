"""NFD - Need Field Dynamics (spec 7). EXPERIMENTAL: weights are uncalibrated.

P_i = a*E_i + b*U_i + c*R_i + d*I_i - e*K_i
E error, U uncertainty, R recurrence, I importance, K execution cost.
Uncertainty is deliberately NOT importance (spec 7.4): a low-confidence trivial question must not
wake an expensive module, so expensive modules are only reached through importance + cost.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from skills.arithmetic.parser import extract_expression, is_pure_arithmetic

from .router import ModuleRegistry, RoutingDecision, available_ram_mb, cpu_busy_percent

NEEDS = ["language", "exact_retrieval", "semantic_retrieval", "arithmetic", "ocr", "reasoning", "verification", "learning"]

_MEMORY_CUES = re.compile(r"\b(remember|earlier|before|last time|previously|you said|i told you|what did i|recall)\b", re.I)
_REASON_CUES = re.compile(r"\b(why|explain|step by step|prove|plan|compare|analy[sz]e|derive)\b", re.I)
_LEARN_CUES = re.compile(r"\b(that'?s wrong|incorrect|actually,|correction|the correct answer|learn this)\b", re.I)


@dataclass
class Task:
    text: str
    has_image: bool = False
    image_path: str | None = None
    user_correction: bool = False
    # Modules the user explicitly asked for (e.g. the CLI's /ocr command). They are still skipped if
    # unavailable, but are never deferred because of RAM / CPU load or a low priority score.
    force: tuple[str, ...] = ()
    # Prior completed turns as (user, assistant) pairs. The web UI supplies this; the CLI leaves it
    # empty. Only the most recent turns are placed in the language prompt.
    history: tuple[tuple[str, str], ...] = ()


@dataclass
class NeedSignals:
    E: float = 0.0
    U: float = 0.0
    R: float = 0.0
    I: float = 0.0


@dataclass
class NFDConfig:
    a_error: float = 1.0
    b_uncertainty: float = 0.6
    c_recurrence: float = 0.5
    d_importance: float = 1.0
    e_cost: float = 0.8
    activation_threshold: float = 0.25
    ram_headroom_mb: float = 1500.0
    cpu_busy_percent: float = 85.0       # above this, optional heavy modules are deferred
    heavy_latency_ms: float = 500.0      # "heavy" = estimated latency at or above this

    @classmethod
    def from_dict(cls, d: dict) -> "NFDConfig":
        m = {"a_error": "a_error", "b_uncertainty": "b_uncertainty", "c_recurrence": "c_recurrence",
             "d_importance": "d_importance", "e_cost": "e_cost", "activation_threshold": "activation_threshold",
             "ram_headroom_mb": "ram_headroom_mb", "cpu_busy_percent": "cpu_busy_percent",
             "heavy_latency_ms": "heavy_latency_ms"}
        return cls(**{k: d[k] for k in m if k in d})


class NeedStats:
    """Running per-need error and demand statistics (spec 7.2 step 10)."""

    def __init__(self):
        self.runs = defaultdict(int)
        self.errors = defaultdict(int)

    def update(self, need: str, ok: bool) -> None:
        self.runs[need] += 1
        self.errors[need] += 0 if ok else 1

    def error_rate(self, need: str) -> float:
        return self.errors[need] / self.runs[need] if self.runs[need] else 0.0

    def recurrence(self, need: str) -> float:
        return min(1.0, self.runs[need] / 20.0)


class NeedField:
    def __init__(self, registry: ModuleRegistry, cfg: NFDConfig | None = None, stats: NeedStats | None = None,
                 cpu_fn=cpu_busy_percent, ram_fn=None):
        self.registry, self.cfg, self.stats = registry, cfg or NFDConfig(), stats or NeedStats()
        self._cpu_fn = cpu_fn
        self._ram_fn = ram_fn            # None -> live system reading; tests/benchmarks inject a fixed value

    # 1-3: classify + estimate
    def signals(self, task: Task) -> dict[str, NeedSignals]:
        t = task.text
        expr = extract_expression(t)
        pure = is_pure_arithmetic(t)
        sig = {n: NeedSignals() for n in NEEDS}
        sig["language"].I = 0.0 if pure else 1.0
        sig["language"].U = 0.5
        sig["arithmetic"].I = 1.0 if expr else 0.0
        sig["verification"].I = 0.9 if expr else 0.0
        sig["ocr"].I = 1.0 if task.has_image else 0.0
        sig["exact_retrieval"].I = 0.9 if _MEMORY_CUES.search(t) else (0.1 if not pure else 0.0)
        sig["reasoning"].I = 0.8 if _REASON_CUES.search(t) else 0.0
        sig["reasoning"].U = 0.7 if len(t.split()) > 12 else 0.4
        sig["learning"].I = 1.0 if (task.user_correction or _LEARN_CUES.search(t)) else 0.0
        sig["semantic_retrieval"].I = 0.0     # only if exact retrieval fails AND a vector index has proven value
        for n in NEEDS:                        # feedback from earlier runs
            sig[n].E = self.stats.error_rate(n)
            sig[n].R = self.stats.recurrence(n) if sig[n].I > 0 else 0.0
        return sig

    def priority(self, need: str, s: NeedSignals) -> float:
        c = self.cfg
        K = self.registry.get(need).cost if need in self.registry else 0.0
        return c.a_error * s.E + c.b_uncertainty * s.U + c.c_recurrence * s.R + c.d_importance * s.I - c.e_cost * K

    # 4-7: select smallest adequate set under resource limits
    def select(self, task: Task) -> RoutingDecision:
        sig = self.signals(task)
        pri = {n: self.priority(n, sig[n]) for n in NEEDS if n in self.registry}
        dec = RoutingDecision(selected=[], priorities=pri)
        ram = self._ram_fn() if self._ram_fn else available_ram_mb()
        budget = ram - self.cfg.ram_headroom_mb
        cpu = self._cpu_fn()
        pure = is_pure_arithmetic(task.text)
        for n in sorted(pri, key=pri.get, reverse=True):
            spec = self.registry.get(n)
            if n == "language" and pure:
                dec.skipped[n] = "cheap skill sufficient"
            elif sig[n].I <= 0 and n != "language":
                dec.skipped[n] = "not needed"
            elif n in task.force and spec.available:
                dec.selected.append(n)                       # explicit user request: no load-based deferral
                dec.est_latency_ms += spec.est_latency_ms
                dec.est_ram_mb += spec.extra_ram_mb
            elif pri[n] < self.cfg.activation_threshold:
                dec.skipped[n] = f"priority {pri[n]:.2f} below threshold"
            elif not spec.available:
                dec.skipped[n] = "needed but not implemented yet"
            elif spec.extra_ram_mb > 0 and spec.extra_ram_mb > budget - dec.est_ram_mb and not spec.critical:
                dec.skipped[n] = "insufficient RAM"
            elif (cpu > self.cfg.cpu_busy_percent and not spec.critical and not spec.resident
                  and spec.est_latency_ms >= self.cfg.heavy_latency_ms):
                dec.skipped[n] = f"CPU busy ({cpu:.0f}% > {self.cfg.cpu_busy_percent:.0f}%)"
            else:
                dec.selected.append(n)
                dec.est_latency_ms += spec.est_latency_ms
                dec.est_ram_mb += spec.extra_ram_mb
        return dec

    # 8-10: executed by the controller, which reports back here
    def report(self, outcomes: dict[str, bool]) -> None:
        for n, ok in outcomes.items():
            self.stats.update(n, ok)


def always_all(registry: ModuleRegistry) -> RoutingDecision:
    """Baseline for the NFD experiment: fixed pipeline that activates every available module."""
    dec = RoutingDecision(selected=[])
    for n in registry.names():
        spec = registry.get(n)
        if spec.available:
            dec.selected.append(n)
            dec.est_latency_ms += spec.est_latency_ms
            dec.est_ram_mb += spec.est_ram_mb
    return dec
