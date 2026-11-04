"""Titans-inspired neural adaptive memory (spec 5.1.D, 15.1, Phase 4).  EXPERIMENTAL.

A bounded linear associative memory M (dim_v x dim_k) trained online at "test time":

    surprise_t = || M k - v ||                      (prediction error before the update)
    S_t        = momentum * S_{t-1} - lr * (M k - v) k^T      (gradient of 0.5||Mk-v||^2; momentum = past surprise)
    M_t        = (1 - decay) * M_{t-1} + S_t        (data-independent forgetting)

Inspired by, NOT a reproduction of, Titans: no deep memory MLP, no data-dependent gates, no attention.
Keys/values are fixed random-indexing vectors of tokens (no learned embedding model, no LLM call).
The gradient is analytic for a linear memory, so NumPy is enough; port to PyTorch when the memory
becomes non-linear. The memory is independent of Qwen, resettable, and checkpointable.
"""
from __future__ import annotations

import math
import os
import re
import time
import zlib
from dataclasses import asdict, dataclass

import numpy as np

_TOK = re.compile(r"\w+", re.UNICODE)


@dataclass
class AMemConfig:
    dim_k: int = 256
    dim_v: int = 256
    lr: float = 0.6              # for unit-norm keys, lr=1.0 fits one pair exactly in one step
    momentum: float = 0.0
    decay: float = 0.0
    surprise_gate: float = 0.0   # skip the update when surprise is below this (already-known pair)
    idf: bool = True             # down-weight tokens that appear in many written keys
    seed: int = 0


class AdaptiveMemory:
    def __init__(self, cfg: AMemConfig | None = None):
        self.cfg = cfg or AMemConfig()
        self._tok_cache: dict[tuple[str, int], np.ndarray] = {}
        self.reset()

    # ---- state ------------------------------------------------------------------------------
    def reset(self) -> None:
        """Drop ALL learned state (M, momentum, token statistics). Token vectors are fixed constants."""
        c = self.cfg
        self.M = np.zeros((c.dim_v, c.dim_k), dtype=np.float32)
        self.S = np.zeros_like(self.M)
        self.df: dict[str, int] = {}
        self.n_writes = 0
        self.last_snapshot = None

    @property
    def param_count(self) -> int:
        return self.M.size

    def snapshot(self) -> dict:
        """Recoverable copy of the learned state (bounded by the parameter count)."""
        return {"M": self.M.copy(), "S": self.S.copy(), "df": dict(self.df), "n_writes": self.n_writes}

    def restore(self, snapshot: dict) -> None:
        if snapshot["M"].shape != self.M.shape:
            raise ValueError("snapshot shape does not match config")
        self.M = snapshot["M"].copy()
        self.S = snapshot["S"].copy()
        self.df = dict(snapshot["df"])
        self.n_writes = int(snapshot["n_writes"])

    # ---- featurisation ------------------------------------------------------------------------
    def _tv(self, tok: str, dim: int) -> np.ndarray:
        key = (tok, dim)
        v = self._tok_cache.get(key)
        if v is None:
            rng = np.random.default_rng(zlib.crc32(tok.encode()) ^ (self.cfg.seed * 2654435761 & 0xFFFFFFFF))
            v = rng.standard_normal(dim).astype(np.float32)
            v /= np.linalg.norm(v)
            self._tok_cache[key] = v
        return v

    def _weight(self, tok: str) -> float:
        if not self.cfg.idf:
            return 1.0
        return math.log(1.0 + (self.n_writes + 1) / (self.df.get(tok, 0) + 1))

    def encode(self, text: str, dim: int, weighted: bool) -> np.ndarray:
        toks = _TOK.findall(text.lower())
        out = np.zeros(dim, dtype=np.float32)
        for t in toks:
            out += (self._weight(t) if weighted else 1.0) * self._tv(t, dim)
        n = np.linalg.norm(out)
        return out / n if n > 0 else out

    def key(self, text: str) -> np.ndarray:
        return self.encode(text, self.cfg.dim_k, weighted=True)

    def value(self, text: str) -> np.ndarray:
        return self.encode(text, self.cfg.dim_v, weighted=False)

    # ---- learning / recall --------------------------------------------------------------------
    def write(self, key_text: str, value_text: str, passes: int = 1) -> float:
        """One online update (repeat `passes` times). Returns the surprise of the first pass."""
        c = self.cfg
        for t in set(_TOK.findall(key_text.lower())):      # df statistics grow with writes
            self.df[t] = self.df.get(t, 0) + 1
        self.n_writes += 1
        k, v = self.key(key_text), self.value(value_text)
        first = None
        for _ in range(passes):
            err = self.M @ k - v
            surprise = float(np.linalg.norm(err))
            first = surprise if first is None else first
            if surprise < c.surprise_gate:
                break
            grad = np.outer(err, k)
            self.S = c.momentum * self.S - c.lr * grad
            self.M = (1.0 - c.decay) * self.M + self.S
        return first or 0.0

    def read(self, key_text: str) -> np.ndarray:
        return self.M @ self.key(key_text)

    def recall(self, key_text: str, candidates: list[str], cand_vecs: np.ndarray | None = None) -> tuple[str, float]:
        """Nearest candidate (cosine) to the recalled vector. Returns (candidate, cosine)."""
        y = self.read(key_text)
        n = np.linalg.norm(y)
        if n == 0:
            return "", 0.0
        V = cand_vecs if cand_vecs is not None else self.candidate_matrix(candidates)
        sims = V @ (y / n)
        i = int(np.argmax(sims))
        return candidates[i], float(sims[i])

    def candidate_matrix(self, candidates: list[str]) -> np.ndarray:
        return np.stack([self.value(c) for c in candidates])

    # ---- persistence --------------------------------------------------------------------------
    def save(self, path: str) -> None:
        """Write atomically (temp file + rename) so an interrupted save never corrupts an existing checkpoint.

        numpy silently appends ".npz" to names that lack it, which made the file land somewhere other than
        `path`; writing through a file object keeps the exact path the caller asked for.
        """
        tmp = f"{path}.tmp"
        with open(tmp, "wb") as f:
            np.savez(f, M=self.M, S=self.S, n_writes=self.n_writes, seed=self.cfg.seed,
                     df_keys=np.array(list(self.df.keys()), dtype=str),
                     df_vals=np.array(list(self.df.values()), dtype=np.int64),
                     cfg=np.array([str(asdict(self.cfg))]))
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str, cfg: AMemConfig | None = None) -> "AdaptiveMemory":
        d = np.load(path, allow_pickle=False)
        m = cls(cfg or AMemConfig())
        if d["M"].shape != m.M.shape:
            raise ValueError("checkpoint shape does not match config")
        # Token vectors are derived from the seed: loading with a different seed would silently scramble recall.
        if "seed" in d.files and int(d["seed"]) != m.cfg.seed:
            raise ValueError(f"checkpoint was trained with seed {int(d['seed'])} but config has seed {m.cfg.seed}")
        m.M, m.S, m.n_writes = d["M"].copy(), d["S"].copy(), int(d["n_writes"])
        m.df = {str(k): int(v) for k, v in zip(d["df_keys"], d["df_vals"])}
        return m


