"""Bounded in-process concurrency for local model calls (F-047).

The Ollama server owns the real parallel slots (`OLLAMA_NUM_PARALLEL`). This gate is the client-side
policy: it caps how many requests one ASHURA process sends at once, bounds the waiting room, and
fails a request instead of letting an unbounded queue grow. It does not create server parallelism.

The default (`max_inflight=0`) is unlimited, preserving the behaviour of every existing caller. The
shipped Ollama profiles set `max_inflight = 1` to match the target laptop's measured server default.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field


class QueueFullError(RuntimeError):
    """The waiting room is full; the caller should shed or retry the request."""


class QueueTimeoutError(TimeoutError):
    """The request waited longer than `queue_timeout_s` for a slot."""


@dataclass
class GateSnapshot:
    max_inflight: int
    max_queue: int
    queue_timeout_s: float
    in_flight: int = 0
    queued: int = 0
    max_in_flight_seen: int = 0
    served: int = 0
    rejected_full: int = 0
    rejected_timeout: int = 0
    wait_ms_total: float = 0.0
    wait_ms_max: float = 0.0
    wait_samples: int = 0


@dataclass
class _GateState:
    in_flight: int = 0
    queued: int = 0
    max_in_flight_seen: int = 0
    served: int = 0
    rejected_full: int = 0
    rejected_timeout: int = 0
    wait_ms_total: float = 0.0
    wait_ms_max: float = 0.0
    wait_samples: int = 0


class ConcurrencyGate:
    """A bounded, timeout-aware semaphore with observable queue statistics."""

    def __init__(self, max_inflight: int = 1, max_queue: int = 8,
                 queue_timeout_s: float = 60.0) -> None:
        if max_inflight < 1:
            raise ValueError("max_inflight must be >= 1; use no gate for unlimited concurrency")
        if max_queue < 0:
            raise ValueError("max_queue must be >= 0")
        if queue_timeout_s <= 0:
            raise ValueError("queue_timeout_s must be positive")
        self.max_inflight = int(max_inflight)
        self.max_queue = int(max_queue)
        self.queue_timeout_s = float(queue_timeout_s)
        self._sem = threading.BoundedSemaphore(self.max_inflight)
        self._lock = threading.Lock()
        self._state = _GateState()

    def _enter(self, started: float) -> None:
        wait_ms = (time.perf_counter() - started) * 1000.0
        with self._lock:
            self._state.in_flight += 1
            self._state.served += 1
            self._state.max_in_flight_seen = max(self._state.max_in_flight_seen,
                                                 self._state.in_flight)
            self._state.wait_ms_total += wait_ms
            self._state.wait_ms_max = max(self._state.wait_ms_max, wait_ms)
            self._state.wait_samples += 1

    def acquire(self) -> None:
        """Take one slot, waiting up to `queue_timeout_s` if the waiting room is not full."""
        started = time.perf_counter()
        if self._sem.acquire(blocking=False):
            self._enter(started)
            return
        with self._lock:
            if self._state.queued >= self.max_queue:
                self._state.rejected_full += 1
                raise QueueFullError(
                    f"inference queue is full ({self.max_queue} waiting, "
                    f"{self._state.in_flight} in flight)")
            self._state.queued += 1
        try:
            acquired = self._sem.acquire(timeout=self.queue_timeout_s)
        finally:
            with self._lock:
                self._state.queued -= 1
        if not acquired:
            with self._lock:
                self._state.rejected_timeout += 1
            raise QueueTimeoutError(
                f"no inference slot within {self.queue_timeout_s:g} s "
                f"({self.max_inflight} slots, {self.max_queue} waiting)")
        self._enter(started)

    def release(self) -> None:
        with self._lock:
            if self._state.in_flight <= 0:
                raise RuntimeError("release() called without a matching acquire()")
            self._state.in_flight -= 1
        self._sem.release()

    @contextmanager
    def slot(self):
        self.acquire()
        try:
            yield
        finally:
            self.release()

    def run(self, fn, *args, **kwargs):
        with self.slot():
            return fn(*args, **kwargs)

    def snapshot(self) -> GateSnapshot:
        with self._lock:
            s = self._state
            return GateSnapshot(
                max_inflight=self.max_inflight,
                max_queue=self.max_queue,
                queue_timeout_s=self.queue_timeout_s,
                in_flight=s.in_flight,
                queued=s.queued,
                max_in_flight_seen=s.max_in_flight_seen,
                served=s.served,
                rejected_full=s.rejected_full,
                rejected_timeout=s.rejected_timeout,
                wait_ms_total=s.wait_ms_total,
                wait_ms_max=s.wait_ms_max,
                wait_samples=s.wait_samples,
            )
