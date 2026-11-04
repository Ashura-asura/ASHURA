"""Structured answer comparison (P19/P20/P26).

Token overlap alone is not understanding. This module extracts comparable values (numbers, dates,
identifiers and simple units), normalises them, and compares negation within the clause it applies
to. It is deliberately rule-based and conservative: an unrecognised paraphrase becomes a conflict
for review, never a silent merge.

Known limits (documented in research/failures.md): no general synonymy, no relation extraction,
limited number-word grammar, and unit conversion only for the dimensions listed below.
"""
from __future__ import annotations

import re
from functools import lru_cache
from decimal import Decimal, InvalidOperation

_TOKEN = re.compile(r"\w+", re.UNICODE)

_STOP = frozenset("""a an the is are was were be been being am of for to in on at by with from as that this these those it its
it's and or but so then than there here what which who whom whose when where why how do does did has have had will would can
could should may might must shall i you he she we they me my your our their""".split())
_NEG = frozenset("""not no never none cannot n't isnt arent wasnt werent dont doesnt didnt wont without neither nor
rarely hardly barely lacks lack lacking fails fail failed""".split())

_UNIT_ALIASES = {
    # length -> metres
    "km": ("length", "1000"), "kilometer": ("length", "1000"), "kilometers": ("length", "1000"),
    "kilometre": ("length", "1000"), "kilometres": ("length", "1000"),
    "m": ("length", "1"), "meter": ("length", "1"), "meters": ("length", "1"),
    "metre": ("length", "1"), "metres": ("length", "1"),
    "cm": ("length", "0.01"), "centimeter": ("length", "0.01"), "centimeters": ("length", "0.01"),
    "mm": ("length", "0.001"), "millimeter": ("length", "0.001"), "millimeters": ("length", "0.001"),
    "mi": ("length", "1609.344"), "mile": ("length", "1609.344"), "miles": ("length", "1609.344"),
    "ft": ("length", "0.3048"), "foot": ("length", "0.3048"), "feet": ("length", "0.3048"),
    "in": ("length", "0.0254"), "inch": ("length", "0.0254"), "inches": ("length", "0.0254"),
    # mass -> grams
    "kg": ("mass", "1000"), "kilogram": ("mass", "1000"), "kilograms": ("mass", "1000"),
    "g": ("mass", "1"), "gram": ("mass", "1"), "grams": ("mass", "1"),
    "mg": ("mass", "0.001"), "milligram": ("mass", "0.001"), "milligrams": ("mass", "0.001"),
    "lb": ("mass", "453.59237"), "lbs": ("mass", "453.59237"), "pound": ("mass", "453.59237"),
    "pounds": ("mass", "453.59237"), "oz": ("mass", "28.349523125"), "ounce": ("mass", "28.349523125"),
    "ounces": ("mass", "28.349523125"),
    # time -> seconds
    "ms": ("time", "0.001"), "millisecond": ("time", "0.001"), "milliseconds": ("time", "0.001"),
    "s": ("time", "1"), "sec": ("time", "1"), "secs": ("time", "1"), "second": ("time", "1"),
    "seconds": ("time", "1"), "min": ("time", "60"), "mins": ("time", "60"), "minute": ("time", "60"),
    "minutes": ("time", "60"), "h": ("time", "3600"), "hr": ("time", "3600"), "hrs": ("time", "3600"),
    "hour": ("time", "3600"), "hours": ("time", "3600"), "day": ("time", "86400"), "days": ("time", "86400"),
    # volume -> litres
    "l": ("volume", "1"), "liter": ("volume", "1"), "liters": ("volume", "1"),
    "litre": ("volume", "1"), "litres": ("volume", "1"),
    "ml": ("volume", "0.001"), "milliliter": ("volume", "0.001"), "milliliters": ("volume", "0.001"),
    # temperature -> celsius (special-cased)
    "c": ("temperature", "c"), "celsius": ("temperature", "c"), "°c": ("temperature", "c"),
    "f": ("temperature", "f"), "fahrenheit": ("temperature", "f"), "°f": ("temperature", "f"),
    "percent": ("percent", "1"), "%": ("percent", "1"),
}

_NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000, "million": 1_000_000, "billion": 1_000_000_000}
_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}

