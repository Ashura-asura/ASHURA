"""Arithmetic specialist skills (HARN/Phase 7).

Public API used by `brain.controller`:
- `exact` module: exact evaluation and independent verification
- `parser` helpers: extract expression from natural language

Neural experts are optional and only loaded when checkpoints exist.
"""

from . import exact
from .parser import extract_expression, is_pure_arithmetic
from .neural_expert import NeuralAdditionExpert, try_neural_addition

__all__ = [
    "exact",
    "extract_expression",
    "is_pure_arithmetic",
    "NeuralAdditionExpert",
    "try_neural_addition",
]
