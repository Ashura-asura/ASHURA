"""Tests for the delayed-copy environment, fixed baseline and B2 training helpers."""
import torch

from brainsim.core.fixed_baseline import FixedWindowMLP
from brainsim.core.model import BrainSim, BrainSimConfig
from brainsim.environment.delayed_copy import DelayedCopyConfig, fixed_window, make_batch
from brainsim.learning.delayed_copy_train import (evaluate_fixed, evaluate_gru,
                                                  make_fixed_dataset, train_fixed, train_gru)
from brainsim.learning.train import TrainConfig, build_model

CFG = DelayedCopyConfig(symbols=5, cue_len=2, max_delay=6, train_delays=(1, 3),
                        eval_delays=(1, 3, 6))


def test_batch_layout_holds_cues_across_the_delay():
    batch = make_batch(CFG, 32, delays=(3,), seed=0)
    tokens, cues, mask = batch["tokens"], batch["cues"], batch["recall_mask"]
    assert tokens.shape == (32, CFG.length)
    assert mask.shape == (32, CFG.length - 1) and int(mask.sum()) == 32 * CFG.cue_len
    for row in range(32):
        go = (tokens[row] == CFG.go).nonzero().item()
        assert torch.equal(tokens[row, :CFG.cue_len], cues[row])
        assert torch.equal(tokens[row, go + 1:go + 1 + CFG.cue_len], cues[row])
        assert torch.all(tokens[row, CFG.cue_len:go] == CFG.blank)
        assert torch.all(mask[row, go:go + CFG.cue_len])


def test_fixed_window_never_contains_the_recall_block():
    batch = make_batch(CFG, 16, delays=(1, 3), seed=1)
    window = fixed_window(batch["tokens"], CFG)
    assert window.shape == (16, CFG.cue_len + CFG.max_delay + 1)
    for row in range(16):
        go = (batch["tokens"][row] == CFG.go).nonzero().item()
        assert go < window.shape[1]
        assert torch.equal(window[row, :CFG.cue_len], batch["cues"][row])
        assert torch.all(window[row, go + 1:] == CFG.blank)


def test_batches_are_deterministic_and_delay_sensitive():
    a = make_batch(CFG, 8, delays=(1, 6), seed=4)
    b = make_batch(CFG, 8, delays=(1, 6), seed=4)
    assert torch.equal(a["tokens"], b["tokens"])
    assert set(a["delay"].tolist()) <= {1, 6}


def test_fixed_baseline_shapes_and_parameter_match():
    gru = BrainSim(BrainSimConfig(vocab=CFG.vocab, hidden=64, in_dim=2 * CFG.vocab + 1))
    fixed = FixedWindowMLP(CFG, hidden=160)
    tokens = make_batch(CFG, 4, delays=(1,), seed=0)["tokens"]
    assert gru(torch.randn(4, 7, gru.cfg.in_dim)).logits.shape == (4, 7, CFG.vocab)
    assert fixed(tokens).shape == (4, CFG.cue_len, CFG.symbols)
    assert 0.5 < fixed.param_count / gru.param_count < 2.0


def test_b2_training_smoke(tmp_path):
    tokens, cues, mask = make_fixed_dataset(CFG, 64, seed=0)
    gru = build_model(CFG.vocab, TrainConfig(hidden=16, layers=1, epochs=2, batch_size=16, seed=0))
    fixed = FixedWindowMLP(CFG, hidden=32)
    gru, gh, gs = train_gru(gru, CFG, tokens, cues, mask, epochs=2, batch=16, seed=0)
    fixed, fh, fs = train_fixed(fixed, CFG, tokens, cues, mask, epochs=2, batch=16, seed=0)
    assert len(gh["loss"]) == 2 and len(fh["loss"]) == 2
    assert gs >= 0 and fs >= 0
    batch = make_batch(CFG, 16, delays=(1,), seed=9)
    for metrics in (evaluate_gru(gru, CFG, batch), evaluate_fixed(fixed, CFG, batch)):
        assert 0.0 <= metrics["token_accuracy"] <= 1.0
        assert 0.0 <= metrics["full_recall_accuracy"] <= 1.0
