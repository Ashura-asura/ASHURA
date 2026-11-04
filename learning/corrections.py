"""Natural-language correction parsing and independent verification (Phase 3, P05/P06/P07).

A user correction is first a *record of what the user said*. It becomes a learning signal only
when ASHURA can check the claim independently. The only claims ASHURA can currently verify without
another model are exact arithmetic equations; everything else stays `user_provided`.

    python -m learning.corrections "actually, 6*7 = 42"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from skills.arithmetic import exact

_PREFIX = re.compile(
    r"^\s*(?:actually|correction|no|nope|wrong|incorrect|that'?s\s+(?:wrong|incorrect)|"
    r"the\s+correct\s+(?:answer|value)\s+is)\b\s*[,:;\-\u2014]?\s*", re.IGNORECASE)
_ARITH = re.compile(
    r"^(?P<lhs>(?:[0-9+\-*/%^().\s]|sqrt)+?)\s*(?:==|=|\bis\b)\s*(?P<rhs>-?\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE)
_FACT = re.compile(r"^(?P<key>.+?)\s+(?:is|are|should\s+be|=)\s+(?P<value>.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class Correction:
    text: str
    kind: str                 # "arithmetic" | "fact" | "unparsed"
    key: str                  # what the claim is about (expression or subject)
    value: str                # what the user asserts
    state: str                # "verified" | "failed" | "unavailable"
    method: str
    reason: str
    expected: str | None = None

    @property
    def verified(self) -> bool:
        return self.state == "verified"

    def to_experience(self):
        """The independently verified correction as a learning record, or None if unverified."""
        if not self.verified:
            return None
        from memory.episodic import Experience
        return Experience(self.key, self.value,
                          task_category="arithmetic" if self.kind == "arithmetic" else "general",
                          source="user_correction_verified",
                          verification_status="verified",
                          verification_method=self.method,
                          outcome="corrected")

    def as_dict(self) -> dict:
        return {"kind": self.kind, "key": self.key, "value": self.value,
                "state": self.state, "method": self.method, "reason": self.reason,
                "expected": self.expected}


def _strip_prefix(text: str) -> str:
    return _PREFIX.sub("", text.strip()).strip().rstrip(".!?")


def _canonical(v: Fraction) -> str:
    return str(v.numerator) if v.denominator == 1 else f"{v.numerator}/{v.denominator}"


def _arithmetic(lhs: str, rhs: str, text: str) -> Correction:
    lhs = lhs.strip()
    if not re.search(r"[+\-*/%^]|\bsqrt\b", lhs, re.IGNORECASE):
        return Correction(text, "unparsed", text, "", "unavailable",
                          "no independent verifier", "not an arithmetic equation")
    try:
        left = exact.evaluate(lhs)
        right = exact.evaluate(rhs)
    except (ArithmeticError, ValueError, RecursionError, MemoryError) as e:
        return Correction(text, "arithmetic", lhs, rhs, "unavailable",
                          "exact arithmetic", f"expression could not be evaluated: {e}")
    if not isinstance(left, Fraction) or not isinstance(right, Fraction):
        return Correction(text, "arithmetic", lhs, rhs, "unavailable",
                          "exact arithmetic", "not a scalar arithmetic equation")
    # Independent cross-check: exact Fraction evaluation must agree with Decimal(60).
    ok, note = exact.verify(lhs, left)
    if ok is None:
        return Correction(text, "arithmetic", lhs, rhs, "unavailable",
                          "exact arithmetic", f"no independent cross-check: {note}")
    if not ok:
        return Correction(text, "arithmetic", lhs, rhs, "failed",
                          "exact arithmetic + Decimal(60)", f"independent check disagrees: {note}")
    claimed = left == right
    true_value, claimed_value = _canonical(left), _canonical(right)
    return Correction(text, "arithmetic", lhs, claimed_value,
                      "verified" if claimed else "failed",
                      "exact arithmetic + Decimal(60) cross-check",
                      "equation is true" if claimed else
                      f"equation is false: {lhs} = {true_value}, not {claimed_value}",
                      true_value)


def _fact(key: str, value: str, text: str, prior: str | None) -> Correction:
    key, value = key.strip(" ,;"), value.strip(" ,;")
    if not key or not value or not re.search(r"\w", key):
        return Correction(text, "unparsed", text, "", "unavailable",
                          "no independent verifier", "could not isolate a factual claim")
    reason = "a user assertion is evidence of what the user said, not independent truth"
    if prior:
        from learning.compare import answers_agree
        reason += "; agrees with the prior answer" if answers_agree(key, value, prior) \
            else "; contradicts the prior answer"
    return Correction(text, "fact", key, value, "unavailable",
                      "user assertion; factual truth not independently verified", reason)


def parse_correction(text: str, prior: str | None = None) -> Correction:
    """Parse a correction and classify how far ASHURA can actually verify it.

    Arithmetic equations are checked by two independent evaluators. Factual claims stay
    `unavailable` even when they contradict stored memory: memory is not independent evidence for
    itself, and a user repeating a claim does not make it true.
    """
    claim = _strip_prefix(text)
    m = _ARITH.match(claim)
    if m:
        return _arithmetic(m.group("lhs"), m.group("rhs"), text)
    m = _FACT.match(claim)
    if m and not re.fullmatch(r"-?\d+(?:\.\d+)?", m.group("key").strip()):
        return _fact(m.group("key"), m.group("value"), text, prior)
    return Correction(text, "unparsed", claim, "", "unavailable",
                      "no independent verifier", "claim form not recognised")


if __name__ == "__main__":
    import sys
    print(parse_correction(" ".join(sys.argv[1:]) or "actually, 6*7 = 42").as_dict())
