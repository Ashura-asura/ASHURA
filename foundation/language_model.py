"""Language foundation interface. The model is a component, not the architecture."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Iterator

from .model_config import ModelConfig, verify_checkpoint


class GenerationCancelled(Exception):
    """Raised by a streaming callback when the client has gone away."""


class LanguageModel(ABC):
    name: str = "abstract"

    @abstractmethod
    def generate(self, prompt: str, max_tokens: int = 128) -> str: ...

    def stream(self, prompt: str, max_tokens: int = 128) -> Iterator[str]:
        """Yield generated text chunks. Backends without token streaming yield once."""
        text = self.generate(prompt, max_tokens)
        if text:
            yield text


class EchoModel(LanguageModel):
    """Deterministic stand-in so the pipeline, tests and latency harness run without weights.

    It is NOT a baseline for answer quality. It only exercises plumbing.
    """
    name = "echo-stub"

    def generate(self, prompt: str, max_tokens: int = 128) -> str:
        m = re.search(r"Question:\s*(.*)$", prompt, re.S)
        return f"[echo] {(m.group(1) if m else prompt).strip()[:200]}"

    def stream(self, prompt: str, max_tokens: int = 128):
        text = self.generate(prompt, max_tokens)
        for index in range(0, len(text), 8):
            yield text[index:index + 8]


class LlamaCppModel(LanguageModel):
    """Quantized local inference through llama.cpp (llama-cpp-python). Weights stay frozen."""

    def __init__(self, cfg: ModelConfig):
        if not cfg.path:
            raise ValueError("foundation.path is empty; download a GGUF and set it in config/ashura.toml")
        if cfg.sha256 and not verify_checkpoint(cfg.path, cfg.sha256):
            raise RuntimeError("checkpoint hash mismatch: refusing to load a modified stable model")
        try:
            from llama_cpp import Llama
        except ImportError as e:  # pragma: no cover
            raise RuntimeError("pip install llama-cpp-python") from e
        self.name = f"{cfg.checkpoint}:{cfg.quantization}"
        self._llm = Llama(model_path=cfg.path, n_ctx=cfg.n_ctx, n_threads=cfg.n_threads, verbose=False)

    def generate(self, prompt: str, max_tokens: int = 128) -> str:  # pragma: no cover
        out = self._llm(prompt, max_tokens=max_tokens, temperature=0.0)  # greedy => reproducible
        return out["choices"][0]["text"].strip()


def build_model(cfg: ModelConfig) -> LanguageModel:
    if cfg.backend == "echo":
        return EchoModel()
    if cfg.backend == "llama_cpp":
        return LlamaCppModel(cfg)
    if cfg.backend == "ollama":
        from .ollama_model import OllamaModel
        return OllamaModel(cfg)
    raise ValueError(f"unknown backend {cfg.backend!r}")
