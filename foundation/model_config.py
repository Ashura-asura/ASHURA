"""Foundation model configuration and stable-checkpoint protection (spec 4, Principle 1)."""
from __future__ import annotations

import hashlib
import os
import stat
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    backend: str = "echo"
    family: str = "Qwen Instruct"
    checkpoint: str = "TBD"
    quantization: str = "TBD"
    licence: str = "TBD"
    path: str = ""
    sha256: str = ""
    n_ctx: int = 2048
    n_threads: int = 4
    # --- Ollama backend (backend = "ollama") ---
    model: str = ""                 # tag as shown by `ollama list`, e.g. "tony:7b"
    host: str = "http://127.0.0.1:11434"
    digest: str = ""                # ID column of `ollama list` (12+ hex chars); pins the exact weights
    keep_alive: str = "10m"
    timeout_s: float = 300.0
    top_p: float = 0.9              # pinned explicitly; greedy decoding still uses temperature 0
    think: bool | None = None       # Ollama thinking models: False for the fast response path, None = model default
    # --- client-side concurrency policy (F-047); the server owns OLLAMA_NUM_PARALLEL ---
    max_inflight: int = 0           # 0 = unlimited; shipped Ollama profiles use 1
    max_queue: int = 8              # waiting requests allowed when max_inflight is reached
    queue_timeout_s: float = 60.0   # reject instead of waiting forever

    def __post_init__(self) -> None:
        if self.backend not in {"echo", "llama_cpp", "ollama"}:
            raise ValueError(f"foundation.backend must be echo, llama_cpp or ollama (got {self.backend!r})")
        if self.n_ctx < 1 or self.n_threads < 1 or self.timeout_s <= 0:
            raise ValueError("foundation.n_ctx, n_threads and timeout_s must be positive")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("foundation.top_p must be in (0, 1]")
        if self.max_inflight < 0 or self.max_queue < 0 or self.queue_timeout_s <= 0:
            raise ValueError("foundation.max_inflight and max_queue must be >= 0; "
                             "queue_timeout_s must be positive")

    @property
    def is_pinned(self) -> bool:
        """A reproducible baseline needs a concrete checkpoint, licence and a content hash/digest."""
        if self.backend == "ollama":
            return all(v and v != "TBD" for v in (self.model, self.digest, self.licence))
        return all(v and v != "TBD" for v in (self.checkpoint, self.quantization, self.licence, self.sha256))


def load_config(path: str | os.PathLike = "config/ashura.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def load_model_config(path: str | os.PathLike = "config/ashura.toml") -> ModelConfig:
    section = load_config(path).get("foundation")
    if section is None:
        raise ValueError(f"{path}: missing the [foundation] section")
    valid = {f.name for f in fields(ModelConfig)}
    unknown = sorted(set(section) - valid)
    if unknown:                      # a typo such as `chekpoint` must be a clear error, not a TypeError traceback
        raise ValueError(f"{path}: unknown [foundation] key(s) {unknown}; valid keys: {sorted(valid)}")
    return ModelConfig(**section)


def sha256_file(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def verify_checkpoint(path: str | os.PathLike, expected_sha256: str) -> bool:
    return bool(expected_sha256) and sha256_file(path) == expected_sha256


def protect_checkpoint(path: str | os.PathLike) -> None:
    """Make a stable checkpoint read-only. (Best effort on Windows.)"""
    p = Path(path)
    p.chmod(p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
