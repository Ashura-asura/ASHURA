"""AMA - Adaptive Memory Admission (spec 6). EXPERIMENTAL: weights are uncalibrated.

A(x) = wN*N + wS*S + wR*R + wU*U - wC*C - wK*K

Design rules taken from the spec:
  * unverified generated claims are never treated as established truth (no facts, no DREAM queue);
  * contradictions are kept as evidence, never silently deleted;
  * every decision and its reason is logged.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from learning.compare import (answer_similarity, answers_agree, extract_values, jaccard,  # noqa: F401
                              negation_scope, surprise_from_prior, tokens)
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience, content_hash
from memory.fts import FTS5Index
from memory.semantic import SemanticMemory

# Only independently verified records may enter verified learning queues (P03).
VERIFIED_STATUSES = {"verified"}

# Retrieval labels: the model must be told what kind of evidence it is being given (P01/P02).
# Utility feedback (P18). These affect *usefulness* ranking only, never reliability or truth.
FEEDBACK_WEIGHTS = {
    "retrieval_hit": 0.05,
    "user_accepted": 0.30,
    "user_rejected": -0.30,
    "task_completed": 0.20,
    "corrected": -0.40,
    "repeated_use": 0.10,
}

PROVENANCE_LABELS = {
    "verified": "verified fact",
    "trusted_material": "trusted material, not independently verified",
    "user_provided": "user-provided, not independently verified",
    "user_corrected": "user correction, not independently verified",
    "unverified": "unverified experience",
}


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
    retrieval_min_reliability: float = 0.5   # unverified model answers (0.2) are not retrieval evidence
    neural_memory_repeats: int = 3     # repeated useful association -> neural memory queue
    record_retrieval_feedback: bool = False  # opt-in: record retrieval hits for utility measurement

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


@dataclass(frozen=True)
class RetrievalItem:
    """One search result with the provenance needed to interpret it safely (P01/P02)."""
    experience: Experience
    label: str
    conflict: bool = False

    @property
    def reliability(self) -> float:
        return self.experience.reliability

    @property
    def provenance(self) -> dict:
        return {
            "source": self.experience.source,
            "verification_status": self.experience.verification_status,
            "verification_method": self.experience.verification_method,
            "timestamp": self.experience.ts,
            "reliability": self.experience.reliability,
            "conflict": self.conflict,
        }

    @property
    def prompt_line(self) -> str:
        suffix = "; conflicting evidence on record" if self.conflict else ""
        return f"Memory ({self.label}{suffix}): {self.experience.text.strip()}"


class AMA:
    def __init__(self, db: Database, cfg: AMAConfig | None = None):
        self.db, self.cfg = db, cfg or AMAConfig()
        self.episodic = EpisodicMemory(db)
        self.semantic = SemanticMemory(db)
        self.fts = FTS5Index(db)

    # ---- utility feedback (P18) ---------------------------------------------------------
    def record_feedback(self, exp_id: str, event: str, value: float = 1.0, source: str = "user",
                        note: str = "", commit: bool = True) -> None:
        """Record a later usefulness signal. Does not alter truth/reliability (P18)."""
        if event not in FEEDBACK_WEIGHTS:
            raise ValueError(f"unknown feedback event {event!r}; expected one of {sorted(FEEDBACK_WEIGHTS)}")
        if not 0.0 <= float(value) <= 1.0:
            raise ValueError("feedback value must be in [0, 1]")
        if self.episodic.get(exp_id) is None:
            raise ValueError(f"experience {exp_id!r} does not exist")
        self.db.conn.execute(
            "INSERT INTO memory_feedback(ts, exp_id, event, value, source, note) VALUES (?,?,?,?,?,?)",
            (time.time(), exp_id, event, float(value), source, note))
        if commit:
            self.db.conn.commit()

    def utility_from_feedback(self, exp_id: str, default: float | None = None) -> float | None:
        """Utility [0,1] from accumulated feedback, or ``default`` when there is none."""
        rows = self.db.conn.execute(
            "SELECT event, value FROM memory_feedback WHERE exp_id = ?", (exp_id,)).fetchall()
        e = self.episodic.get(exp_id)
        repeats = max(0, (e.repeat_count if e else 1) - 1)
        if not rows and repeats == 0:
            return default
        delta = sum(FEEDBACK_WEIGHTS[r["event"]] * r["value"] for r in rows if r["event"] in FEEDBACK_WEIGHTS)
        delta += FEEDBACK_WEIGHTS["repeated_use"] * min(repeats, 3)
        return max(0.0, min(1.0, 0.3 + delta))

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
        # utility: measured feedback when available, otherwise the documented heuristic proxy
        measured = self.utility_from_feedback(x.id) if x.id else None
        f.utility = utility if utility is not None else (
            measured if measured is not None
            else min(1.0, 0.3 + 0.4 * (f.reliability >= self.cfg.reliable_fact_threshold)
                     + 0.3 * (x.outcome in {"success", "corrected"})))
        return f

    def score(self, f: Features) -> float:
        c = self.cfg
        return (c.w_novelty * f.novelty + c.w_surprise * f.surprise + c.w_reliability * f.reliability
                + c.w_utility * f.utility - c.w_conflict * f.conflict - c.w_cost * f.cost)

    # ---- retrieval ----------------------------------------------------------------------
    @staticmethod
    def provenance_label(e: Experience) -> str:
        return PROVENANCE_LABELS.get(e.verification_status, e.verification_status)

    def retrieve(self, query: str, limit: int = 3, min_reliability: float | None = None,
                 include_unverified: bool = False) -> list[RetrievalItem]:
        """Reliability-aware FTS5 retrieval.

        By default, records below ``retrieval_min_reliability`` (unverified model output) are not
        returned at all. Anything returned carries a provenance label and conflict flag, so an
        unverified experience can never silently masquerade as an established fact.
        """
        threshold = self.cfg.retrieval_min_reliability if min_reliability is None else min_reliability
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("min_reliability must be in [0, 1]")
        hits = self.fts.search(query, limit=max(limit * 5, 15))
        out: list[RetrievalItem] = []
        for memory_id, _ in hits:
            e = self.episodic.get(memory_id)
            if e is None:
                continue
            if not include_unverified and e.reliability < threshold:
                continue
            out.append(RetrievalItem(e, self.provenance_label(e), conflict=bool(e.related_ids)))
            if self.cfg.record_retrieval_feedback:
                self.record_feedback(memory_id, "retrieval_hit", note=query[:200])
            if len(out) >= limit:
                break
        return out

    # ---- conflict index (P21) ------------------------------------------------------------
    def conflicts(self, open_only: bool = True, limit: int = 100) -> list[dict]:
        where = "WHERE status = 'open'" if open_only else ""
        rows = self.db.conn.execute(
            f"SELECT * FROM conflicts {where} ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def resolve_conflict(self, conflict_id: int, resolution: str,
                         verified_exp_id: str | None = None) -> bool:
        """Explicitly resolve a conflict. Superseding requires a verified experience (P21)."""
        if not resolution.strip():
            raise ValueError("conflict resolution requires an explanation")
        row = self.db.conn.execute("SELECT * FROM conflicts WHERE id = ?", (conflict_id,)).fetchone()
        if row is None:
            return False
        if verified_exp_id:
            e = self.episodic.get(verified_exp_id)
            if e is None or e.verification_status != "verified":
                raise ValueError("superseding a conflict requires an independently verified experience")
            self.fts.delete(row["old_exp_id"], commit=False)
            self.fts.add(e.id, e.text, commit=False)
            status = "superseded"
        else:
            status = "dismissed"
        self.db.conn.execute(
            """UPDATE conflicts SET status = ?, resolution = ?, resolved_ts = ?, policy = ?
               WHERE id = ?""",
            (status, resolution, time.time(), "explicit human/resolver decision", conflict_id))
        self._log(Decision("CONFLICT_RESOLVED", 0.0, f"{status}: {resolution}",
                           verified_exp_id, ["conflict_index"], Features()), commit=False)
        self.db.conn.commit()
        return True

    # ---- decision -----------------------------------------------------------------------
    def admit(self, x: Experience, surprise: float = 0.0, utility: float | None = None) -> Decision:
        """Analyse and store in one transaction, so a partial admission is never visible."""
        conn = self.db.conn
        started = not conn.in_transaction
        try:
            if started:
                conn.execute("BEGIN IMMEDIATE")
            d = self._admit(x, surprise, utility)
            if started:
                conn.commit()
            return d
        except Exception:
            if started and conn.in_transaction:
                conn.rollback()
            raise

    def _admit(self, x: Experience, surprise: float, utility: float | None) -> Decision:
        f = self.analyse(x, surprise, utility)
        s = self.score(f)

        if f.duplicate_of:
            old = self.episodic.get(f.duplicate_of)
            self.episodic.bump_repeat(f.duplicate_of,
                                      x.verification_status if x.verification_status in VERIFIED_STATUSES else None,
                                      commit=False)
            dests = ["episodic(merge)"]
            new_count = (old.repeat_count + 1) if old else 2
            if new_count >= self.cfg.neural_memory_repeats and (old and old.reliability >= self.cfg.reliable_fact_threshold):
                self._enqueue(f.duplicate_of, "neural_memory", commit=False); dests.append("neural_memory_queue")
            return self._log(Decision("MERGED", s, f"duplicate of {f.duplicate_of}", f.duplicate_of, dests, f),
                             commit=False)

        if f.conflicts_with:
            return self._handle_conflict(x, f, s, commit=False)

        if s < self.cfg.discard_threshold:
            return self._log(Decision("DISCARDED", s, f"score {s:.2f} < {self.cfg.discard_threshold}", None, [], f),
                             commit=False)

        return self._log(self._store(x, f, s, index=True, commit=False), commit=False)

    def _handle_conflict(self, x: Experience, f: Features, s: float, commit: bool = True) -> Decision:
        olds = [o for o in (self.episodic.get(i) for i in f.conflicts_with) if o]
        best_old = max((o.reliability for o in olds), default=0.0)
        # Superseding requires independent verification of the new claim AND strictly stronger
        # evidence than every old claim. Two verified claims stay in conflict for review.
        can_supersede = (x.verification_status == "verified"
                         and x.reliability > best_old
                         and all(o.verification_status != "verified" for o in olds))
        if can_supersede:
            for o in olds:
                self.fts.delete(o.id, commit=False)
                self.episodic.link(o.id, x.id, commit=False)
            d = self._store(x, f, s, index=True, commit=False)
            policy = "independent verification + strictly greater reliability than every old claim"
            d.reason = (f"conflict resolved under policy ({policy}); reliability {x.reliability:.2f} > "
                        f"{best_old:.2f}; {len(olds)} older record(s) de-indexed but retained")
            self._record_conflicts(x, olds, "superseded", policy, d.reason, commit=False)
            return self._log(d, commit=commit)
        # Weaker, equal or unverified evidence: keep every record auditable but do not index the
        # new claim. Reliability alone never resolves a conflict.
        d = self._store(x, f, s, index=False, commit=False)
        d.decision = "REVIEW_REQUIRED"
        policy = "reliability alone does not resolve; independent verification + explicit review required"
        d.reason = (f"conflicts with {len(olds)} record(s) of >= reliability ({best_old:.2f}); "
                    f"stored as evidence only")
        self._record_conflicts(x, olds, "open", policy, "", commit=False)
        return self._log(d, commit=commit)

    def _record_conflicts(self, x: Experience, olds: list[Experience], status: str,
                          policy: str, resolution: str, commit: bool) -> None:
        for o in olds:
            self.episodic.link(o.id, x.id, commit=False)
            self.db.conn.execute(
                """INSERT OR IGNORE INTO conflicts(ts, question, new_exp_id, old_exp_id, new_status,
                   old_status, new_reliability, old_reliability, status, policy, resolution)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (time.time(), x.input, x.id, o.id, x.verification_status, o.verification_status,
                 x.reliability, o.reliability, status, policy, resolution))
        if commit:
            self.db.conn.commit()

    def _store(self, x: Experience, f: Features, s: float, index: bool, commit: bool = True) -> Decision:
        x.related_ids = sorted(set(x.related_ids) | set(f.conflicts_with))
        self.episodic.add(x, commit=False)
        dests = ["episodic"]
        if index:
            self.fts.add(x.id, x.text, commit=False); dests.append("fts5")
            # Semantic memory is the verified-fact store. A reliability score alone is not
            # verification evidence (P01/P29); SemanticMemory re-checks the source experience.
            if x.verification_status == "verified" and x.reliability >= self.cfg.reliable_fact_threshold:
                self.semantic.add_fact(
                    x.text, x.id, x.reliability,
                    derivation=f"admitted from verified experience {x.id} (method: {x.verification_method})",
                    commit=False)
                dests.append("semantic")
        if x.verification_status in VERIFIED_STATUSES and not f.conflicts_with:
            self._enqueue(x.id, "dream", commit=False); dests.append("dream_queue")
        if commit:
            self.db.conn.commit()
        return Decision("ADMITTED", s, f"score {s:.2f}", x.id, dests, f)

    def _enqueue(self, exp_id: str, queue: str, commit: bool = True) -> None:
        self.db.conn.execute("INSERT OR REPLACE INTO dream_queue(exp_id, queue, ts) VALUES (?,?,?)", (exp_id, queue, time.time()))
        if commit:
            self.db.conn.commit()

    def _log(self, d: Decision, commit: bool = True) -> Decision:
        features = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in asdict(d.features).items()}
        self.db.conn.execute(
            "INSERT INTO admission_log(ts, exp_id, decision, score, features, reason) VALUES (?,?,?,?,?,?)",
            (time.time(), d.exp_id, d.decision, round(d.score, 6), json.dumps(features), d.reason))
        if commit:
            self.db.conn.commit()
        return d

    def storage_report(self) -> dict:
        """Approximate payload bytes per table, for measuring storage overhead (P17)."""
        pages: dict[str, int] = {}
        for table in ("experiences", "fts_index", "facts", "admission_log", "conflicts",
                      "memory_feedback", "dream_queue"):
            try:
                cols = [r["name"] for r in self.db.conn.execute(f"PRAGMA table_info({table})")]
                if not cols:
                    continue
                expr = " + ".join(f"COALESCE(LENGTH(CAST({c} AS BLOB)), 0)" for c in cols)
                pages[table] = int(self.db.conn.execute(
                    f"SELECT COALESCE(SUM({expr}), 0) FROM {table}").fetchone()[0])
            except Exception:
                pages[table] = 0
        return {
            "pages": pages,
            "total_bytes": sum(pages.values()),
            "rows": {
                "experiences": self.episodic.count(),
                "fts": self.fts.count(),
                "facts": self.semantic.count(),
                "admission_log": self.db.conn.execute("SELECT COUNT(*) FROM admission_log").fetchone()[0],
                "conflicts": self.db.conn.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0],
                "feedback": self.db.conn.execute("SELECT COUNT(*) FROM memory_feedback").fetchone()[0],
            },
        }


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
