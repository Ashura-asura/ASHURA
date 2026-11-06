"""Cognitive controller: ties routing, memory, skills, verification and the learning path together.

Response path and learning path are separate (spec 3.1). In this version the AMA call runs
synchronously after the answer is produced; making it asynchronous is a later task.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from foundation.language_model import GenerationCancelled, LanguageModel
from learning.ama import AMA, surprise_from_prior
from learning.cage import CAGE
from learning.corrections import parse_correction
from memory.episodic import Experience, normalize
from memory.fts import FTS5Index
from skills.arithmetic import exact, try_neural_addition
from skills.arithmetic.parser import extract_expression
from skills.perception import OCRCorrectionStore, ocr_file

from .execution_trace import ExecutionTrace, TraceStep
from .need_field import NeedField, Task, always_all
from .router import ModuleRegistry, ModuleSpec
from .verification import Verification
from .working_memory import WorkingMemory

# A declarative user turn is evidence about what the user said, not a model answer. These cues
# keep such statements at user-provided reliability instead of admitting the generated reply as
# if the model had produced the fact.
_USER_ASSERTION = re.compile(r"^\s*(remember|note|store|save|keep in mind)\b", re.I)


def load_measured_costs(path: str | os.PathLike = "config/module_costs.json") -> dict:
    """Measured per-module costs written by `evaluation.ollama_baseline --calibrate`. {} if none exist yet."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return {k: v for k, v in json.loads(p.read_text()).items() if isinstance(v, dict)}
    except (OSError, ValueError):
        return {}


def default_registry(language_available: bool = True, costs_path: str | os.PathLike = "config/module_costs.json") -> ModuleRegistry:
    r = ModuleRegistry()
    # Figures are PLACEHOLDER ESTIMATES unless config/module_costs.json exists (measured on the target laptop).
    m = load_measured_costs(costs_path).get("language", {})
    r.register(ModuleSpec("language", m.get("est_latency_ms", 3000), m.get("est_ram_mb", 2500), language_available,
                          resident=True))  # model is loaded once by the app
    r.register(ModuleSpec("exact_retrieval", 20, 20))
    r.register(ModuleSpec("semantic_retrieval", 150, 600, available=False))   # optional, not built
    r.register(ModuleSpec("arithmetic", 1, 1))
    try:
        from skills.perception.ocr import OCREngine
        ocr_available = OCREngine().available
    except Exception:
        ocr_available = False
    r.register(ModuleSpec("ocr", 1500, 600, available=ocr_available))                # Phase 8
    r.register(ModuleSpec("reasoning", 8000, 2500, available=False))         # later phase
    r.register(ModuleSpec("verification", 5, 5))
    r.register(ModuleSpec("learning", 30, 10, available=False))              # Phase 4+
    return r


def _loop_summary(result: Any) -> dict:
    """A small, JSON-safe view of a LoopResult- or QueuedResult-like object."""
    if hasattr(result, "stage"):
        summary = {"stage": str(result.stage),
                   "promoted": bool(getattr(result, "promoted", False)),
                   "reasons": [str(r) for r in getattr(result, "reasons", []) or []]}
        job_id = getattr(result, "job_id", None)
        if job_id:
            summary["job_id"] = str(job_id)
        return summary
    return {"stage": "unknown", "result": repr(result)}


@dataclass
class Response:
    text: str
    trace: ExecutionTrace
    verified: bool | None = None          # compatibility view: True / False / None (unavailable)
    admission: str | None = None
    attribution: str | None = None
    verification: Verification | None = None
    correction: dict | None = None       # parsed user correction and its independent check


