"""Neural arithmetic expert (Phase 7 - HARN, initial seed).

This is intentionally lightweight and NumPy-only so it works with the current
repo dependencies.

Milestone:
- Train a tiny “neural expert” for integer addition.
- Provide a stable predict() API that returns exact rational values
  (Fractions) so the existing verifier (`skills/arithmetic/exact.py`) can
  cross-check safely.

Integration:
- `brain/controller.py` may use this expert when a checkpoint is present and
  the expression is a simple integer addition.

Checkpoint location:
- Default: `checkpoints/neural_arithmetic/addition.npz`
- Override via env var: `ASHURA_NEURAL_ADDITION_CHECKPOINT`
"""

from __future__ import annotations

import ast
import os
import threading
from dataclasses import dataclass
from fractions import Fraction
from typing import Tuple

import numpy as np


# Expression parsing ---------------------------------------------------------------------------------


def _parse_int_literal(node: ast.AST) -> int | None:
    """Return an int for supported AST nodes, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        v = _parse_int_literal(node.operand)
        if v is None:
            return None
        return v if isinstance(node.op, ast.UAdd) else -v
    return None


def parse_simple_integer_add(expr: str) -> Tuple[int, int] | None:
    """Parse a simple integer addition expression `a + b`.

    Supports whitespace and unary +/- on integer literals.

    Returns:
        (a, b) or None if expression is not a strict integer add.
    """
    try:
        tree = ast.parse(expr.replace("^", "**"), mode="eval")
    except SyntaxError:
        return None

    node = tree.body
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Add):
        return None

    a = _parse_int_literal(node.left)
    b = _parse_int_literal(node.right)
    if a is None or b is None:
        return None

    # This phase deliberately limits to integer addition.
    return a, b


# Expert --------------------------------------------------------------------------------------------


@dataclass
class AdditionExpertConfig:
    """Training configuration for the addition expert."""

    seed: int = 0
    # Training range for generating random integer pairs.
    a_min: int = -1000
    a_max: int = 1000
    b_min: int = -1000
    b_max: int = 1000


class NeuralAdditionExpert:
    """A NumPy-trained addition expert.

    Model (linear regression):
        y = w1 * a + w2 * b + bias

    For integer addition, a least-squares fit with enough random coverage
    should produce a function that is extremely close to the exact sum.
    """

    def __init__(self, w: np.ndarray | None = None, bias: float | None = None):
        self.w = w  # shape (2,)
        self.bias = bias

    @property
    def available(self) -> bool:
        return self.w is not None and self.bias is not None

    @classmethod
    def default_checkpoint_path(cls) -> str:
        override = os.environ.get("ASHURA_NEURAL_ADDITION_CHECKPOINT")
        if override:
            return override
        return os.path.join("checkpoints", "neural_arithmetic", "addition.npz")

    @classmethod
    def load(cls, path: str) -> "NeuralAdditionExpert":
        d = np.load(path)
        w = d["w"].astype(np.float64)
        bias = float(d["bias"])
        if w.shape != (2,):
            raise ValueError(f"bad addition weights shape: {w.shape}")
        return cls(w=w, bias=bias)

    def save(self, path: str) -> None:
        if not self.available:
            raise ValueError("cannot save: expert not trained/loaded")
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        np.savez(path, w=self.w, bias=self.bias)

    def train(self, cfg: AdditionExpertConfig, n: int = 5000) -> None:
        rng = np.random.default_rng(cfg.seed)
        a = rng.integers(cfg.a_min, cfg.a_max + 1, size=n, dtype=np.int64)
        b = rng.integers(cfg.b_min, cfg.b_max + 1, size=n, dtype=np.int64)
        y = (a.astype(np.float64) + b.astype(np.float64))

        # Solve least squares for y = w1*a + w2*b + bias
        X = np.stack(
            [a.astype(np.float64), b.astype(np.float64), np.ones_like(a, dtype=np.float64)], axis=1
        )
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        self.w = beta[:2]
        self.bias = float(beta[2])

    def predict_fraction(self, a: int, b: int) -> Fraction:
        if not self.available:
            raise NotImplementedError("neural addition expert not available")

        y = float(self.w[0]) * a + float(self.w[1]) * b + float(self.bias)
        # For a trained least-squares expert this should be very close to an int.
        y_int = int(round(y))
        return Fraction(y_int, 1)

    def predict_int(self, a: int, b: int) -> int:
        return int(self.predict_fraction(a, b).numerator)

    @classmethod
    def load_if_available(cls, path: str | None = None) -> "NeuralAdditionExpert":
        p = path or cls.default_checkpoint_path()
        if os.path.exists(p):
            try:
                return cls.load(p)
            except Exception:
                # Corrupt checkpoint: treat as unavailable.
                return cls()
        return cls()


# Float64 represents integers exactly only up to 2**53. Beyond that the candidate is not applicable
# (and float(huge_int) would raise OverflowError), so the exact evaluator simply answers alone.
_MAX_SAFE_INT = 2 ** 53

_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, NeuralAdditionExpert]] = {}


def _cached_expert(path: str | None = None) -> NeuralAdditionExpert:
    """Load the checkpoint once and reload only when the file changes (was: a disk read per request)."""
    p = path or NeuralAdditionExpert.default_checkpoint_path()
    try:
        mtime = os.path.getmtime(p)
    except OSError:
        with _cache_lock:
            _cache.pop(p, None)
        return NeuralAdditionExpert()
    with _cache_lock:
        hit = _cache.get(p)
        if hit and hit[0] == mtime:
            return hit[1]
    expert = NeuralAdditionExpert.load_if_available(p)
    with _cache_lock:
        _cache[p] = (mtime, expert)
    return expert


def try_neural_addition(expr: str, expert: NeuralAdditionExpert | None = None) -> Fraction | None:
    """Try to compute an integer addition expression using the neural expert."""
    if expert is None:
        expert = _cached_expert()
    if not expert.available:
        return None

    parsed = parse_simple_integer_add(expr)
    if parsed is None:
        return None

    a, b = parsed
    if abs(a) > _MAX_SAFE_INT or abs(b) > _MAX_SAFE_INT:
        return None
    return expert.predict_fraction(a, b)
