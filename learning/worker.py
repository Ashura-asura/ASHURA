"""Opt-in background learning worker (F-041 residual, P67).

The response path must not block on candidate training. `LearningWorker` owns a single daemon
thread and a bounded queue; it serialises learning jobs and records their status. It is deliberately
small:

* `submit()` never raises and returns a `QueuedResult` immediately;
* a job can be cancelled only while it is still queued (Python cannot safely kill a running thread);
* `wait()`/`join()` expose completion, but ``timeout`` never interrupts a running job;
* the worker is opt-in: the default CLI still does not configure a replay corpus or checkpoint.

    worker = LearningWorker(run_verified_correction_partial)
    controller = Controller(..., correction_loop=worker)
    ...
    worker.wait(job_id, timeout=30)
    worker.stop()
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class QueuedResult:
    """Hook-shaped acknowledgement returned to the controller."""
    job_id: str
    stage: str
    promoted: bool = False
    reasons: tuple[str, ...] = ()


@dataclass
class JobRecord:
    id: str
    status: str = "queued"                 # queued | running | done | error | cancelled
    submitted: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    result: Any = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {"job_id": self.id, "status": self.status, "submitted": self.submitted,
                "started": self.started, "finished": self.finished,
                "result": self.result, "error": self.error}


class LearningWorker:
    """Bounded, single-threaded background runner for learning jobs."""

    def __init__(self, run_fn: Callable[[Any, Any], Any], *, max_queue: int = 8,
                 name: str = "ashura-learning", poll_s: float = 0.02):
        if max_queue < 1:
            raise ValueError("max_queue must be positive")
        self._run_fn = run_fn
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._poll_s = poll_s
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()

    # ---- submission / observation -----------------------------------------------------------
    def submit(self, correction: Any, trace: Any) -> QueuedResult:
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            if self._stop.is_set():
                return QueuedResult("", "refused_stopped", False,
                                    ("learning worker is stopping; correction was not scheduled",))
            self._jobs[job_id] = JobRecord(job_id)
        try:
            self._queue.put_nowait((job_id, correction, trace))
        except queue.Full:
            with self._lock:
                self._jobs.pop(job_id, None)
            return QueuedResult("", "refused_queue_full", False,
                                ("learning queue is full; correction was not scheduled",))
        return QueuedResult(job_id, "queued", False, ("queued for background learning",))

    def __call__(self, correction: Any, trace: Any) -> QueuedResult:
        """Controller `correction_loop` adapter."""
        return self.submit(correction, trace)

    def status(self, job_id: str) -> dict | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def wait(self, job_id: str, timeout: float | None = None) -> dict | None:
        """Wait for a job, or return its current record when the timeout expires."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return None
                if job.status in {"done", "error", "cancelled"}:
                    return job.as_dict()
                snapshot = job.as_dict()
            if deadline is not None and time.monotonic() >= deadline:
                return snapshot
            time.sleep(self._poll_s)

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job. A running job cannot be cancelled safely and returns False."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return False
            job.status = "cancelled"
            job.finished = time.time()
            return True

    def active(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status in {"queued", "running"})

    def join(self, timeout: float | None = None) -> bool:
        """Wait until no job is queued/running. Returns True if drained, False on timeout."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while self.active():
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(self._poll_s)
        return True

    # ---- lifecycle --------------------------------------------------------------------------
    def stop(self, timeout: float | None = None) -> bool:
        """Stop accepting work after draining queued jobs. Returns False if the thread is stuck."""
        self._stop.set()
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def __enter__(self) -> "LearningWorker":
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    @property
    def thread_alive(self) -> bool:
        return self._thread.is_alive()

    # ---- worker -----------------------------------------------------------------------------
    def _loop(self) -> None:
        while not (self._stop.is_set() and self._queue.empty()):
            try:
                job_id, correction, trace = self._queue.get(timeout=self._poll_s)
            except queue.Empty:
                continue
            try:
                with self._lock:
                    job = self._jobs.get(job_id)
                    if job is None or job.status == "cancelled":
                        continue
                    job.status = "running"
                    job.started = time.time()
                try:
                    result = self._run_fn(correction, trace)
                    with self._lock:
                        job.status = "done"
                        job.result = result
                except Exception as e:  # noqa: BLE001 - one bad job must not kill the worker
                    with self._lock:
                        job.status = "error"
                        job.error = f"{type(e).__name__}: {e}"
                finally:
                    with self._lock:
                        job.finished = time.time()
            finally:
                self._queue.task_done()
