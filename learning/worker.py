"""Opt-in background learning worker (F-041 residual, P67, F-045).

The response path must not block on candidate training. `LearningWorker` owns a single daemon
thread and a bounded queue; it serialises learning jobs and records their status.

Durability and termination are explicit:

* with a `SQLiteJobStore`, jobs and results survive a process exit; queued jobs are re-scheduled on
  the next start and previously running jobs are marked interrupted rather than replayed;
* `hard_timeout_s` runs each job in a spawned child process and terminates it at the deadline;
  the callable must be picklable. If it carries state, the child returns its post-job object and
  the parent adopts it, so a stateful runner does not lose updates between jobs;
* without a store or a hard timeout the worker is the original in-process, non-durable runner.

The worker remains opt-in: the default CLI does not configure a replay corpus or checkpoint.

    worker = LearningWorker(run_verified_correction_partial)
    controller = Controller(..., correction_loop=worker)
    ...
    worker.wait(job_id, timeout=30)
    worker.close()
"""
from __future__ import annotations

import multiprocessing
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from learning.jobs import TERMINAL, SQLiteJobStore


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
    status: str = "queued"                 # queued | running | done | error | cancelled | timeout
    submitted: float = field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    attempts: int = 0
    result: Any = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {"job_id": self.id, "status": self.status, "submitted": self.submitted,
                "started": self.started, "finished": self.finished, "attempts": self.attempts,
                "result": self.result, "error": self.error}


def _child_entry(run_fn: Callable[[Any, Any], Any], correction: Any, trace: Any, conn) -> None:
    """Spawn target: run one job and send (status, payload, post-job callable) to the parent."""
    try:
        result = run_fn(correction, trace)
        conn.send(("done", result, run_fn))
    except BaseException as e:  # noqa: BLE001 - the child must report, not traceback silently
        try:
            conn.send(("error", f"{type(e).__name__}: {e}", None))
        except BaseException:  # noqa: BLE001 - the parent will report the missing result
            pass
    finally:
        conn.close()


def _run_in_child(run_fn: Callable[[Any, Any], Any], correction: Any, trace: Any,
                  timeout_s: float) -> tuple[str, Any, Callable | None]:
    """Run one job in a spawned process and hard-terminate it at the deadline."""
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_entry, args=(run_fn, correction, trace, child), daemon=True)
    try:
        proc.start()
    except BaseException:
        parent.close()
        child.close()
        raise
    child.close()

    message: tuple[str, Any, Callable | None] | None = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if parent.poll(0.05):
            try:
                message = parent.recv()
            except EOFError:
                message = None
            break
        if not proc.is_alive():
            if parent.poll(0.1):
                try:
                    message = parent.recv()
                except EOFError:
                    message = None
            break

    if message is None:
        if proc.is_alive():
            proc.terminate()
            proc.join(5)
            if proc.is_alive():
                proc.kill()
                proc.join(5)
            parent.close()
            return "timeout", None, None
        exitcode = proc.exitcode
        parent.close()
        return "error", f"child exited with code {exitcode} without a result", None

    proc.join(5)
    if proc.is_alive():
        proc.terminate()
        proc.join(5)
        if proc.is_alive():
            proc.kill()
            proc.join(5)
    parent.close()
    return message


