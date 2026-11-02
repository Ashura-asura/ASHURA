"""Isolated fast associative memory (blueprint 3.4G and 4.2).

The memory is a small matrix ``M`` that maps an observation key to a distribution over the
next token. It is updated with a normalised delta (Hebbian-style) rule:

    error_t = onehot(v_t) - M[k_t]
    M[k_t] = decay * M[k_t] + eta * error_t

For one-hot keys and ``eta = 1`` a single observation is stored exactly; repeated
observations converge. Two key modes are provided: ``token`` uses the current token only;
``pair`` uses (previous token, current token), which makes the same observation in a
different context a different key. The matrix is separate from all model parameters, can be
reset, and can be saved/loaded. It is deliberately *not* a second neural network: the first
experiment must isolate whether experience in this state changes later behaviour.

The memory does not decide when it is applied. Callers pass an ``apply_mask`` to blend it
only where it is valid (for example only for keys seen in the current task). This keeps
task-scoping and gate experiments in the learning controller, not hidden inside storage.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class FastMemoryConfig:
    vocab: int
    key_mode: str = "token"      # "token" (current observation) | "pair" (previous, current)
    decay: float = 1.0            # lambda in M_t = lambda*M_{t-1} + eta*delta
    eta: float = 1.0              # update rate
    blend: float = 0.9            # weight of memory when it is applied
    logit_scale: float = 20.0     # sharpens the memory distribution before blending
    surprise_threshold: float = 0.0   # update only when ||target - M[k]|| exceeds this

    def __post_init__(self) -> None:
        if self.vocab < 2:
            raise ValueError("vocab must be >= 2")
        if self.key_mode not in ("token", "pair"):
            raise ValueError("key_mode must be 'token' or 'pair'")
        if not 0.0 <= self.blend <= 1.0:
            raise ValueError("blend must be in [0, 1]")
        if self.logit_scale <= 0.0:
            raise ValueError("logit_scale must be > 0")
        if self.decay < 0.0 or self.eta <= 0.0:
            raise ValueError("decay must be >= 0 and eta must be > 0")

    @property
    def n_rows(self) -> int:
        return self.vocab if self.key_mode == "token" else self.vocab * self.vocab


class FastAssociativeMemory:
    """A bounded, resettable token -> next-token associative matrix."""

    def __init__(self, cfg: FastMemoryConfig | None = None):
        if cfg is None:
            raise ValueError("FastMemoryConfig (with vocab) is required")
        self.cfg = cfg
        self.M = torch.zeros(cfg.n_rows, cfg.vocab, dtype=torch.float32)
        self.counts = torch.zeros(cfg.n_rows, dtype=torch.int64)

    # ---- inspection ---------------------------------------------------------------------
    @property
    def size_bytes(self) -> int:
        return self.M.numel() * self.M.element_size() + self.counts.numel() * self.counts.element_size()

    @property
    def seen_keys(self) -> int:
        return int((self.counts > 0).sum())

    def seen(self, keys: torch.Tensor, prev: torch.Tensor | None = None) -> torch.Tensor:
        ids = self._ids(keys, prev)
        return self.counts[ids] > 0

    # ---- update -------------------------------------------------------------------------
    def update(self, keys: torch.Tensor, values: torch.Tensor,
               prev: torch.Tensor | None = None) -> list[float]:
        """Store observed transitions. Returns the surprise of each observation."""
        ids = self._ids(keys, prev)
        values = self._tokens(values)
        if ids.numel() != values.numel():
            raise ValueError("keys and values must have the same length")
        surprises: list[float] = []
        with torch.no_grad():
            for key, value in zip(ids.tolist(), values.tolist()):
                target = F.one_hot(torch.tensor(value), self.cfg.vocab).float()
                error = target - self.M[key]
                surprise = float(error.norm())
                surprises.append(surprise)
                if surprise >= self.cfg.surprise_threshold:
                    self.M[key] = self.cfg.decay * self.M[key] + self.cfg.eta * error
                    self.counts[key] += 1
        return surprises

    # ---- recall -------------------------------------------------------------------------
    def scores(self, keys: torch.Tensor, prev: torch.Tensor | None = None) -> torch.Tensor:
        """Raw memory scores for keys: (N, vocab). Unseen keys return zeros."""
        return self.M[self._ids(keys, prev)]

    def probabilities(self, keys: torch.Tensor, prev: torch.Tensor | None = None) -> torch.Tensor:
        return F.softmax(self.scores(keys, prev), dim=-1)

    def blend(self, model_logits: torch.Tensor, keys: torch.Tensor,
              prev: torch.Tensor | None = None,
              apply_mask: torch.Tensor | None = None) -> torch.Tensor:
        """Blend memory into model probabilities where it is valid.

        model_logits: (N, vocab). keys: (N,). prev: (N,) only for pair-keyed memory.
        apply_mask: optional (N,) bool mask from a learning controller. A key that has
        never been stored is never used.
        """
        if model_logits.ndim != 2 or model_logits.shape[-1] != self.cfg.vocab:
            raise ValueError("model_logits must be (N, vocab)")
        ids = self._ids(keys, prev)
        if ids.shape[0] != model_logits.shape[0]:
            raise ValueError("keys and model_logits must share the batch dimension")
        use = self.counts[ids] > 0
        if apply_mask is not None:
            mask = torch.as_tensor(apply_mask, dtype=torch.bool).flatten()
            if mask.shape[0] != ids.shape[0]:
                raise ValueError("apply_mask must match the batch dimension")
            use = use & mask
        p_model = F.softmax(model_logits, dim=-1)
        p_mem = F.softmax(self.M[ids] * self.cfg.logit_scale, dim=-1)
        out = p_model.clone()
        if bool(use.any()):
            out[use] = (1.0 - self.cfg.blend) * p_model[use] + self.cfg.blend * p_mem[use]
        return out

    # ---- lifecycle ----------------------------------------------------------------------
    def reset(self) -> None:
        """Drop every temporary association. Model parameters are never touched."""
        self.M.zero_()
        self.counts.zero_()

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        torch.save({"M": self.M, "counts": self.counts, "config": asdict(self.cfg)}, path)
        return path

    @classmethod
    def load(cls, path: str | Path, cfg: FastMemoryConfig | None = None) -> "FastAssociativeMemory":
        data = torch.load(path, map_location="cpu", weights_only=True)
        cfg = cfg or FastMemoryConfig(**data["config"])
        mem = cls(cfg)
        m, counts = data["M"], data["counts"]
        if m.shape != mem.M.shape or counts.shape != mem.counts.shape:
            raise ValueError("saved memory shape does not match the requested configuration")
        mem.M.copy_(m)
        mem.counts.copy_(counts)
        return mem

    def _ids(self, keys: torch.Tensor, prev: torch.Tensor | None = None) -> torch.Tensor:
        keys = self._tokens(keys)
        if self.cfg.key_mode == "token":
            return keys
        if prev is None:
            raise ValueError("pair-keyed memory requires previous tokens")
        prev = self._tokens(prev)
        if prev.shape != keys.shape:
            raise ValueError("previous tokens must match keys")
        return prev * self.cfg.vocab + keys

    def _tokens(self, tokens: torch.Tensor) -> torch.Tensor:
        tokens = torch.as_tensor(tokens, dtype=torch.long).flatten()
        if tokens.numel() and (int(tokens.min()) < 0 or int(tokens.max()) >= self.cfg.vocab):
            raise ValueError("token id outside the vocabulary")
        return tokens
