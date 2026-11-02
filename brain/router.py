"""Module registry + resource-aware selection (spec 7, 16.2)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


@dataclass
class ModuleSpec:
    name: str
    est_latency_ms: float
    est_ram_mb: float
    available: bool = True           # False = not implemented / not installed yet
    critical: bool = False
    resident: bool = False           # already loaded in RAM -> no additional RAM needed
    fn: Callable | None = None

    @property
    def cost(self) -> float:
        """Normalised execution cost K in [0,1]. Reference scales are experimental."""
        return min(1.0, 0.5 * self.est_latency_ms / 5000.0 + 0.5 * self.est_ram_mb / 4000.0)

    @property
    def extra_ram_mb(self) -> float:
        return 0.0 if self.resident else self.est_ram_mb


class ModuleRegistry:
    def __init__(self):
        self._m: dict[str, ModuleSpec] = {}

    def register(self, spec: ModuleSpec) -> None:
        self._m[spec.name] = spec

    def get(self, name: str) -> ModuleSpec:
        return self._m[name]

    def names(self) -> list[str]:
        return list(self._m)

    def __contains__(self, name: str) -> bool:
        return name in self._m


def available_ram_mb() -> float:
    return psutil.virtual_memory().available / 1e6 if psutil else 1e9


if psutil:
    psutil.cpu_percent(interval=None)       # prime: the first call has no previous sample to compare with


def cpu_busy_percent() -> float:
    """System-wide CPU utilisation since the previous call (0-100). 0.0 if psutil is unavailable."""
    return psutil.cpu_percent(interval=None) if psutil else 0.0


@dataclass
class RoutingDecision:
    selected: list[str]
    skipped: dict[str, str] = field(default_factory=dict)       # module -> reason
    priorities: dict[str, float] = field(default_factory=dict)
    est_latency_ms: float = 0.0
    est_ram_mb: float = 0.0
