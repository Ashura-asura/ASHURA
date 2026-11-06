"""F-045: durable jobs, restart recovery and hard timeout for the learning worker."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from learning.jobs import SQLiteJobStore
from learning.runtime import build_learning_worker
from learning.worker import LearningWorker


def _echo(correction, trace):
    return {"correction": correction, "trace": trace}


def _slow_or_fast(correction, trace):
    if correction == "slow":
        time.sleep(30)
    return correction


class CountingRunner:
    """Picklable stateful callable: the child's updated instance must return to the parent."""

    def __init__(self):
        self.calls = 0

    def __call__(self, correction, trace):
        self.calls += 1
        return self.calls


def test_durable_store_survives_worker_restart(tmp_path):
    path = str(tmp_path / "jobs.db")
    store = SQLiteJobStore(path)
    worker = LearningWorker(_echo, store=store, poll_s=0.005)
    queued = worker.submit("c", "t")
    record = worker.wait(queued.job_id, timeout=5)
    assert record["status"] == "done"
    assert record["result"] == {"correction": "c", "trace": "t"}
    assert worker.close(timeout=5)

    reopened = SQLiteJobStore(path)
    try:
        persisted = reopened.get(queued.job_id)
        assert persisted["status"] == "done" and persisted["attempts"] == 1
        assert persisted["result"]["correction"] == "c"
    finally:
        reopened.close()


def test_recovery_reschedules_queued_and_interrupts_running_jobs(tmp_path):
    path = str(tmp_path / "jobs.db")
    store = SQLiteJobStore(path)
    store.create("queued1", "c", "t")
    store.create("running1", "c", "t")
    assert store.mark_running("running1")
    store.close()

    store = SQLiteJobStore(path)
    worker = LearningWorker(_echo, store=store, poll_s=0.005)
    try:
        assert worker.interrupted == ["running1"]
        assert worker.recovered == 1
        assert worker.wait("queued1", timeout=5)["status"] == "done"
        interrupted = worker.status("running1")
        assert interrupted["status"] == "error"
        assert "interrupted by process restart" in interrupted["error"]
    finally:
        assert worker.close(timeout=5)


def test_a_real_process_crash_is_recovered_as_interrupted(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    db = tmp_path / "crash.db"
    ready = tmp_path / "ready.txt"
    script = """
import sys, time
from pathlib import Path
from learning.jobs import SQLiteJobStore
from learning.worker import LearningWorker

store = SQLiteJobStore(sys.argv[1])
worker = LearningWorker(lambda correction, trace: time.sleep(60), store=store, poll_s=0.01)
job = worker.submit("block", "trace")
Path(sys.argv[2]).write_text(job.job_id, encoding="utf-8")
time.sleep(60)
"""
    proc = subprocess.Popen([sys.executable, "-c", script, str(db), str(ready)],
                            cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            if proc.poll() is not None:
                raise AssertionError(f"worker child exited early: {proc.stderr.read()}")
            time.sleep(0.02)
        assert ready.exists(), "worker child did not report its job id"
        job_id = ready.read_text(encoding="utf-8").strip()

        store = SQLiteJobStore(str(db))
        try:
            deadline = time.monotonic() + 10
            status = None
            while time.monotonic() < deadline:
                record = store.get(job_id)
                status = record["status"] if record else None
                if status == "running":
                    break
                time.sleep(0.02)
            assert status == "running", f"job never started (status={status})"
        finally:
            store.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    store = SQLiteJobStore(str(db))
    worker = LearningWorker(_echo, store=store, poll_s=0.005)
    try:
        assert job_id in worker.interrupted
        record = worker.status(job_id)
        assert record["status"] == "error"
        assert "interrupted by process restart" in record["error"]
    finally:
        assert worker.close(timeout=5)


def test_hard_timeout_terminates_a_job_and_the_worker_continues():
    # 5 s, not 1 s: spawning a child can take over a second on a loaded Windows host,
    # which would make the *next* fast job look like a timeout.
    worker = LearningWorker(_slow_or_fast, hard_timeout_s=5.0, poll_s=0.005)
    try:
        started = time.monotonic()
        slow = worker.submit("slow", "t")
        record = worker.wait(slow.job_id, timeout=15)
        assert record["status"] == "timeout"
        assert time.monotonic() - started < 15
        assert worker.thread_alive

        fast = worker.submit("fast", "t")
        fast_record = worker.wait(fast.job_id, timeout=15)
        assert fast_record["status"] == "done" and fast_record["result"] == "fast"
    finally:
        assert worker.close(timeout=5)


def test_hard_timeout_returns_stateful_runner_updates_to_the_parent():
    runner = CountingRunner()
    worker = LearningWorker(runner, hard_timeout_s=10.0, poll_s=0.005)
    try:
        first = worker.submit("c", "t")
        assert worker.wait(first.job_id, timeout=15)["result"] == 1
        second = worker.submit("c", "t")
        assert worker.wait(second.job_id, timeout=15)["result"] == 2
        assert worker._run_fn.calls == 2
    finally:
        assert worker.close(timeout=5)


def _write_replay(tmp_path: Path) -> Path:
    path = tmp_path / "replay.jsonl"
    records = [
        {"id": f"old-{i}", "key": f"entity{i} old", "value": f"old-{i}",
         "category": "old", "verified": True}
        for i in range(4)
    ] + [{"id": "target-h", "key": "wording", "value": "42",
          "category": "corrected", "verified": True, "split": "heldout"}]
    path.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    return path


def test_learning_runtime_is_disabled_by_default():
    assert build_learning_worker(None) is None
    assert build_learning_worker({"enabled": False}) is None


def test_learning_runtime_requires_a_replay_corpus():
    with pytest.raises(ValueError, match="replay_path"):
        build_learning_worker({"enabled": True})


def test_learning_runtime_builds_from_a_minimal_corpus(tmp_path):
    worker = build_learning_worker({
        "enabled": True,
        "replay_path": str(_write_replay(tmp_path)),
        "jobs_db": str(tmp_path / "jobs.db"),
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "initialization": "fresh",
        "min_train": 1,
    })
    assert worker is not None
    assert worker.close(timeout=5)


def test_learning_runtime_refuses_stable_without_a_checkpoint(tmp_path):
    with pytest.raises(ValueError, match="no stable checkpoint"):
        build_learning_worker({
            "enabled": True,
            "replay_path": str(_write_replay(tmp_path)),
            "jobs_db": str(tmp_path / "jobs.db"),
            "checkpoint_dir": str(tmp_path / "checkpoints"),
        })


def test_store_claims_a_queued_job_only_once(tmp_path):
    path = str(tmp_path / "jobs.db")
    first, second = SQLiteJobStore(path), SQLiteJobStore(path)
    try:
        first.create("job", "c", "t")
        assert first.mark_running("job") is True
        assert second.mark_running("job") is False
    finally:
        first.close()
        second.close()
