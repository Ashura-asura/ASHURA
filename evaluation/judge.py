"""Answer judge for the benchmark suites (fixes F-005: the old substring judge was gameable).

Three defences against false passes:
  1. Echo stripping - any run of >= 3 words copied from the prompt is removed before matching, so a model
     that just repeats the question cannot match an answer that happens to occur in the question.
  2. Whole-token matching - "391" does not match "3910" or "1,391"; "12" does not match "12.5".
  3. A strict mode that only credits the answer if it is the model's *first* line (or first word for
     items with  "match": "first_word"), so "No ... but yes" or a long ramble that mentions the answer
     in passing is not counted.

Two scores are reported side by side. `lenient` = answer appears anywhere after echo stripping.
`strict` = answer appears in the first non-empty line (and first word for yes/no items). Use strict for
NGR promotion decisions; use the gap between them to see how chatty a model is.
"""
from __future__ import annotations

import re
import unicodedata

_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|\w+", re.UNICODE)
_SEP = "\x00"


def _norm_token(t: str) -> str:
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", t):      # 1,024 -> 1024
        t = t.replace(",", "")
    if re.fullmatch(r"-?\d+\.\d+", t):                    # 4.000 -> 4; 0.250 -> 0.25
        t = t.rstrip("0").rstrip(".")
    return t


def words(text: str) -> list[str]:
    return [_norm_token(t) for t in _TOKEN.findall(text)]


def strip_echo(out_words: list[str], prompt: str, min_run: int = 3) -> list[str]:
    """Replace every run of >= min_run words that also occurs contiguously in the prompt by a separator."""
    pw = words(prompt)
    grams = {tuple(pw[i:i + min_run]) for i in range(len(pw) - min_run + 1)}
    marked = [False] * len(out_words)
    for i in range(len(out_words) - min_run + 1):
        if tuple(out_words[i:i + min_run]) in grams:
            for j in range(i, i + min_run):
                marked[j] = True
    cleaned: list[str] = []
    for w, m in zip(out_words, marked):
        if m:
            if cleaned and cleaned[-1] != _SEP:
                cleaned.append(_SEP)
        else:
            cleaned.append(w)
    return cleaned


def _contains(haystack: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def _first_line(text: str) -> str:
    for line in text.splitlines():
        if line.strip():
            return line
    return ""


def judge(output: str, item: dict, prompt: str | None = None, strict: bool = False) -> bool:
    prompt = prompt if prompt is not None else item.get("prompt", "")
    accepts = [words(a) for a in item["accept"]]
    if strict:
        cleaned = strip_echo(words(_first_line(output)), prompt)
        cleaned = [w for w in cleaned if w != _SEP]
        if item.get("match") == "first_word":
            return bool(cleaned) and any(len(a) == 1 and cleaned[0] == a[0] for a in accepts)
        return any(_contains(cleaned, a) for a in accepts)
    cleaned = strip_echo(words(output), prompt)
    return any(_contains(cleaned, a) for a in accepts)


def judge_both(output: str, item: dict, prompt: str | None = None) -> dict:
    return {"lenient": judge(output, item, prompt, strict=False), "strict": judge(output, item, prompt, strict=True)}
