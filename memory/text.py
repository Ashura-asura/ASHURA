"""Text normalisation shared by the memory layer (kept dependency-free to avoid import cycles)."""
from __future__ import annotations

import re


def normalize(text: str) -> str:
    """Lower-case and collapse whitespace; the canonical form used to compare questions."""
    return re.sub(r"\s+", " ", text.strip().lower())
