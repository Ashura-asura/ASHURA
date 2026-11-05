"""Ollama backend: the language model as a component served by a local `ollama serve`.

Standard library only (urllib), so ASHURA gains no new dependency. Decoding is greedy
(temperature 0, fixed seed) so repeated benchmark runs are comparable.

Pinning: the stable-checkpoint hash check of the llama.cpp backend becomes a digest check here.
`digest` is the ID column of `ollama list` (a prefix of the model's sha256 digest); if it is set and
the installed model's digest does not start with it, loading is refused.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .concurrency import ConcurrencyGate
from .language_model import LanguageModel
from .model_config import ModelConfig


class OllamaError(RuntimeError):
    pass


def _call(host: str, path: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    url = host.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
        if not isinstance(body, dict):
            raise OllamaError(f"unexpected response from Ollama for {path}: expected a JSON object")
        if body.get("error"):
            raise OllamaError(f"Ollama reported an error for {path}: {str(body['error'])[:300]}")
        return body
    except OllamaError:
        raise
    except json.JSONDecodeError as e:
        raise OllamaError(f"Ollama returned invalid JSON for {path}: {e}") from e
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise OllamaError(f"Ollama returned HTTP {e.code} for {path}: {body}") from e
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        raise OllamaError(f"cannot reach Ollama at {host} ({e}). Is `ollama serve` running?") from e


def list_models(host: str = "http://127.0.0.1:11434") -> list[dict]:
    """[{name, digest, size}] for every installed model (same data as `ollama list`)."""
    return [{"name": m["name"], "digest": m.get("digest", ""), "size": m.get("size", 0)}
            for m in _call(host, "/api/tags").get("models", [])]


def running_models(host: str = "http://127.0.0.1:11434") -> list[dict]:
    """Models currently loaded in memory, with their RAM/VRAM footprint (`ollama ps`)."""
    return [{"name": m["name"], "size": m.get("size", 0), "size_vram": m.get("size_vram", 0)}
            for m in _call(host, "/api/ps").get("models", [])]


def unload(host: str, model: str) -> None:
    """Free the model's memory so the next model is measured on its own."""
    _call(host, "/api/generate", {"model": model, "keep_alive": 0}, timeout=60)


@dataclass
class GenStats:
    eval_count: int = 0                # generated tokens
    eval_duration_ns: int = 0
    prompt_eval_count: int = 0
    prompt_eval_duration_ns: int = 0
    load_duration_ns: int = 0
    total_duration_ns: int = 0

    @property
    def tokens_per_s(self) -> float:
        return self.eval_count / (self.eval_duration_ns / 1e9) if self.eval_duration_ns else float("nan")


class OllamaModel(LanguageModel):
    def __init__(self, cfg: ModelConfig):
        if not cfg.model:
            raise ValueError("foundation.model is empty; set it to a tag from `ollama list`")
        self.cfg, self.name = cfg, f"ollama:{cfg.model}"
        self.last_stats = GenStats()
        installed = {m["name"]: m for m in list_models(cfg.host)}
        if cfg.model not in installed:
            raise OllamaError(f"model {cfg.model!r} is not installed; installed: {sorted(installed)}")
        self.digest = installed[cfg.model]["digest"]
        if cfg.digest and not self.digest.startswith(cfg.digest):
            raise RuntimeError(f"digest mismatch for {cfg.model}: installed {self.digest[:12]}, "
                               f"pinned {cfg.digest[:12]}; refusing to use a modified model")
        self.gate = (ConcurrencyGate(cfg.max_inflight, cfg.max_queue, cfg.queue_timeout_s)
                     if cfg.max_inflight else None)

    def _request(self, prompt: str, max_tokens: int) -> str:
        payload = {
            "model": self.cfg.model, "prompt": prompt, "stream": False, "keep_alive": self.cfg.keep_alive,
            "options": {"temperature": 0, "seed": 0, "top_p": self.cfg.top_p,
                        "num_predict": max_tokens, "num_ctx": self.cfg.n_ctx},
        }
        if self.cfg.think is not None:
            payload["think"] = self.cfg.think
        r = _call(self.cfg.host, "/api/generate", payload, timeout=self.cfg.timeout_s)
        self.last_stats = GenStats(r.get("eval_count", 0), r.get("eval_duration", 0), r.get("prompt_eval_count", 0),
                                   r.get("prompt_eval_duration", 0), r.get("load_duration", 0), r.get("total_duration", 0))
        return r.get("response", "").strip()

    def generate(self, prompt: str, max_tokens: int = 128) -> str:
        if self.gate is None:
            return self._request(prompt, max_tokens)
        with self.gate.slot():
            return self._request(prompt, max_tokens)
