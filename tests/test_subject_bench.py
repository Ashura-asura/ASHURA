"""Frozen subject suite and scoring regression tests (no real model needed)."""
from __future__ import annotations

from pathlib import Path

from evaluation.subject_bench import (
    CATEGORIES,
    compare,
    final_answer,
    load_suite,
    rubric_coverage,
    score_item,
    suite_sha256,
)

SUITE = "evaluation/benchmarks/subject_tutor_v1.jsonl"
SUITE_SHA256 = "efb3c2cbee93f87ecd5704a9f710d68abf0c31c4e0e9a98e7a85160008fb3410"


def test_subject_suite_is_frozen_and_balanced():
    items = load_suite(SUITE)
    assert len(items) == 42
    assert suite_sha256(SUITE) == SUITE_SHA256
    assert {item["category"] for item in items} == set(CATEGORIES)
    assert {category: sum(1 for item in items if item["category"] == category)
            for category in CATEGORIES} == {category: 6 for category in CATEGORIES}
    assert len({item["id"] for item in items}) == len(items)
    assert all(item["accept"] for item in items)
    branch = next(item for item in items if item["id"] == "prg-04")
    assert "git branch" not in branch["accept"]          # creates but does not switch


def test_final_answer_extraction_prefers_the_final_line():
    assert final_answer("Some reasoning.\nFinal answer: 6 N") == ("6 N", True)
    assert final_answer("**Final answer:** 512") == ("512", True)
    assert final_answer("The answer is 6 N.") == ("The answer is 6 N.", False)


def test_scoring_requires_the_correct_answer_and_two_rubric_terms():
    item = next(item for item in load_suite(SUITE) if item["id"] == "phy-01")
    good = score_item("Final answer: 6 N\nNewton's second law gives the product F = ma.", item)
    assert good["format_ok"] and good["answer_correct"] and good["quality"]
    assert good["rubric_coverage"] == 1.0

    wrong = score_item("Final answer: 5 N\nNewton's second law gives the product F = ma.", item)
    assert wrong["format_ok"] and not wrong["answer_correct"] and not wrong["quality"]

    echoed = score_item("Final answer: a 2 kg block experiences a net force that gives it an "
                        "acceleration of 3 m/s^2", item)
    assert not echoed["answer_correct"]


def test_rubric_strips_prompt_echo():
    item = next(item for item in load_suite(SUITE) if item["id"] == "phy-01")
    # The prompt itself contains "mass" and "acceleration"; the rubric terms are different.
    assert rubric_coverage("Final answer: 6 N. mass and acceleration.", item) == 0.0
    assert rubric_coverage("Final answer: 6 N. Newton's second law gives the product.", item) == 1.0


def test_compare_reports_a_paired_win():
    reference = {"model": "base", "n": 4, "rows": [
        {"id": "a", "quality": False, "answer_correct": False, "strict_correct": False},
        {"id": "b", "quality": False, "answer_correct": False, "strict_correct": False},
        {"id": "c", "quality": False, "answer_correct": False, "strict_correct": False},
        {"id": "d", "quality": False, "answer_correct": False, "strict_correct": False},
    ]}
    candidate = {"model": "new", "n": 4, "rows": [
        {"id": "a", "quality": True, "answer_correct": True, "strict_correct": True},
        {"id": "b", "quality": True, "answer_correct": True, "strict_correct": True},
        {"id": "c", "quality": True, "answer_correct": True, "strict_correct": True},
        {"id": "d", "quality": True, "answer_correct": True, "strict_correct": True},
    ]}
    result = compare({"base": reference, "new": candidate}, "base")
    assert result["new"]["quality"] == {"wins": 4, "losses": 0, "ties": 0, "p_value": 0.125}
    assert result["new"]["verdict"] == "no detectable difference from reference"


def test_suite_hash_matches_the_committed_file():
    assert suite_sha256(SUITE) == SUITE_SHA256


def test_suite_hash_is_independent_of_checkout_line_endings(tmp_path):
    canonical = Path(SUITE).read_bytes().replace(b"\r\n", b"\n")
    crlf = tmp_path / "subject_tutor_v1_crlf.jsonl"
    crlf.write_bytes(canonical.replace(b"\n", b"\r\n"))
    assert suite_sha256(str(crlf)) == SUITE_SHA256
