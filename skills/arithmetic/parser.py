"""Extract an arithmetic expression from natural language (heuristic, conservative)."""
from __future__ import annotations

import re

_WORDS = [(r"\bdivided by\b", "/"), (r"\bmultiplied by\b", "*"), (r"\btimes\b", "*"), (r"\bplus\b", "+"),
          (r"\bminus\b", "-"), (r"\bmodulo\b", "%"), (r"\bto the power of\b", "**"), (r"\bsquare root of\b", "sqrt")]
_SPAN = re.compile(r"(?:sqrt\s*\(|[\d.()\s+\-*/%^<>=!])+")
_FILLER = {"what", "is", "whats", "calculate", "compute", "solve", "evaluate", "the", "result", "of", "answer",
           "please", "equals", "equal", "how", "much", "to", "me", "tell", "can", "you", "give", "a", "and"}


def _normalise(text: str) -> str:
    t = text.lower().replace("×", "*").replace("÷", "/").replace("−", "-").replace("'", "")
    for pat, rep in _WORDS:
        t = re.sub(pat, f" {rep} ", t)
    t = re.sub(r"sqrt\s+(\d[\d.]*)", r"sqrt(\1)", t)
    return t


def extract_expression(text: str) -> str | None:
    best = None
    for m in _SPAN.finditer(_normalise(text)):
        s = m.group().strip()
        if re.search(r"\d", s) and re.search(r"[+\-*/%^<>=!]|sqrt", s[1:] if s[:1] in "+-" else s):
            if best is None or len(s) > len(best):
                best = s
    if best and best.count("(") > best.count(")"):
        best += ")" * (best.count("(") - best.count(")"))
    return best


def is_pure_arithmetic(text: str) -> bool:
    """True when the request is just 'compute this' - a cheap skill can handle it alone."""
    expr = extract_expression(text)
    if not expr:
        return False
    rest = _normalise(text).replace(expr, " ") if expr in _normalise(text) else _normalise(text)
    words = re.findall(r"[a-z]+", rest)
    return all(w in _FILLER for w in words) and len(words) <= 6
