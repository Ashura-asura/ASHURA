"""Offline training for the tiny BrainSim core (blueprint B1).

PyTorch, CPU-first, standard optimiser and cross-entropy loss. The first experiment only
supervises next-token prediction; the need/action/confidence heads are built but stay
untrained until their tasks exist. Training is deterministic for a given seed.
"""
from __future__ import annotations

import math
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from brainsim.core.encoder import encode
from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.environment.sequence_tasks import to_xy


@dataclass(frozen=True)
class TrainConfig:
    hidden: int = 384
    layers: int = 2
    epochs: int = 30
    batch_size: int = 32
    lr: float = 3e-3
    weight_decay: float = 1e-4
    grad_clip: float = 1.0
    seed: int = 0
    device: str = "cpu"
    checkpoint: str | None = None
    verbose: bool = False

    def __post_init__(self) -> None:
        for name, value in (("hidden", self.hidden), ("layers", self.layers),
                            ("epochs", self.epochs), ("batch_size", self.batch_size)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name, value, allow_zero in (("lr", self.lr, False),
                                        ("weight_decay", self.weight_decay, True),
                                        ("grad_clip", self.grad_clip, True)):
            if (not isinstance(value, (int, float)) or isinstance(value, bool)
                    or not math.isfinite(float(value))
                    or (value < 0 if allow_zero else value <= 0)):
                bound = "non-negative" if allow_zero else "positive"
                raise ValueError(f"{name} must be finite and {bound}")
        try:
            torch.device(self.device)
        except (TypeError, RuntimeError) as e:
            raise ValueError(f"invalid device {self.device!r}") from e


def _validated_tokens(tokens: torch.Tensor, vocab: int, name: str) -> torch.Tensor:
    raw = torch.as_tensor(tokens)
    if raw.ndim != 2 or raw.shape[0] < 1 or raw.shape[1] < 2:
        raise ValueError(f"{name} must have shape (N>=1, L>=2)")
    if raw.is_complex() or raw.dtype == torch.bool:
        raise ValueError(f"{name} must contain real integer token ids")
    if raw.is_floating_point():
        if not bool(torch.isfinite(raw).all()) or not bool((raw == raw.round()).all()):
            raise ValueError(f"{name} must contain finite integer token ids")
    raw = raw.to(dtype=torch.long)
    if int(raw.min()) < 0 or int(raw.max()) >= vocab:
        raise ValueError(f"{name} contains token ids outside [0, {vocab})")
    return raw


def build_model(vocab: int, cfg: TrainConfig) -> BrainSim:
    torch.manual_seed(cfg.seed)
    return BrainSim(BrainSimConfig(vocab=vocab, hidden=cfg.hidden, layers=cfg.layers,
                                   in_dim=2 * vocab + 1))


def train_offline(model: BrainSim, tokens: torch.Tensor, cfg: TrainConfig,
                  val_tokens: torch.Tensor | None = None,
                  checkpoint: str | Path | None = None) -> tuple[dict, float]:
    """Train next-token prediction and return (history, seconds)."""
    if not isinstance(model, BrainSim):
        raise TypeError("model must be a BrainSim instance")
    tokens = _validated_tokens(tokens, model.cfg.vocab, "tokens")
    if val_tokens is not None:
        val_tokens = _validated_tokens(val_tokens, model.cfg.vocab, "val_tokens")
    torch.manual_seed(cfg.seed)
    device = torch.device(cfg.device)
    model.to(device)
    model.train()

    x, y = to_xy(tokens)
    loader = DataLoader(TensorDataset(x, y), batch_size=cfg.batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(cfg.seed))
    optimiser = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    loss_fn = nn.CrossEntropyLoss()

    history: dict = {"loss": [], "val_acc": []}
    started = time.perf_counter()
    for epoch in range(cfg.epochs):
        total, n = 0.0, 0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            optimiser.zero_grad(set_to_none=True)
            logits = model(encode(xb, model.cfg.vocab)).logits
            loss = loss_fn(logits.reshape(-1, model.cfg.vocab), yb.reshape(-1))
            loss.backward()
            if cfg.grad_clip > 0:
                nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            optimiser.step()
            total += float(loss.detach()) * xb.shape[0]
            n += xb.shape[0]
        history["loss"].append(total / max(n, 1))
        if val_tokens is not None:
            history["val_acc"].append(sequence_accuracy(model, val_tokens))
        if cfg.verbose:
            tail = f" val={history['val_acc'][-1]:.3f}" if history["val_acc"] else ""
            print(f"epoch {epoch + 1:02d}/{cfg.epochs} loss={history['loss'][-1]:.4f}{tail}")
    seconds = time.perf_counter() - started
    history["train_seconds"] = seconds
    model.eval()

    path = checkpoint or cfg.checkpoint
    if path:
        save_checkpoint(model, path, history, cfg)
    return history, seconds


def save_checkpoint(model: BrainSim, path: str | Path, history: dict | None = None,
                    cfg: TrainConfig | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    train_data = asdict(cfg) if cfg else None
    if train_data and train_data.get("checkpoint") is not None:
        train_data["checkpoint"] = str(train_data["checkpoint"])
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(fd)
    try:
        torch.save({"format_version": 1, "model": model.state_dict(),
                    "model_config": asdict(model.cfg), "train_config": train_data,
                    "history": history or {}}, tmp_name)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def load_checkpoint(path: str | Path, device: str = "cpu") -> BrainSim:
    data = torch.load(path, map_location=device, weights_only=True)
    model = BrainSim(BrainSimConfig(**data["model_config"]))
    model.load_state_dict(data["model"])
    model.to(device)
    return model


@torch.no_grad()
def sequence_logits(model: BrainSim, tokens: torch.Tensor, batch_size: int = 64) -> torch.Tensor:
    """Logits for every transition: (N, L-1, vocab). Each sequence starts from a zero state."""
    model.eval()
    device = next(model.parameters()).device
    x, _ = to_xy(tokens)
    out = []
    for start in range(0, x.shape[0], batch_size):
        xb = encode(x[start:start + batch_size].to(device), model.cfg.vocab)
        out.append(model(xb).logits.cpu())
    return torch.cat(out, dim=0)


@torch.no_grad()
def sequence_accuracy(model: BrainSim, tokens: torch.Tensor, batch_size: int = 64) -> float:
    _, y = to_xy(tokens)
    logits = sequence_logits(model, tokens, batch_size)
    return float((logits.argmax(-1) == y).float().mean())


@torch.no_grad()
def position_accuracy(model: BrainSim, tokens: torch.Tensor, batch_size: int = 64) -> list[float]:
    """Accuracy at each position in the sequence; useful for spotting rule-identification lag."""
    _, y = to_xy(tokens)
    correct = (sequence_logits(model, tokens, batch_size).argmax(-1) == y).float()
    return [float(v) for v in correct.mean(dim=0)]
