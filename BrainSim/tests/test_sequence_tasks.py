"""Tests for the permutation-sequence environment."""
import torch

from brainsim.environment.sequence_tasks import (SequenceConfig, adaptation_episodes,
                                                 make_rules, single_cycle_permutation,
                                                 to_xy, training_sequences)


def test_single_cycle_permutation_visits_every_token():
    import numpy as np
    rng = np.random.default_rng(0)
    for _ in range(20):
        rule = single_cycle_permutation(12, rng)
        assert sorted(rule) == list(range(12))
        seen, token = [], 0
        for _ in range(12):
            seen.append(token)
            token = rule[token]
        assert token == 0 and len(set(seen)) == 12


def test_rules_are_disjoint_and_deterministic():
    cfg = SequenceConfig(vocab=12, train_rules=5, heldout_rules=5, seed=7)
    a = make_rules(cfg)
    b = make_rules(cfg)
    assert a == b
    assert len(set(a.train)) == 5 and len(set(a.heldout)) == 5
    assert not set(a.train) & set(a.heldout)


def test_sequences_follow_the_hidden_rule():
    cfg = SequenceConfig(vocab=10, train_rules=3, heldout_rules=2, starts_per_rule=4,
                         val_starts_per_rule=3, episodes_per_rule=2, seq_len=12,
                         study_len=5, test_len=8, seed=3)
    rules = make_rules(cfg)
    train = training_sequences(cfg, rules)
    for row in train:
        rule = next(r for r in rules.train
                    if all(r[int(row[i])] == int(row[i + 1]) for i in range(len(row) - 1)))
        assert all(rule[int(row[i])] == int(row[i + 1]) for i in range(len(row) - 1))
    for ep in adaptation_episodes(cfg, rules):
        rule = rules.heldout[ep.rule_id]
        for seq in (ep.study, ep.test):
            assert all(rule[int(seq[i])] == int(seq[i + 1]) for i in range(len(seq) - 1))


def test_adaptation_split_shapes_and_xy():
    cfg = SequenceConfig(vocab=9, train_rules=2, heldout_rules=3, episodes_per_rule=4,
                         seq_len=7, study_len=4, test_len=6, seed=1)
    rules = make_rules(cfg)
    episodes = adaptation_episodes(cfg, rules)
    assert len(episodes) == 3 * 4
    assert episodes[0].study.shape == (5,) and episodes[0].test.shape == (7,)
    x, y = to_xy(torch.stack([e.test for e in episodes]))
    assert x.shape == (12, 6) and y.shape == (12, 6)
    assert torch.equal(x[:, 1:], y[:, :-1])


def test_different_seeds_change_data():
    a = make_rules(SequenceConfig(seed=0))
    b = make_rules(SequenceConfig(seed=1))
    assert a.train != b.train
