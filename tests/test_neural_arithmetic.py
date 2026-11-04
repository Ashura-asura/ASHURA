import os
from fractions import Fraction

import pytest

from brain.controller import Controller
from foundation.language_model import EchoModel
from learning.ama import AMA
from memory.database import Database
from skills.arithmetic import try_neural_addition
from skills.arithmetic.neural_expert import AdditionExpertConfig, NeuralAdditionExpert


def test_try_neural_addition_returns_none_without_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(tmp_path / "missing.npz"))
    assert try_neural_addition("2+3") is None


def test_try_neural_addition_with_checkpoint(tmp_path, monkeypatch):
    expert = NeuralAdditionExpert()
    expert.train(AdditionExpertConfig(seed=0, a_min=-20, a_max=20, b_min=-20, b_max=20), n=8000)

    ckpt = tmp_path / "addition.npz"
    expert.save(str(ckpt))
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(ckpt))

    got = try_neural_addition("2+3")
    assert got == Fraction(5, 1)


def ctl():
    return Controller(EchoModel(), ama=AMA(Database()))


def test_controller_uses_neural_addition_when_available(tmp_path, monkeypatch):
    expert = NeuralAdditionExpert()
    expert.train(AdditionExpertConfig(seed=0, a_min=-20, a_max=20, b_min=-20, b_max=20), n=8000)

    ckpt = tmp_path / "addition.npz"
    expert.save(str(ckpt))
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(ckpt))

    r = ctl().handle("what is 2+3?")
    assert r.text == "5"
    assert r.verified is True
    assert r.trace.step("arithmetic").note == "exact evaluator; neural candidate agrees"
    assert r.trace.step("neural_arithmetic_candidate").ok is True


def test_controller_falls_back_to_exact_evaluator_for_non_addition(tmp_path, monkeypatch):
    expert = NeuralAdditionExpert()
    expert.train(AdditionExpertConfig(seed=0, a_min=-20, a_max=20, b_min=-20, b_max=20), n=8000)

    ckpt = tmp_path / "addition.npz"
    expert.save(str(ckpt))
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(ckpt))

    r = ctl().handle("what is 2*3?")
    assert r.text == "6"
    assert r.verified is True
    assert r.trace.step("arithmetic").note == "exact evaluator"