class Controller:
    def __init__(self, model: LanguageModel, db=None, ama: AMA | None = None, nfd: NeedField | None = None,
                 wm: WorkingMemory | None = None, routing_mode: str = "nfd", cage: CAGE | None = None,
                 correction_loop: Callable[[Any, ExecutionTrace], Any] | None = None):
        self.model, self.ama = model, ama
        self.registry = nfd.registry if nfd else default_registry()
        self.nfd = nfd or NeedField(self.registry)
        self.wm = wm if wm is not None else WorkingMemory()   # NOT `wm or ...`: an empty WorkingMemory is falsy
        self.fts = FTS5Index(ama.db) if ama else None
        self.ocr_store = OCRCorrectionStore(ama.db.conn) if ama else None
        self.routing_mode = routing_mode
        self.cage = cage
        # F-041: retain the last non-correction trace so a correction can be attributed to the
        # execution that produced the answer. The loop is opt-in: it needs a replay corpus and a
        # checkpoint store, which the plain controller does not own.
        self.correction_loop = correction_loop
        self._last_trace: ExecutionTrace | None = None

    def close(self) -> None:
        """Release the database connection (flushes the SQLite WAL). Safe to call twice."""
        if self.ama is not None:
            try:
                self.ama.db.close()
            except Exception:  # noqa: BLE001 - already closed
                pass

    def __enter__(self) -> "Controller":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def handle(self, task: Task | str, on_token: Callable[[str], None] | None = None) -> Response:
        task = Task(task) if isinstance(task, str) else task
        trace = ExecutionTrace(task=task.text)
        t0 = time.perf_counter()

        r0 = time.perf_counter()
        routing = self.nfd.select(task) if self.routing_mode == "nfd" else always_all(self.registry)
        trace.routing_ms = (time.perf_counter() - r0) * 1000
        trace.routing = {"selected": routing.selected, "skipped": routing.skipped,
                         "priorities": {k: round(v, 3) for k, v in routing.priorities.items()}}

        ctx, value, expr, prior = [], None, None, None
        verification = Verification.UNAVAILABLE
        verification_note = ""
        outcomes: dict[str, bool] = {}
        sel = set(routing.selected)

        if "exact_retrieval" in sel and self.ama:
            key = "ctx:" + normalize(task.text)
            cached = self.wm.get(key)                       # fast path: working memory first
            if cached is not None:
                ctx, prior = cached
                trace.add(TraceStep("exact_retrieval", task.text, "working-memory hit", 0.0, note="fast path"))
            else:
                s = time.perf_counter()
                found = self.ama.retrieve(task.text, limit=3)   # reliability-filtered + provenance-labelled
                ctx = [item.prompt_line for item in found]
                # prior belief = what reliable memory already holds for this exact question
                prior = next((item.experience.output for item in found
                              if normalize(item.experience.input) == normalize(task.text)), None)
                self.wm.put(key, (ctx, prior))
                trace.add(TraceStep("exact_retrieval", task.text, f"{len(ctx)} hits",
                                    (time.perf_counter() - s) * 1000,
                                    note="reliability-filtered" if found else ""))
            outcomes["exact_retrieval"] = True

        if "arithmetic" in sel:
            s = time.perf_counter()
            expr = extract_expression(task.text)

            if not expr:
                trace.add(TraceStep("arithmetic", task.text, "no arithmetic expression found", (time.perf_counter() - s) * 1000,
                                     ok=False))
                outcomes["arithmetic"] = False
            else:
                try:
                    # Exact CPU arithmetic is authoritative. Neural HARN is a logged candidate
                    # and can never replace or veto the exact result.
                    value = exact.evaluate(expr)
                    neural_value = try_neural_addition(expr)
                    if neural_value is not None:
                        agrees = neural_value == value
                        trace.add(TraceStep("neural_arithmetic_candidate", expr,
                                            exact.format_value(neural_value),
                                            (time.perf_counter() - s) * 1000, ok=agrees,
                                            note="candidate agrees with exact" if agrees
                                            else "candidate rejected; exact retained"))
                        note = ("exact evaluator; neural candidate agrees" if agrees
                                else "exact evaluator; neural candidate rejected")
                    else:
                        note = "exact evaluator"
                    trace.add(TraceStep("arithmetic", expr, exact.format_value(value),
                                        (time.perf_counter() - s) * 1000, note=note))
                    outcomes["arithmetic"] = True
                except (ArithmeticError, ValueError, RecursionError, MemoryError) as e:
                    # A bad or oversized expression must degrade to a failed step, never crash the request.
                    value = None
                    trace.add(TraceStep("arithmetic", expr, str(e), (time.perf_counter() - s) * 1000, ok=False))
                    outcomes["arithmetic"] = False

        if "ocr" in sel and task.image_path:
            s = time.perf_counter()
            try:
                ocr_result = ocr_file(task.image_path, image_ref=task.image_path,
                                      document_type="document")
                outcomes["ocr"] = ocr_result.ok
                if ocr_result.ok:
                    if self.ocr_store is not None:
                        self.ocr_store.add(ocr_result)
                    ocr_text = ocr_result.text
                    ctx.append(f"OCR ({ocr_result.confidence:.0%}): {ocr_text}")
                    trace.add(TraceStep("ocr", task.image_path, ocr_text, (time.perf_counter() - s) * 1000,
                                         note=f"conf={ocr_result.confidence:.2f} engine={ocr_result.engine}"))
                else:
                    trace.add(TraceStep("ocr", task.image_path, "", (time.perf_counter() - s) * 1000,
                                         ok=False, note=ocr_result.reason))
            except Exception as e:
                trace.add(TraceStep("ocr", task.image_path, "", (time.perf_counter() - s) * 1000,
                                     ok=False, note=f"ocr error: {e}"))
                outcomes["ocr"] = False
        elif "ocr" in sel:
            trace.add(TraceStep("ocr", task.image_path or "", "", 0.0, ok=False,
                                 note="no image path provided"))
            outcomes["ocr"] = False

        if "verification" in sel and value is not None:
            s = time.perf_counter()
            ok, verification_note = exact.verify(expr, value)
            verification = Verification.from_optional(ok)
            # `ok` is operational: the verifier ran. Factual status lives in `verification`.
            trace.add(TraceStep("verification", expr, verification_note, (time.perf_counter() - s) * 1000,
                                ok=verification is not Verification.FAILED,
                                note=f"{verification.value}: {verification_note}",
                                verification=verification.value))
            outcomes["verification"] = True

        answered = True
        if "language" in sel:
            s = time.perf_counter()
            facts = f"Known: {format_value_safe(value)}\n" if value is not None else ""
            context = "".join(f"{c}\n" for c in ctx)
            history = "".join(f"User: {u[:1000]}\nAssistant: {a[:1000]}\n"
                              for u, a in task.history[-8:])
            prompt = f"{history}{context}{facts}Question: {task.text}"
            try:
                if on_token is None:
                    text = self.model.generate(prompt)
                else:
                    chunks: list[str] = []
                    for chunk in self.model.stream(prompt):
                        if chunk:
                            chunks.append(chunk)
                            on_token(chunk)
                    text = "".join(chunks).strip()
                trace.add(TraceStep("language", task.text, text, (time.perf_counter() - s) * 1000))
                outcomes["language"] = True
            except GenerationCancelled:
                raise
            except Exception as e:  # noqa: BLE001 - backend down / timeout / bad response: degrade, don't crash
                trace.add(TraceStep("language", task.text, "", (time.perf_counter() - s) * 1000, ok=False,
                                    note=f"language model failed: {e}"))
                outcomes["language"] = False
                if value is not None:
                    text = exact.format_value(value)
                elif ctx:
                    text = "\n".join(ctx)
                else:
                    text, answered = f"The language model is unavailable right now ({e}).", False
        elif value is not None:
            text = exact.format_value(value)
        elif ctx:
            text = "\n".join(ctx)
        else:
            text, answered = "I could not compute that.", False

        trace.total_ms = (time.perf_counter() - t0) * 1000
        self.nfd.report(outcomes)

        # A response is only verified if it *is* the independently checked exact answer. If the
        # language model wrote the text, a verified arithmetic value elsewhere in the turn does
        # not verify the response (P02/P03).
        response_verified = (verification is Verification.VERIFIED and value is not None
                             and outcomes.get("language") is not True
                             and text.strip() == exact.format_value(value).strip())

        attribution = None
        if self.cage is not None and outcomes and not all(outcomes.values()):
            expected = exact.format_value(value) if value is not None else None
            verifiers = {}
            if expected is not None:
                verifiers["arithmetic"] = lambda out, e=expected: out == e
                if outcomes.get("language"):
                    verifiers["language"] = lambda out, e=expected: out == e
            attr = self.cage.attribute(trace, expected=expected, verifiers=verifiers)
            # A verified learning signal requires both a VERIFIED outcome and a verifier that
            # covers the attributed module. An ordinary model failure never qualifies (P08).
            verified_signal = (verification is Verification.VERIFIED and attr.module is not None
                               and attr.module in verifiers)
            decision = self.cage.authorise(attr, verified=verified_signal)
            attribution = (f"{attr.module or 'unattributed'} ({attr.confidence:.2f}): {attr.reason}; "
                           f"update allowed={decision.allowed}")

        admission = None
        category = "arithmetic" if value is not None else "general"
        user_turn = task.user_correction or bool(_USER_ASSERTION.match(task.text))
        admitted = False

        # P05/P06: a user correction is a separate record of what the user said. It is not a
        # verdict on the assistant's reply, and its factual truth is not established by the user
        # merely saying it. The generated reply is never relabelled as corrected.
        correction = None
        if self.ama and user_turn:
            e_user = Experience(task.text, "", task_category=category, source="user",
                                verification_status="user_provided",
                                verification_method="user assertion; factual truth not independently verified",
                                outcome="corrected" if task.user_correction else "reported")
            d = self.ama.admit(e_user)
            admission = d.decision
            admitted = d.decision != "MERGED"

            # P05/P06/P07: a correction is still stored as a user record. Only a claim ASHURA can
            # check independently (exact arithmetic) also produces a verified training record.
            if task.user_correction:
                parsed = parse_correction(task.text, prior=prior)
                correction = parsed.as_dict()
                verified_record = parsed.to_experience()
                if verified_record is not None:
                    d2 = self.ama.admit(verified_record)
                    admission = f"{admission} / {d2.decision}"
                    admitted = admitted or d2.decision != "MERGED"
                correction["admission"] = admission
                correction["verified_record"] = verified_record is not None

                # F-041: a verified correction may start the learning loop against the previous
                # execution trace. The hook is optional and a hook failure never breaks the reply.
                if parsed.verified and self.correction_loop is not None:
                    if self._last_trace is None:
                        correction["loop"] = {"stage": "not_run",
                                              "reason": "no previous execution trace to attribute"}
                    else:
                        try:
                            correction["loop"] = _loop_summary(
                                self.correction_loop(parsed, self._last_trace))
                        except Exception as e:  # noqa: BLE001 - learning must not break answering
                            correction["loop"] = {"stage": "error", "error": f"{type(e).__name__}: {e}"}

        if self.ama and answered and not user_turn:          # learning path; error text is not learned
            # Only an independently verified exact answer may be stored as verified (P03).
            if response_verified:
                status, category = "verified", "arithmetic"
                method = "exact arithmetic + Decimal(60) cross-check"
            else:
                status = "unverified"
                method = "none (model-generated or unverified)"
            e = Experience(task.text, text, task_category=category, source="interaction",
                           verification_status=status, verification_method=method,
                           outcome="success" if response_verified else "unknown")
            d = self.ama.admit(e, surprise=surprise_from_prior(task.text, text, prior))
            admission = d.decision if admission is None else f"{admission} / {d.decision}"
            admitted = admitted or d.decision != "MERGED"

        if self.ama and admitted:
            # Memory changed, so cached retrieval results for OTHER questions are stale (a fact told a moment
            # ago must be findable). This question's own entry is kept: re-asking it should hit the fast path
            # instead of retrieving the answer we just stored.
            self.wm.invalidate(keep={"ctx:" + normalize(task.text)})
        if not task.user_correction:
            self._last_trace = trace                 # corrections are attributed to the prior turn
        response_state = (Verification.VERIFIED if response_verified
                          else Verification.FAILED if verification is Verification.FAILED
                          else Verification.UNAVAILABLE)
        return Response(text, trace, response_state.legacy_bool, admission, attribution, response_state,
                        correction)


def format_value_safe(v) -> str:
    return exact.format_value(v)