def _conflicting_verified(ep, e) -> bool:
    """True when another record with the same key makes a contradictory claim with >= evidence."""
    from learning.compare import answers_agree
    for old in ep.find_by_input(e.input, e.task_category):
        if old.id == e.id:
            continue
        if old.verification_status in {"verified", "trusted_material", "user_provided",
                                       "user_corrected"} and not answers_agree(
                e.input, e.output, old.output):
            return True
    return False


def drain_neural_queue(db, mem: AdaptiveMemory, payload=lambda e: e.output, passes: int = 1,
                       require_verified: bool = True, min_reliability: float = 0.8,
                       max_updates: int = 1000) -> int:
    """Consume AMA's 'neural_memory' queue into the adaptive memory under a write gate (P23).

    A record is applied only if it is independently verified, meets the reliability floor, has no
    unresolved verified conflict, and the drain respects a hard update bound. Rejected records are
    removed from the queue and logged; they are never silently learned.
    """
    from .episodic import EpisodicMemory
    if passes < 1 or max_updates < 1:
        raise ValueError("passes and max_updates must be positive")
    ep, n = EpisodicMemory(db), 0
    rows = db.conn.execute(
        "SELECT exp_id FROM dream_queue WHERE queue = 'neural_memory' ORDER BY ts LIMIT ?",
        (max_updates,)).fetchall()
    snapshot = mem.snapshot() if rows else None       # old associations stay recoverable (P23)
    try:
        for r in rows:
            e = ep.get(r["exp_id"])
            reason = ""
            if e is None:
                reason = "experience no longer exists"
            elif require_verified and e.verification_status != "verified":
                reason = f"verification_status={e.verification_status!r} is not independently verified"
            elif e.reliability < min_reliability:
                reason = f"reliability {e.reliability:.2f} < required {min_reliability:.2f}"
            elif _conflicting_verified(ep, e):
                reason = "unresolved conflict with another verified/trusted claim"
            if reason:
                db.conn.execute(
                    """INSERT INTO admission_log(ts, exp_id, decision, score, features, reason)
                       VALUES (?,?,?,?,?,?)""",
                    (time.time(), r["exp_id"], "NEURAL_UPDATE_REJECTED", None, "{}", reason))
            else:
                mem.write(e.input, payload(e), min(passes, 8))
                n += 1
            db.conn.execute("DELETE FROM dream_queue WHERE exp_id = ?", (r["exp_id"],))
    except Exception:
        if snapshot is not None:
            mem.restore(snapshot)
        db.conn.rollback()
        raise
    mem.last_snapshot = snapshot
    db.conn.commit()
    return n
