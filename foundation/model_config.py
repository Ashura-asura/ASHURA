"""Foundation model configuration and stable-checkpoint protection (spec 4, Principle 1)."""
from __future__ import annotations

import hashlib
import os
import stat
import tomllib
from dataclasses import dataclass
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
    model: str = ""                 # tag as shown by `ollama list`, e.g. "ref-base:7b"
    host: str = "http://127.0.0.1:11434"
    digest: str = ""                # ID column of `ollama list` (12+ hex chars); pins the exact weights
    keep_alive: str = "10m"
    timeout_s: float = 300.0

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
    return ModelConfig(**load_config(path)["foundation"])


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
