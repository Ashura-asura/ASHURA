"""Extract an arithmetic expression from natural language (heuristic, conservative)."""
from __future__ import annotations

import re

_WORDS = [(r"\bdivided by\b", "/"), (r"\bmultiplied by\b", "*"), (r"\btimes\b", "*"), (r"\bplus\b", "+"),
          (r"\bminus\b", "-"), (r"\bmodulo\b", "%"), (r"\bto the power of\b", "**"), (r"\bsquare root of\b", "sqrt")]
_SPAN = re.compile(r"(?:sqrt\s*\(|[\d.()\s+\-*/%^<>=!])+")
_FILLER = {"what", "is", "whats", "calculate", "compute", "solve", "evaluate", "the", "result", "of", "answer",
           "please", "equals", "equal", "how", "much", "to", "me", "tell", "can", "you", "give", "a", "and"}


# Things that look like subtraction/division but are almost never arithmetic requests. Treating them as
# arithmetic would inject a wrong "verified" number (e.g. 2026-11-05 -> 2010) into the answer and memory.
# Only unambiguous shapes (no spaces, 4-digit years, 3-3-4 phone numbers) are masked, so "100-50-25" and
# "2026 - 11 - 05" are still computed.
_NOT_ARITHMETIC = re.compile(
    r"(?<![\d.])(?:\d{4}-(?:0?[1-9]|1[0-2])-(?:0?[1-9]|[12]\d|3[01])"       # ISO date 2026-11-05
    r"|(?:0?[1-9]|[12]\d|3[01])/(?:0?[1-9]|1[0-2])/\d{4}"                      # 05/11/2026
    r"|(?:0?[1-9]|1[0-2])/(?:0?[1-9]|[12]\d|3[01])/\d{4}"                      # 11/05/2026
    r"|\d{3}[-.]\d{3}[-.]\d{4})(?![\d.])")                                    # 555-123-4567


def _normalise(text: str) -> str:
    t = _NOT_ARITHMETIC.sub(" ", text).lower().replace("×", "*").replace("÷", "/").replace("−", "-").replace("'", "")
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
