"""AMA - Adaptive Memory Admission (spec 6). EXPERIMENTAL: weights are uncalibrated.

A(x) = wN*N + wS*S + wR*R + wU*U - wC*C - wK*K

Design rules taken from the spec:
  * unverified generated claims are never treated as established truth (no facts, no DREAM queue);
  * contradictions are kept as evidence, never silently deleted;
  * every decision and its reason is logged.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field

from memory.database import Database
from memory.episodic import RELIABILITY_BY_STATUS, EpisodicMemory, Experience, content_hash, normalize
from memory.fts import FTS5Index
from memory.semantic import SemanticMemory

_TOK = re.compile(r"\w+", re.UNICODE)
VERIFIED_STATUSES = {"verified", "user_corrected", "trusted_material"}


def tokens(text: str) -> set[str]:
    return set(_TOK.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a or b) else 1.0


# ---- answer comparison (fixes F-002: token overlap alone flagged 63% of correct rewordings as conflicts) ----
_STOP = frozenset("""a an the is are was were be been being am of for to in on at by with from as that this these those it its
it's and or but so then than there here what which who whom whose when where why how do does did has have had will would can
could should may might must shall i you he she we they me my your our their""".split())
_NEG = frozenset("not no never none cannot n't isnt arent wasnt werent dont doesnt didnt wont without neither nor".split())


def _answer_values(answer: str, question: str) -> set[str]:
    """Digit-bearing tokens of the answer (codes, numbers, dates) that are not just repeating the question.

    Tokens already present in the question are entity identifiers ("project P7"), not answer values.
    """
    q = tokens(question)
    return {t for t in tokens(answer) if any(ch.isdigit() for ch in t) and t not in q}


def _content(answer: str, question: str) -> set[str]:
    q = tokens(question)
    return {t for t in tokens(answer) if t not in _STOP and t not in _NEG and t not in q and not any(ch.isdigit() for ch in t)}


def _negated(answer: str) -> bool:
    toks = _TOK.findall(answer.lower().replace("n't", "nt").replace("\u2019t", "t"))
    return sum(t in _NEG for t in toks) % 2 == 1


def answers_agree(question: str, new: str, old: str, dup_similarity: float = 0.9, content_overlap: float = 0.75) -> bool:
    """True if two answers to the same question say the same thing (possibly worded differently).

    1. Near-identical token sets agree (formatting noise, punctuation).
    2. Otherwise a negation mismatch means they disagree ("is 4821" vs "is not 4821").
    3. If either contains answer values (numbers/codes), the value sets must be identical; a value present
       in only one answer (or an extra hedge like "4821 or 9999") is treated as disagreement - the safe direction.
    4. With no values, agree if the non-stopword content words overlap strongly (overlap coefficient).

    Known limits (documented in research/failures.md F-002): number words vs digits ("four" vs 4), units
    ("5 km" vs "5 miles"), and synonyms/paraphrase without shared content words are not understood; those
    cases fall back to "disagree" and are stored as evidence for review, never silently merged.
    """
    if jaccard(tokens(new), tokens(old)) >= dup_similarity:
        return True
    if _negated(new) != _negated(old):
        return False
    vn, vo = _answer_values(new, question), _answer_values(old, question)
    if vn or vo:
        return bool(vn) and vn == vo
    cn, co = _content(new, question), _content(old, question)
    if not cn or not co:
        return False
    return len(cn & co) / min(len(cn), len(co)) >= content_overlap


@dataclass
class AMAConfig:
    w_novelty: float = 1.0
    w_surprise: float = 0.5
    w_reliability: float = 1.0
    w_utility: float = 0.7
    w_conflict: float = 0.8
    w_cost: float = 0.3
    discard_threshold: float = 0.45
    duplicate_similarity: float = 0.9
    reliable_fact_threshold: float = 0.8
    neural_memory_repeats: int = 3     # repeated useful association -> neural memory queue

    @classmethod
    def from_dict(cls, d: dict) -> "AMAConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Features:
    novelty: float = 1.0
    surprise: float = 0.0
    reliability: float = 0.2
    utility: float = 0.3
    conflict: float = 0.0
    cost: float = 0.0
    duplicate_of: str | None = None
    conflicts_with: list[str] = field(default_factory=list)


@dataclass
class Decision:
    decision: str                  # ADMITTED | MERGED | DISCARDED | REVIEW_REQUIRED
    score: float
    reason: str
    exp_id: str | None = None
    destinations: list[str] = field(default_factory=list)
    features: Features = field(default_factory=Features)


def surprise_from_prior(question: str, actual: str, prior: str | None, dup_similarity: float = 0.9) -> float:
    """Prediction error in [0,1]: 0 if memory already believed this answer, 1 if it believed something else.

    `prior` is what memory returned for this exact question before answering. With no prior belief there was
    nothing to be surprised about (0.0) - that case is already scored by novelty, not surprise.
    """
    if not prior:
        return 0.0
    return 0.0 if answers_agree(question, actual, prior, dup_similarity) else 1.0


class AMA:
    def __init__(self, db: Database, cfg: AMAConfig | None = None):
        self.db, self.cfg = db, cfg or AMAConfig()
        self.episodic = EpisodicMemory(db)
        self.semantic = SemanticMemory(db)
        self.fts = FTS5Index(db)

    # ---- feature extraction -------------------------------------------------------------
    def analyse(self, x: Experience, surprise: float = 0.0, utility: float | None = None) -> Features:
        f = Features(surprise=max(0.0, min(1.0, surprise)), reliability=x.reliability or 0.0)
        f.cost = min(1.0, len(x.text) / 2000.0)
        # exact duplicate
        dup = self.episodic.find_by_hash(content_hash(x.input, x.output))
        if dup:
            f.duplicate_of, f.novelty = dup.id, 0.0
            return f
        # same question, different answer?  (checked BEFORE near-duplicate merging, because two
        # answers that differ by one token have very high overall similarity)
        for old in self.episodic.find_by_input(x.input, x.task_category):
            if answers_agree(x.input, x.output, old.output, self.cfg.duplicate_similarity):
                f.duplicate_of, f.novelty = old.id, 0.0       # same answer, possibly reworded -> merge
                return f
            f.conflicts_with.append(old.id)
        if f.conflicts_with:
            f.conflict = 1.0
        # novelty vs nearest existing records
        x_tok, best, best_id = tokens(x.text), 0.0, None
        for mid, _ in self.fts.search(x.text, limit=5):
            old = self.episodic.get(mid)
            if old and old.task_category == x.task_category:
                s = jaccard(x_tok, tokens(old.text))
                if s > best:
                    best, best_id = s, mid
        f.novelty = 1.0 - best
        if best >= self.cfg.duplicate_similarity and not f.conflicts_with:
            f.duplicate_of = best_id
        # utility: heuristic placeholder (documented as uncalibrated)
        f.utility = utility if utility is not None else min(1.0, 0.3 + 0.4 * (f.reliability >= self.cfg.reliable_fact_threshold)
                                                           + 0.3 * (x.outcome in {"success", "corrected"}))
        return f

    def score(self, f: Features) -> float:
        c = self.cfg
        return (c.w_novelty * f.novelty + c.w_surprise * f.surprise + c.w_reliability * f.reliability
                + c.w_utility * f.utility - c.w_conflict * f.conflict - c.w_cost * f.cost)

    # ---- decision -----------------------------------------------------------------------
    def admit(self, x: Experience, surprise: float = 0.0, utility: float | None = None) -> Decision:
        f = self.analyse(x, surprise, utility)
        s = self.score(f)

        if f.duplicate_of:
            old = self.episodic.get(f.duplicate_of)
            self.episodic.bump_repeat(f.duplicate_of, x.verification_status if x.verification_status in VERIFIED_STATUSES else None)
            dests = ["episodic(merge)"]
            new_count = (old.repeat_count + 1) if old else 2
            if new_count >= self.cfg.neural_memory_repeats and (old and old.reliability >= self.cfg.reliable_fact_threshold):
                self._enqueue(f.duplicate_of, "neural_memory"); dests.append("neural_memory_queue")
            return self._log(Decision("MERGED", s, f"duplicate of {f.duplicate_of}", f.duplicate_of, dests, f))

        if f.conflicts_with:
            return self._handle_conflict(x, f, s)

        if s < self.cfg.discard_threshold:
            return self._log(Decision("DISCARDED", s, f"score {s:.2f} < {self.cfg.discard_threshold}", None, [], f))

        return self._log(self._store(x, f, s, index=True))

    def _handle_conflict(self, x: Experience, f: Features, s: float) -> Decision:
        olds = [o for o in (self.episodic.get(i) for i in f.conflicts_with) if o]
        best_old = max((o.reliability for o in olds), default=0.0)
        if x.reliability > best_old:
            # Stronger evidence supersedes: keep the old records as history, remove them from search.
            for o in olds:
                self.fts.delete(o.id)
            d = self._store(x, f, s, index=True)
            d.reason = f"conflict resolved by stronger evidence (reliability {x.reliability:.2f} > {best_old:.2f}); " \
                       f"{len(olds)} older record(s) de-indexed but retained"
            return self._log(d)
        # Weaker or equal evidence: keep as conflicting evidence, do NOT make it retrievable.
        d = self._store(x, f, s, index=False)
        d.decision = "REVIEW_REQUIRED"
        d.reason = f"conflicts with {len(olds)} record(s) of >= reliability ({best_old:.2f}); stored as evidence only"
        return self._log(d)

    def _store(self, x: Experience, f: Features, s: float, index: bool) -> Decision:
        x.related_ids = sorted(set(x.related_ids) | set(f.conflicts_with))
        self.episodic.add(x)
        dests = ["episodic"]
        if index:
            self.fts.add(x.id, x.text); dests.append("fts5")
            if x.reliability >= self.cfg.reliable_fact_threshold:
                self.semantic.add_fact(x.text, x.id, x.reliability); dests.append("semantic")
        if x.verification_status in VERIFIED_STATUSES and not f.conflicts_with:
            self._enqueue(x.id, "dream"); dests.append("dream_queue")
        return Decision("ADMITTED", s, f"score {s:.2f}", x.id, dests, f)

    def _enqueue(self, exp_id: str, queue: str) -> None:
        self.db.conn.execute("INSERT OR REPLACE INTO dream_queue(exp_id, queue, ts) VALUES (?,?,?)", (exp_id, queue, time.time()))
        self.db.conn.commit()

    def _log(self, d: Decision) -> Decision:
        self.db.conn.execute(
            "INSERT INTO admission_log(ts, exp_id, decision, score, features, reason) VALUES (?,?,?,?,?,?)",
            (time.time(), d.exp_id, d.decision, d.score, json.dumps(asdict(d.features)), d.reason))
        self.db.conn.commit()
        return d


class StoreEverything:
    """Baseline for the AMA experiment: unconditional storage + indexing (spec 21)."""

    def __init__(self, db: Database):
        self.db = db
        self.episodic = EpisodicMemory(db)
        self.fts = FTS5Index(db)

    def admit(self, x: Experience, **_) -> Decision:
        self.episodic.add(x)
        self.fts.add(x.id, x.text)
        return Decision("ADMITTED", 0.0, "baseline: store everything", x.id, ["episodic", "fts5"])
