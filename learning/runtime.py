"""Configuration and CLI wiring for durable learning jobs (F-045).

The worker is opt-in. `[learning].enabled = true` requires a JSONL replay corpus and a checkpoint
directory; a missing or inconsistent corpus fails at startup instead of letting every background
job fail silently.

`LoopRunner` is a picklable callable so `hard_timeout_s` can run it in a spawned child process. Its
NGR policy is constructed per call because `MappingProxyType` is not picklable.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from evaluation.ngr import NGRPolicy
from learning.cage import CAGE
from learning.dream import DreamConfig
from learning.jobs import SQLiteJobStore
from learning.loop import run_verified_correction
from learning.replay import ReplayBuffer, ReplayItem
from learning.worker import LearningWorker
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore


@dataclass
class LoopRunner:
    """Picklable end-to-end correction runner used by the durable worker."""
    buffer: ReplayBuffer
    store: CheckpointStore
    cfg: DreamConfig
    min_target_gain: float = 0.05
    fast: FastWeights = field(default_factory=FastWeights)

    def __call__(self, correction, trace):
        return run_verified_correction(
            correction, trace, cage=CAGE(), updater=GatedUpdater(self.fast),
            buffer=self.buffer, store=self.store,
            policy=NGRPolicy(self.cfg.target, min_target_gain=self.min_target_gain),
            cfg=self.cfg,
        )


def load_replay(path: str | Path) -> ReplayBuffer:
    """Load a JSONL replay corpus. Every record must be a valid `ReplayItem`."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"learning replay corpus not found: {source}")
    buffer = ReplayBuffer()
    for lineno, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            item = ReplayItem(**record)
        except (ValueError, TypeError) as e:
            raise ValueError(f"{source}:{lineno}: invalid replay item: {e}") from e
        try:
            buffer.add(item)
        except ValueError as e:
            raise ValueError(f"{source}:{lineno}: {e}") from e
    return buffer


def build_learning_worker(section: dict | None) -> LearningWorker | None:
    """Build the opt-in worker, or return None when `[learning].enabled` is false."""
    section = section or {}
    if not section.get("enabled", False):
        return None
    replay_path = str(section.get("replay_path", "")).strip()
    if not replay_path:
        raise ValueError("learning.enabled requires learning.replay_path (a JSONL replay corpus)")
    buffer = load_replay(replay_path)
    target = str(section.get("target", "corrected"))
    if not buffer.training_set():
        raise ValueError(f"{replay_path}: the replay corpus has no verified training items")
    if not buffer.heldout(target):
        raise ValueError(f"{replay_path}: the replay corpus has no held-out items in {target!r}")

    jobs_db = str(section.get("jobs_db", "data/learning_jobs.db"))
    store = SQLiteJobStore(jobs_db)
    try:
        checkpoints = CheckpointStore(section.get("checkpoint_dir", "checkpoints"))
        cfg = DreamConfig(
            target=target,
            dim=int(section.get("dim", 128)),
            min_train=int(section.get("min_train", 4)),
            new_ratio=float(section.get("new_ratio", 0.5)),
            seed=int(section.get("seed", 0)),
            replay=bool(section.get("replay", True)),
            replay_policy=str(section.get("replay_policy", "random")),
            initialization=str(section.get("initialization", "stable")),
            cold_start_checkpoint=(str(section["cold_start_checkpoint"])
                                   if section.get("cold_start_checkpoint") else None),
        )
        if len(buffer.training_set()) < cfg.min_train:
            raise ValueError(f"{replay_path}: {len(buffer.training_set())} verified training items, "
                             f"but learning.min_train is {cfg.min_train}")
        if (cfg.initialization == "stable" and checkpoints.current() is None
                and not cfg.cold_start_checkpoint):
            raise ValueError("learning.checkpoint_dir has no stable checkpoint; stage one or set "
                             "learning.cold_start_checkpoint (or use initialization = \"fresh\")")
        runner = LoopRunner(buffer, checkpoints, cfg,
                            min_target_gain=float(section.get("min_target_gain", 0.05)))
        hard_timeout = float(section.get("hard_timeout_s", 0) or 0)
        return LearningWorker(
            runner,
            store=store,
            max_queue=int(section.get("max_queue", 8)),
            hard_timeout_s=hard_timeout if hard_timeout > 0 else None,
        )
    except Exception:
        store.close()
        raise
