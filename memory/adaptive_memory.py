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
import re
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

    @property
    def param_count(self) -> int:
        return self.M.size

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
        np.savez(path, M=self.M, S=self.S, n_writes=self.n_writes,
                 df_keys=np.array(list(self.df.keys())), df_vals=np.array(list(self.df.values()), dtype=np.int64),
                 cfg=np.array([str(asdict(self.cfg))]))

    @classmethod
    def load(cls, path: str, cfg: AMemConfig | None = None) -> "AdaptiveMemory":
        d = np.load(path, allow_pickle=False)
        m = cls(cfg or AMemConfig())
        if d["M"].shape != m.M.shape:
            raise ValueError("checkpoint shape does not match config")
        m.M, m.S, m.n_writes = d["M"].copy(), d["S"].copy(), int(d["n_writes"])
        m.df = {str(k): int(v) for k, v in zip(d["df_keys"], d["df_vals"])}
        return m


def drain_neural_queue(db, mem: AdaptiveMemory, payload=lambda e: e.output, passes: int = 1) -> int:
    """Consume AMA's 'neural_memory' queue (repeated, reliable associations) into the adaptive memory."""
    from .episodic import EpisodicMemory
    ep, n = EpisodicMemory(db), 0
    rows = db.conn.execute("SELECT exp_id FROM dream_queue WHERE queue = 'neural_memory'").fetchall()
    for r in rows:
        e = ep.get(r["exp_id"])
        if e:
            mem.write(e.input, payload(e), passes)
            n += 1
        db.conn.execute("DELETE FROM dream_queue WHERE exp_id = ?", (r["exp_id"],))
    db.conn.commit()
    return n
