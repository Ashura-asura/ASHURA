"""Frozen-corpus and control probes for EXP-014."""
from __future__ import annotations

from experiments.learning.correction_bench import load_corpus, run_case, run_control


def test_frozen_correction_corpus_is_internally_consistent():
    corpus = load_corpus()
    assert corpus["version"] == "corrections-v1"
    assert len(corpus["verified_cases"]) == 10
    assert len(corpus["controls"]) == 5
    assert all(case["heldout"] for case in corpus["verified_cases"])


def test_one_verified_case_promotes_and_its_controls_are_refused():
    corpus = load_corpus()
    case = corpus["verified_cases"][0]
    promoted = run_case(case, 0, initialization="stable", replay=True)
    assert promoted["stage"] == "promoted" and promoted["promoted"]
    assert promoted["heldout_correct"] == promoted["heldout_total"] == len(case["heldout"])
    assert promoted["stable_changed"]

    rejected = run_case(case, 0, initialization="fresh", replay=False)
    assert rejected["stage"] == "candidate_rejected" and not rejected["stable_changed"]

    control = next(c for c in corpus["controls"] if c["id"] == "false-arithmetic")
    refused = run_control(control, 0)
    assert refused["matched"] and refused["stage"] == "refused_unverified"
    assert refused["new_candidates"] == 0 and refused["fast_delta_norm"] == 0.0