_UNIT_RE = re.compile(
    r"(?<![\w.])(?P<num>-?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>°?[a-zA-Z%]+)?", re.UNICODE)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_MONTH_DATE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", re.IGNORECASE)
_DAY_MONTH_DATE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")\s+(\d{4})\b", re.IGNORECASE)
_ID_RE = re.compile(r"\b(?:[a-z]{1,4}[-_]?\d[\w-]*|\d+[a-z][\w-]*)\b", re.IGNORECASE)


_CONTRACTIONS = {
    "can't": "can not", "won't": "will not", "n't": " not", "don't": "do not",
    "doesn't": "does not", "didn't": "did not", "isn't": "is not", "aren't": "are not",
    "wasn't": "was not", "weren't": "were not",
}


def _text(text: str) -> str:
    s = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    for src, dst in _CONTRACTIONS.items():
        s = s.replace(src, dst)
    return s


@lru_cache(maxsize=8192)
def _tokens_cached(text: str) -> frozenset[str]:
    return frozenset(_TOKEN.findall(_text(text)))


def tokens(text: str) -> frozenset[str]:
    return _tokens_cached(text)


def _canon_number(value: Decimal) -> str:
    try:
        value = value.normalize()
    except InvalidOperation:
        return str(value)
    s = format(value, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _convert(value: Decimal, unit: str) -> str | None:
    meta = _UNIT_ALIASES.get(unit.lower())
    if not meta:
        return None
    dimension, factor = meta
    if dimension == "temperature":
        celsius = value if factor == "c" else (value - Decimal(32)) * Decimal(5) / Decimal(9)
        return f"{_canon_number(celsius)}c"
    if dimension == "percent":
        return f"{_canon_number(value)}%"
    return f"{_canon_number(value * Decimal(factor))}{dimension}"


def _number_word_value(words: list[str]) -> int | None:
    total = current = 0
    seen = False
    for w in words:
        if w in _NUMBER_WORDS:
            current += _NUMBER_WORDS[w]; seen = True
        elif w in _SCALES:
            current = (current or 1) * _SCALES[w]; total += current; current = 0; seen = True
        else:
            return None
    return total + current if seen else None


def _date_values(text: str) -> set[str]:
    out: set[str] = set()
    for y, m, d in _ISO_DATE.findall(text):
        try:
            out.add(f"date:{int(y):04d}-{int(m):02d}-{int(d):02d}")
        except ValueError:
            pass
    for m, d, y in _SLASH_DATE.findall(text):
        mi, di = int(m), int(d)
        if mi > 12 and di <= 12:          # day/month/year when the first field cannot be a month
            mi, di = di, mi
        out.add(f"date:{int(y):04d}-{mi:02d}-{di:02d}")
    for month, day, year in _MONTH_DATE.findall(text):
        out.add(f"date:{int(year):04d}-{_MONTHS[month.lower()]:02d}-{int(day):02d}")
    for day, month, year in _DAY_MONTH_DATE.findall(text):
        out.add(f"date:{int(year):04d}-{_MONTHS[month.lower()]:02d}-{int(day):02d}")
    return out


def extract_values(text: str) -> set[str]:
    """Digital, unit-bearing and identifier values, normalised for comparison.

    A plain number is kept; a number with a recognised unit is converted to a base unit so
    ``1.5 km`` equals ``1500 m``. Dates become ``date:YYYY-MM-DD``. Identifiers keep case folding.
    """
    text = _text(text)
    out: set[str] = _date_values(text)
    # Date components are not independent values: remove the matched spans before numbers.
    for pattern in (_ISO_DATE, _SLASH_DATE, _MONTH_DATE, _DAY_MONTH_DATE):
        text = pattern.sub(" ", text)
    for m in _UNIT_RE.finditer(text):
        raw, unit = m.group("num"), (m.group("unit") or "").lower()
        # A number followed by an ordinary word is not a unit-bearing value.
        if unit and unit not in _UNIT_ALIASES:
            out.add(f"num:{_canon_number(Decimal(raw))}")
            continue
        if unit:
            converted = _convert(Decimal(raw), unit)
            if converted:
                out.add(f"val:{converted}")
                continue
        out.add(f"num:{_canon_number(Decimal(raw))}")
    for word_match in re.finditer(r"\b((?:" + "|".join(list(_NUMBER_WORDS) + list(_SCALES)) + r")"
                                  r"(?:[\s-]+(?:" + "|".join(list(_NUMBER_WORDS) + list(_SCALES)) + r"))+)\b",
                                  text.lower()):
        words = re.split(r"[\s-]+", word_match.group(1))
        number = _number_word_value(words)
        if number is None:
            continue
        tail = text[word_match.end():word_match.end() + 12].strip().split(" ", 1)[0].lower()
        converted = _convert(Decimal(number), tail) if tail else None
        out.add(f"val:{converted}" if converted else f"num:{number}")
    out |= {f"id:{t.lower()}" for t in _ID_RE.findall(text)}
    return out


def _content(answer: str, question: str) -> set[str]:
    q = tokens(question)
    return {t for t in tokens(answer)
            if t not in _STOP and t not in _NEG and t not in q
            and not any(ch.isdigit() for ch in t)}


def _clauses(answer: str) -> list[str]:
    return [c for c in re.split(r"[.;!?]|\b(?:but|however|although|though|whereas)\b", _text(answer)) if c.strip()]


def negation_scope(answer: str, question: str = "") -> frozenset[str]:
    """Content/value tokens that fall inside a negated clause.

    This replaces token parity: "not the capital of France" negates the capital relation, while a
    separate positive clause is not cancelled by an unrelated negation.
    """
    scope: set[str] = set()
    for clause in _clauses(answer):
        clause_tokens = set(_TOKEN.findall(clause))
        if not clause_tokens & _NEG:
            continue
        scope |= _content(clause, question)
        for v in extract_values(clause):
            scope.add(v)
    return frozenset(scope)


def _negated(answer: str) -> bool:
    return any(set(_TOKEN.findall(c)) & _NEG for c in _clauses(answer))


def answer_similarity(question: str, first: str, second: str,
                      dup_similarity: float = 0.9, content_overlap: float = 0.75) -> float:
    """Continuous [0,1] similarity; 1.0 only when the answers agree under ``answers_agree``."""
    if answers_agree(question, first, second, dup_similarity, content_overlap):
        return 1.0
    v1 = extract_values(first) - extract_values(question)
    v2 = extract_values(second) - extract_values(question)
    if v1 or v2:
        return round(len(v1 & v2) / max(len(v1), len(v2)) * 0.5, 4)
    c1, c2 = _content(first, question), _content(second, question)
    if c1 or c2:
        base = len(c1 & c2) / len(c1 | c2) if (c1 | c2) else 0.0
        if negation_scope(first, question) != negation_scope(second, question):
            base *= 0.25
        return round(min(base, 0.9), 4)
    return round(jaccard(tokens(first), tokens(second)) * 0.5, 4)


def answers_agree(question: str, new: str, old: str, dup_similarity: float = 0.9,
                  content_overlap: float = 0.75) -> bool:
    """True only when two answers state the same thing according to the structured rules.

    Order matters: negation is checked before lexical similarity, because "4821" and "not 4821"
    otherwise share most of their tokens.
    """
    if not new.strip() or not old.strip():
        return False
    if " ".join(_TOKEN.findall(new.lower())) == " ".join(_TOKEN.findall(old.lower())):
        return True
    if negation_scope(new, question) != negation_scope(old, question):
        return False
    if jaccard(tokens(new), tokens(old)) >= dup_similarity:
        return True
    vn, vo = extract_values(new) - extract_values(question), extract_values(old) - extract_values(question)
    if vn or vo:
        return bool(vn) and vn == vo
    cn, co = _content(new, question), _content(old, question)
    if not cn or not co:
        return False
    return len(cn & co) / min(len(cn), len(co)) >= content_overlap


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


def surprise_from_prior(question: str, actual: str, prior: str | None,
                        dup_similarity: float = 0.9) -> float:
    """Prediction error in [0,1], continuous rather than binary.

    No prior belief means no surprise (novelty covers that case). A different answer with shared
    values/words produces a proportional error; an unrelated answer is 1.0.
    """
    if not prior:
        return 0.0
    return round(1.0 - answer_similarity(question, actual, prior, dup_similarity), 4)
