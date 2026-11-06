"""Single-writer controller worker for the local web UI.

The Controller owns one SQLite connection and one local model. Neither is safe to use from several
HTTP threads at once, so every controller operation is executed by one background thread. HTTP
handlers submit a job and either wait for the result or consume streamed token events.

The queue is deliberately bounded. When the bound is reached the caller gets
:class:`WorkerQueueFull` and the HTTP layer answers 429 rather than growing an unbounded backlog.

A job is a small handle with:

* ``events`` - ``("token", str)`` while streaming, then exactly one terminal event:
  ``("done", result)``, ``("error", {"error": str})`` or ``("cancelled", {"reason": str})``.
* ``wait(timeout)`` - blocking result for non-streaming callers.
* ``cancel()`` - cooperative cancellation, honoured by the token callback. The controller raises
  :class:`~foundation.language_model.GenerationCancelled` inside the model stream, so a stopped
  response is not persisted by the caller.
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from typing import Any, Callable

from foundation.language_model import GenerationCancelled


class WorkerStopped(RuntimeError):
    """The worker is shutting down and no longer accepts jobs."""


class WorkerQueueFull(RuntimeError):
    """The bounded job queue is full. The HTTP layer maps this to 429."""


TokenCallback = Callable[[str], None]


class Job:
    """A unit of work submitted to :class:`ControllerWorker`."""

    def __init__(self, kind: str, fn: Callable[[TokenCallback], Any], *,
                 cancel_event: threading.Event | None = None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.fn = fn
        self.cancel_event = cancel_event or threading.Event()
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.done = threading.Event()
        self.status = "queued"          # queued | running | done | error | cancelled
        self.result: Any = None
        self.error: BaseException | None = None
        self.enqueued = time.monotonic()
        self.started: float | None = None
        self.finished: float | None = None
        self.queue_position = 0
        self._terminal = False

    def cancel(self) -> None:
        self.cancel_event.set()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def emit(self, text: str) -> None:
        """Token callback passed to the controller. Raises when the client has gone away."""
        if not text:
            return
        if self.cancel_event.is_set():
            raise GenerationCancelled()
        self.events.put(("token", text))

    def _finish(self, status: str, *, result: Any = None, error: BaseException | None = None,
                reason: str | None = None) -> None:
        self.status = status
        self.result = result
        self.error = error
        self.finished = time.monotonic()
        self._terminal = True
        if status == "done":
            self.events.put(("done", result))
        elif status == "error":
            self.events.put(("error", {"error": f"{type(error).__name__}: {error}"}))
        else:
            self.events.put(("cancelled", {"reason": reason or "cancelled"}))
        self.done.set()

    def wait(self, timeout: float | None = None) -> Any:
        if not self.done.wait(timeout):
            raise TimeoutError(f"job {self.id} did not finish within {timeout}s")
        if self.error is not None:
            raise self.error
        if self.status == "cancelled":
            raise RuntimeError("job was cancelled")
        return self.result


class ControllerWorker:
    """Serialize every access to one Controller through a bounded queue."""

    def __init__(self, controller: Any, max_queue: int = 8, name: str = "ashura-controller"):
        self.controller = controller
        self.max_queue = max(1, int(max_queue))
        self._queue: queue.Queue[Job | None] = queue.Queue(maxsize=self.max_queue)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._active: Job | None = None
        self._counters = {
            "submitted": 0, "completed": 0, "failed": 0, "cancelled": 0, "rejected": 0,
            "total_wait_s": 0.0, "total_run_s": 0.0,
        }
        self._last: dict[str, Any] = {}
        self._thread.start()

    # ---- submission -------------------------------------------------------------------------
    def submit(self, fn: Callable[[TokenCallback], Any], kind: str = "task", *,
               cancel_event: threading.Event | None = None) -> Job:
        if self._stop.is_set():
            raise WorkerStopped("controller worker is stopping")
        job = Job(kind, fn, cancel_event=cancel_event)
        with self._lock:
            if self._stop.is_set():
                raise WorkerStopped("controller worker is stopping")
            try:
                self._queue.put_nowait(job)
            except queue.Full:
                self._counters["rejected"] += 1
                raise WorkerQueueFull(
                    f"worker queue is full ({self.max_queue} jobs); try again") from None
            job.queue_position = self._queue.qsize()
            self._counters["submitted"] += 1
        return job

    # ---- worker loop ------------------------------------------------------------------------
    def _run(self) -> None:
        while True:
            try:
                job = self._queue.get(timeout=0.25)
            except queue.Empty:
                if self._stop.is_set():
                    return
                continue
            if job is None:
                self._queue.task_done()
                return
            try:
                if self._stop.is_set() or job.cancelled:
                    self._finish_cancelled(job, "worker stopping" if self._stop.is_set() else "cancelled")
                else:
                    self._execute(job)
            finally:
                self._queue.task_done()
                if self._stop.is_set() and self._queue.empty():
                    return

    def _execute(self, job: Job) -> None:
        job.status = "running"
        job.started = time.monotonic()
        with self._lock:
            self._active = job
        try:
            result = job.fn(job.emit)
        except Exception as error:  # noqa: BLE001 - job failure is reported, never raised in the thread
            if isinstance(error, GenerationCancelled) or job.cancelled:
                self._finish_cancelled(job, "client cancelled")
            else:
                job._finish("error", error=error)
                self._account(job, failed=True)
        else:
            if job.cancelled:
                self._finish_cancelled(job, "client cancelled")
            else:
                job._finish("done", result=result)
                self._account(job, completed=True)
        finally:
            with self._lock:
                self._active = None

    def _finish_cancelled(self, job: Job, reason: str) -> None:
        job._finish("cancelled", reason=reason)
        self._account(job, cancelled=True)

    def _account(self, job: Job, *, completed: bool = False, failed: bool = False,
                 cancelled: bool = False) -> None:
        now = time.monotonic()
        wait = (job.started or now) - job.enqueued
        run = (job.finished or now) - (job.started or now)
        with self._lock:
            self._counters["total_wait_s"] += max(0.0, wait)
            self._counters["total_run_s"] += max(0.0, run)
            if completed:
                self._counters["completed"] += 1
            if failed:
                self._counters["failed"] += 1
            if cancelled:
                self._counters["cancelled"] += 1
            self._last = {
                "id": job.id, "kind": job.kind, "status": job.status,
                "wait_ms": round(wait * 1000, 1), "run_ms": round(run * 1000, 1),
                "error": f"{type(job.error).__name__}: {job.error}" if job.error else None,
            }

    # ---- introspection / shutdown ------------------------------------------------------------
    def stats(self) -> dict:
        with self._lock:
            counters = dict(self._counters)
            active = self._active
            last = dict(self._last)
        submitted = counters["submitted"]
        finished = counters["completed"] + counters["failed"] + counters["cancelled"]
        return {
            "queue_depth": self._queue.qsize(),
            "max_queue": self.max_queue,
            "active": active.kind if active is not None else None,
            "active_id": active.id if active is not None else None,
            "submitted": submitted,
            "completed": counters["completed"],
            "failed": counters["failed"],
            "cancelled": counters["cancelled"],
            "rejected": counters["rejected"],
            "avg_wait_ms": round(counters["total_wait_s"] * 1000 / max(1, finished), 1),
            "avg_run_ms": round(counters["total_run_s"] * 1000 / max(1, finished), 1),
            "last": last or None,
            "alive": self._thread.is_alive(),
        }

    def stop(self, timeout: float = 10.0) -> bool:
        """Cancel queued work and ask the worker to exit. Returns True when the thread stopped."""
        self._stop.set()
        while True:
            try:
                job = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                if job is not None:
                    self._finish_cancelled(job, "worker stopping")
            finally:
                self._queue.task_done()
        with self._lock:
            active = self._active
        if active is not None:
            active.cancel()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def close(self, timeout: float = 10.0) -> bool:
        return self.stop(timeout)

    def __enter__(self) -> "ControllerWorker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