class LearningWorker:
    """Bounded, single-threaded background runner for learning jobs."""

    def __init__(self, run_fn: Callable[[Any, Any], Any], *, max_queue: int = 8,
                 name: str = "ashura-learning", poll_s: float = 0.02,
                 store: SQLiteJobStore | None = None, hard_timeout_s: float | None = None):
        if max_queue < 1:
            raise ValueError("max_queue must be positive")
        if poll_s <= 0:
            raise ValueError("poll_s must be positive")
        if hard_timeout_s is not None and hard_timeout_s <= 0:
            raise ValueError("hard_timeout_s must be positive or None")
        self._run_fn = run_fn
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue)
        self._jobs: dict[str, JobRecord] = {}
        self._payloads: dict[str, tuple[Any, Any]] = {}
        self._scheduled: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._drain = True
        self._poll_s = poll_s
        self._store = store
        self._hard_timeout_s = hard_timeout_s
        self.interrupted: list[str] = []
        self.recovered = 0

        if store is not None:
            self.interrupted = store.recover_running()
            self.recovered = len(store.queued_ids())
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)
        self._thread.start()
        self._schedule_from_store()

    # ---- submission / observation -----------------------------------------------------------
    def submit(self, correction: Any, trace: Any) -> QueuedResult:
        job_id = uuid.uuid4().hex[:12]
        if self._stop.is_set():
            return QueuedResult("", "refused_stopped", False,
                                ("learning worker is stopping; correction was not scheduled",))
        if self._store is not None:
            try:
                self._store.create(job_id, correction, trace)
            except Exception as e:  # noqa: BLE001 - submit must never raise into the answer path
                return QueuedResult("", "refused_store", False,
                                    (f"could not persist learning job: {type(e).__name__}: {e}",))
        else:
            with self._lock:
                self._jobs[job_id] = JobRecord(job_id)
                self._payloads[job_id] = (correction, trace)
        try:
            with self._lock:
                self._scheduled.add(job_id)
                self._queue.put_nowait(job_id)
        except queue.Full:
            with self._lock:
                self._scheduled.discard(job_id)
                self._payloads.pop(job_id, None)
                self._jobs.pop(job_id, None)
            if self._store is not None:
                self._store.mark_cancelled(job_id, "learning queue was full")
            return QueuedResult("", "refused_queue_full", False,
                                ("learning queue is full; correction was not scheduled",))
        return QueuedResult(job_id, "queued", False, ("queued for background learning",))

    def __call__(self, correction: Any, trace: Any) -> QueuedResult:
        """Controller `correction_loop` adapter."""
        return self.submit(correction, trace)

    def status(self, job_id: str) -> dict | None:
        if self._store is not None:
            return self._store.get(job_id)
        with self._lock:
            job = self._jobs.get(job_id)
            return job.as_dict() if job else None

    def wait(self, job_id: str, timeout: float | None = None) -> dict | None:
        """Wait for a job, or return its current record when the timeout expires."""
        deadline = time.monotonic() + timeout if timeout is not None else None
        while True:
            snapshot = self.status(job_id)
            if snapshot is None:
                return None
            if snapshot["status"] in TERMINAL:
                return snapshot
            if deadline is not None and time.monotonic() >= deadline:
                return snapshot
            time.sleep(self._poll_s)

    def cancel(self, job_id: str) -> bool:
        """Cancel a queued job. A running job cannot be cancelled safely and returns False."""
        if self._store is not None:
            cancelled = self._store.mark_cancelled(job_id)
            if cancelled:
                with self._lock:
                    self._scheduled.discard(job_id)
            return cancelled
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status != "queued":
                return False
            job.status = "cancelled"
            job.finished = time.time()
            self._scheduled.discard(job_id)
            self._payloads.pop(job_id, None)
            return True

    def active(self) -> int:
        if self._store is not None:
            return self._store.active()
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
    def stop(self, timeout: float | None = None, *, drain: bool = True) -> bool:
        """Stop accepting work. With drain=True queued jobs are completed first.

        A running job is never killed here; use `hard_timeout_s` for a termination policy.
        Returns False if the worker thread is still alive when the timeout expires.
        """
        with self._lock:
            self._drain = drain
        self._stop.set()
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def close(self, timeout: float | None = None, *, drain: bool = True) -> bool:
        """Stop the worker and close an owned job store once its thread has exited."""
        stopped = self.stop(timeout, drain=drain)
        if stopped and self._store is not None:
            self._store.close()
        return stopped

    def __enter__(self) -> "LearningWorker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def thread_alive(self) -> bool:
        return self._thread.is_alive()

    # ---- worker -----------------------------------------------------------------------------
    def _schedule_from_store(self) -> None:
        if self._store is None:
            return
        with self._lock:
            for job_id in self._store.queued_ids(exclude=self._scheduled):
                try:
                    self._queue.put_nowait(job_id)
                except queue.Full:
                    break
                self._scheduled.add(job_id)

    def _loop(self) -> None:
        while True:
            with self._lock:
                stopping = self._stop.is_set()
                drain = self._drain
            if stopping and not drain:
                break
            if stopping and self._queue.empty() and not (self._store and self._store.has_queued()):
                break
            try:
                job_id = self._queue.get(timeout=self._poll_s)
            except queue.Empty:
                self._schedule_from_store()
                continue
            try:
                self._execute(job_id)
            finally:
                self._queue.task_done()
                with self._lock:
                    self._scheduled.discard(job_id)
                self._schedule_from_store()

    def _execute(self, job_id: str) -> None:
        if self._store is not None:
            if not self._store.mark_running(job_id):
                return                                  # cancelled or claimed by another worker
            payload = self._store.payload(job_id)
        else:
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None or job.status != "queued":
                    return
                job.status = "running"
                job.started = time.time()
                job.attempts += 1
            payload = self._payloads.get(job_id)
        if payload is None:
            self._finish(job_id, "error", error="job payload is missing or unreadable")
            return

        correction, trace = payload
        status, value = "done", None
        try:
            if self._hard_timeout_s is not None:
                status, value, runner = _run_in_child(self._run_fn, correction, trace,
                                                      self._hard_timeout_s)
                if status == "done" and runner is not None:
                    self._run_fn = runner                    # keep stateful runner updates
            else:
                value = self._run_fn(correction, trace)
        except Exception as e:  # noqa: BLE001 - one bad job must not kill the worker
            status, value = "error", f"{type(e).__name__}: {e}"

        if status == "done":
            self._finish(job_id, "done", result=value)
        elif status == "timeout":
            self._finish(job_id, "timeout", error=str(value or "job exceeded its hard timeout"))
        else:
            self._finish(job_id, "error", error=str(value))

    def _finish(self, job_id: str, status: str, *, result: Any = None,
                error: str | None = None) -> None:
        if self._store is not None:
            if status == "done":
                self._store.mark_done(job_id, result)
            elif status == "timeout":
                self._store.mark_timeout(job_id, error or "job exceeded its hard timeout")
            else:
                self._store.mark_error(job_id, error or "unknown error")
            return
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = status
            job.finished = time.time()
            job.result = result
            job.error = error
            self._payloads.pop(job_id, None)
