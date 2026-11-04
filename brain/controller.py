"""Cognitive controller: ties routing, memory, skills, verification and the learning path together.

Response path and learning path are separate (spec 3.1). In this version the AMA call runs
synchronously after the answer is produced; making it asynchronous is a later task.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from foundation.language_model import LanguageModel
from learning.ama import AMA, surprise_from_prior
from learning.cage import CAGE
from memory.episodic import Experience, normalize
from memory.fts import FTS5Index
from skills.arithmetic import exact, try_neural_addition
from skills.arithmetic.parser import extract_expression
from skills.perception import OCRCorrectionStore, ocr_file

from .execution_trace import ExecutionTrace, TraceStep
from .need_field import NeedField, Task, always_all
from .router import ModuleRegistry, ModuleSpec
from .working_memory import WorkingMemory


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


@dataclass
class Response:
    text: str
    trace: ExecutionTrace
    verified: bool | None = None
    admission: str | None = None
    attribution: str | None = None


class Controller:
    def __init__(self, model: LanguageModel, db=None, ama: AMA | None = None, nfd: NeedField | None = None,
                 wm: WorkingMemory | None = None, routing_mode: str = "nfd", cage: CAGE | None = None):
        self.model, self.ama = model, ama
        self.registry = nfd.registry if nfd else default_registry()
        self.nfd = nfd or NeedField(self.registry)
        self.wm = wm or WorkingMemory()
        self.fts = FTS5Index(ama.db) if ama else None
        self.ocr_store = OCRCorrectionStore(ama.db.conn) if ama else None
        self.routing_mode = routing_mode
        self.cage = cage

    def handle(self, task: Task | str) -> Response:
        task = Task(task) if isinstance(task, str) else task
        trace = ExecutionTrace(task=task.text)
        t0 = time.perf_counter()

        r0 = time.perf_counter()
        routing = self.nfd.select(task) if self.routing_mode == "nfd" else always_all(self.registry)
        trace.routing_ms = (time.perf_counter() - r0) * 1000
        trace.routing = {"selected": routing.selected, "skipped": routing.skipped,
                         "priorities": {k: round(v, 3) for k, v in routing.priorities.items()}}

        ctx, value, verified, expr, prior = [], None, None, None, None
        outcomes: dict[str, bool] = {}
        sel = set(routing.selected)

        if "exact_retrieval" in sel and self.fts:
            key = "ctx:" + normalize(task.text)
            cached = self.wm.get(key)                       # fast path: working memory first
            if cached is not None:
                ctx, prior = cached
                trace.add(TraceStep("exact_retrieval", task.text, "working-memory hit", 0.0, note="fast path"))
            else:
                s = time.perf_counter()
                hits = self.fts.search(task.text, limit=3)
                found = [e for e in (self.ama.episodic.get(h) for h, _ in hits) if e]
                ctx = [e.text for e in found]
                # prior belief = what memory already holds for this exact question (used for AMA's surprise)
                prior = next((e.output for e in found if normalize(e.input) == normalize(task.text)), None)
                self.wm.put(key, (ctx, prior))
                trace.add(TraceStep("exact_retrieval", task.text, f"{len(ctx)} hits", (time.perf_counter() - s) * 1000))
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
                except ArithmeticError as e:
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
            verified, note = exact.verify(expr, value)
            trace.add(TraceStep("verification", expr, note, (time.perf_counter() - s) * 1000, ok=verified is not False))
            outcomes["verification"] = verified is not False

        if "language" in sel:
            s = time.perf_counter()
            facts = f"Known: {format_value_safe(value)}\n" if value is not None else ""
            context = "".join(f"Memory: {c}\n" for c in ctx)
            text = self.model.generate(f"{context}{facts}Question: {task.text}")
            trace.add(TraceStep("language", task.text, text, (time.perf_counter() - s) * 1000))
            outcomes["language"] = True
        elif value is not None:
            text = exact.format_value(value)
        elif ctx:
            text = "\n".join(ctx)
        else:
            text = "I could not compute that."

        trace.total_ms = (time.perf_counter() - t0) * 1000
        self.nfd.report(outcomes)

        attribution = None
        if self.cage is not None and outcomes and not all(outcomes.values()):
            expected = exact.format_value(value) if value is not None else None
            verifiers = {"arithmetic": (lambda out, e=expected: out == e)} if expected is not None else {}
            attr = self.cage.attribute(trace, expected=expected, verifiers=verifiers)
            decision = self.cage.authorise(attr, verified=False)   # a failure is not a verified learning signal
            attribution = (f"{attr.module or 'unattributed'} ({attr.confidence:.2f}): {attr.reason}; "
                           f"update allowed={decision.allowed}")

        admission = None
        if self.ama:                                         # learning path (separate from answering)
            if value is not None and verified:
                status, category = "verified", "arithmetic"
            else:
                status, category = "unverified", "arithmetic" if value is not None else "general"
            if task.user_correction:
                status = "user_corrected"
            e = Experience(task.text, text, task_category=category, source="interaction",
                           verification_status=status, outcome="success" if verified else "unknown")
            admission = self.ama.admit(e, surprise=surprise_from_prior(task.text, text, prior)).decision
        return Response(text, trace, verified, admission, attribution)


def format_value_safe(v) -> str:
    return exact.format_value(v)
