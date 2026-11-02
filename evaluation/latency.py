"""Latency / RAM / CPU measurement (spec 16.3)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return float("nan")
    v = sorted(values)
    k = (len(v) - 1) * p / 100.0
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / 1e6 if psutil else float("nan")


@dataclass
class LatencyRecorder:
    samples_ms: list[float] = field(default_factory=list)
    peak_rss_mb: float = 0.0
    _cpu0: float = 0.0
    _wall0: float = 0.0

    def start(self) -> None:
        self._cpu0, self._wall0 = time.process_time(), time.perf_counter()

    def record(self, ms: float) -> None:
        self.samples_ms.append(ms)
        self.peak_rss_mb = max(self.peak_rss_mb, rss_mb())

    def time(self, fn, *a, **k):
        s = time.perf_counter()
        out = fn(*a, **k)
        self.record((time.perf_counter() - s) * 1000)
        return out

    def summary(self) -> dict:
        wall = time.perf_counter() - self._wall0 if self._wall0 else float("nan")
        cpu = time.process_time() - self._cpu0 if self._cpu0 else float("nan")
        return {"n": len(self.samples_ms), "p50_ms": percentile(self.samples_ms, 50),
                "p95_ms": percentile(self.samples_ms, 95), "mean_ms": sum(self.samples_ms) / max(1, len(self.samples_ms)),
                "peak_rss_mb": self.peak_rss_mb, "cpu_s": cpu, "wall_s": wall,
                "cpu_utilisation": cpu / wall if wall and wall == wall else float("nan")}
