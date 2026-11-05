"""EXP-015: measured module costs and a sustained-load run (P61-P63/P69).

Measures, on the machine that runs the test:

  * exact arithmetic evaluation and its independent Decimal(60) cross-check;
  * AMA admission, FTS5 retrieval and database growth on a synthetic stream;
  * controller end-to-end latency for arithmetic and general text turns;
  * the background learning worker's submit/drain overhead;
  * a full verified-correction loop job (NumPy candidate training, not a language model);
  * a 300-turn sustained mix with RSS, CPU, database growth and first/last-quartile drift.

The language-model figures in ``config/module_costs.json`` are copied in for reference and are NOT
re-measured here; they come from the Ollama baseline run. This experiment does not load tony:7b.

    python -m experiments.runtime.load_bench
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import time
from pathlib import Path

from brain.controller import Controller, default_registry
from brain.execution_trace import ExecutionTrace, TraceStep
from brain.need_field import NeedField
from brain.verification import Verification
from evaluation.latency import percentile, rss_mb
from evaluation.ngr import NGRPolicy, NGRResult
from foundation.language_model import EchoModel
from foundation.model_config import load_model_config
from foundation.ollama_model import OllamaModel, running_models, unload
from learning.ama import AMA
from learning.cage import CAGE
from learning.corrections import parse_correction
from learning.dream import DreamConfig
from learning.loop import run_verified_correction
from learning.replay import ReplayBuffer, ReplayItem
from learning.worker import LearningWorker
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from memory.database import Database
from memory.episodic import Experience
from plasticity.fast_weights import FastWeights
from plasticity.gated_update import GatedUpdater
from plasticity.slow_weights import CheckpointStore
from skills.arithmetic import exact

RESULT = Path("experiments/runtime/results.json")
EXPRESSIONS = [
    ("small-mul", "6*7"),
    ("large-mul", "123456789*987654321"),
    ("fraction-chain", "(2+3)*4/7"),
    ("sqrt", "sqrt(144)"),
    ("modulo", "10%3"),
    ("power", "2^32"),
    ("decimal", "3.5+1.5"),
]


def stats(samples_ms: list[float]) -> dict:
    if not samples_ms:
        return {"n": 0}
    return {
        "n": len(samples_ms),
        "p50_ms": round(percentile(samples_ms, 50), 3),
        "p95_ms": round(percentile(samples_ms, 95), 3),
        "p99_ms": round(percentile(samples_ms, 99), 3),
        "mean_ms": round(sum(samples_ms) / len(samples_ms), 3),
        "max_ms": round(max(samples_ms), 3),
    }


def measure(fn, n: int, warmup: int = 2) -> dict:
    for _ in range(warmup):
        fn()
    samples, errors = [], 0
    for _ in range(n):
        started = time.perf_counter()
        try:
            fn()
        except Exception:  # noqa: BLE001 - an error is a measurement
            errors += 1
        samples.append((time.perf_counter() - started) * 1000)
    return {**stats(samples), "errors": errors}


def bench_exact(n: int = 30) -> dict:
    rows = []
    for name, expr in EXPRESSIONS:
        value = exact.evaluate(expr)
        evaluated = measure(lambda e=expr: exact.evaluate(e), n)
        verified = measure(lambda e=expr, v=value: exact.verify(e, v), n)
        rows.append({"name": name, "expression": expr, "value": exact.format_value(value),
                     "evaluate": evaluated, "verify": verified})
    combined = [r["evaluate"]["p50_ms"] for r in rows]
    return {"cases": rows, "evaluate_p50_slowest_case_ms": max(combined)}


def make_controller(db: Database) -> Controller:
    ama = AMA(db)
    nfd = NeedField(default_registry(), cpu_fn=lambda: 5.0, ram_fn=lambda: 16000.0)
    return Controller(EchoModel(), ama=ama, nfd=nfd, cage=CAGE())


def bench_memory(n: int = 200) -> dict:
    path = os.path.join(tempfile.mkdtemp(prefix="exp015_memory_"), "memory.db")
    db = Database(path)
    ama = AMA(db)
    start_rss = rss_mb()
    admit = []
    for i in range(n):
        experience = Experience(f"what is the access code for project P{i}",
                                f"the access code is {1000 + i}", verification_status="verified")
        t0 = time.perf_counter()
        ama.admit(experience)
        admit.append((time.perf_counter() - t0) * 1000)
    db.conn.commit()
    search, retrieve = [], []
    for i in range(100):
        query = f"access code project P{i}"
        t0 = time.perf_counter()
        ama.fts.search(query, limit=3)
        search.append((time.perf_counter() - t0) * 1000)
        t0 = time.perf_counter()
        ama.retrieve(query, limit=3)
        retrieve.append((time.perf_counter() - t0) * 1000)
    db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    out = {
        "records": n,
        "admit": stats(admit),
        "fts_search": stats(search),
        "ama_retrieve": stats(retrieve),
        "db_kb": round(os.path.getsize(path) / 1024, 1),
        "episodic_rows": ama.episodic.count(),
        "fts_rows": ama.fts.count(),
        "rss_start_mb": round(start_rss, 1),
        "rss_end_mb": round(rss_mb(), 1),
    }
    db.close()
    return out


def bench_controller(n_arith: int = 40, n_general: int = 20) -> dict:
    path = os.path.join(tempfile.mkdtemp(prefix="exp015_controller_"), "controller.db")
    db = Database(path)
    controller = make_controller(db)
    arithmetic, general = [], []
    arithmetic_verified = 0
    errors = 0
    start_rss = rss_mb()
    try:
        for i in range(n_arith + n_general):
            arithmetic_turn = i < n_arith
            text = (f"what is {i + 1}+{i + 2}" if arithmetic_turn
                    else f"please describe situation number {i}")
            t0 = time.perf_counter()
            try:
                response = controller.handle(text)
                if arithmetic_turn and response.verification is Verification.VERIFIED:
                    arithmetic_verified += 1
            except Exception:  # noqa: BLE001 - controller errors are part of the measurement
                errors += 1
            (arithmetic if arithmetic_turn else general).append(
                (time.perf_counter() - t0) * 1000)
    finally:
        end_rss = rss_mb()
        controller.close()
    return {
        "arithmetic": stats(arithmetic),
        "general": stats(general),
        "arithmetic_verified": arithmetic_verified,
        "errors": errors,
        "rss_start_mb": round(start_rss, 1),
        "rss_end_mb": round(end_rss, 1),
    }


def bench_worker(n: int = 100) -> dict:
    worker = LearningWorker(lambda correction, trace: correction, max_queue=n, poll_s=0.001)
    try:
        submit = []
        last = None
        wall0 = time.perf_counter()
        for i in range(n):
            t0 = time.perf_counter()
            last = worker.submit(i, "trace")
            submit.append((time.perf_counter() - t0) * 1000)
        submitted = time.perf_counter()
        record = worker.wait(last.job_id, timeout=30)
        drained = time.perf_counter()
        statuses = {record["status"]} if record else set()
        return {
            "jobs": n,
            "job": "no-op: returns its correction immediately; this measures worker overhead only",
            "submit": stats(submit),
            "drain_ms": round((drained - submitted) * 1000, 2),
            "total_ms": round((drained - wall0) * 1000, 2),
            "jobs_per_s": round(n / (drained - wall0), 1),
            "last_status": sorted(statuses),
        }
    finally:
        worker.stop(timeout=30)


def _loop_fixture():
    store = CheckpointStore(Path(tempfile.mkdtemp(prefix="exp015_loop_")))
    buffer = ReplayBuffer()
    for i in range(20):
        buffer.add(ReplayItem(f"old-{i}", f"entity{i} old", f"old-{i}", category="old",
                              verified=True))
        buffer.add(ReplayItem(f"old-h-{i}", f"old entity{i}", f"old-{i}", category="old",
                              verified=True, split="heldout"))
    buffer.add(ReplayItem("target-h-0", "what is 6*7", "42", category="corrected",
                          verified=True, split="heldout"))
    buffer.add(ReplayItem("target-h-1", "please compute 6*7", "42", category="corrected",
                          verified=True, split="heldout"))
    memory = AdaptiveMemory(AMemConfig(dim_k=64, dim_v=64, seed=0))
    for item in buffer.training_set():
        if item.category == "old":
            memory.write(item.key, item.value)
    source = store.root / "old_source.npz"
    memory.save(str(source))
    store.stage(source, "old.npz")
    store.promote("old.npz", NGRResult(True, ["fixture"], {}))
    fast = FastWeights()
    execution = ExecutionTrace(task="what is 6*7")
    execution.add(TraceStep("arithmetic", "6*7", "42", 0.5, ok=True))
    execution.add(TraceStep("language", "6*7", "43", 10.0, ok=True))
    correction = parse_correction("actually, 6*7 = 42")
    return store, buffer, fast, execution, correction


def bench_learning_loop(n: int = 5) -> dict:
    samples, promotions = [], 0
    for _ in range(n):
        store, buffer, fast, trace, correction = _loop_fixture()
        t0 = time.perf_counter()
        result = run_verified_correction(
            correction, trace, cage=CAGE(), updater=GatedUpdater(fast), buffer=buffer, store=store,
            policy=NGRPolicy("corrected", min_target_gain=0.5),
            cfg=DreamConfig(target="corrected", dim=64, min_train=1, replay=True,
                            initialization="stable", seed=0))
        samples.append((time.perf_counter() - t0) * 1000)
        promotions += int(result.promoted)
    return {**stats(samples), "promotions": promotions}


def bench_sustained(n: int = 300) -> dict:
    path = os.path.join(tempfile.mkdtemp(prefix="exp015_load_"), "load.db")
    db = Database(path)
    controller = make_controller(db)
    latencies, errors, arithmetic_ok, arithmetic_total = [], 0, 0, 0
    start_rss = rss_mb()
    peak_rss = start_rss
    wall0, cpu0 = time.perf_counter(), time.process_time()
    try:
        for i in range(n):
            arithmetic_turn = i % 5 != 0
            text = (f"what is {i + 1}+{i + 2}" if arithmetic_turn
                    else f"write a note about topic {i}")
            t0 = time.perf_counter()
            try:
                response = controller.handle(text)
                if arithmetic_turn:
                    arithmetic_total += 1
                    step = response.trace.step("arithmetic")
                    arithmetic_ok += int(step is not None and step.ok)
            except Exception:  # noqa: BLE001 - sustained errors are recorded
                errors += 1
            latencies.append((time.perf_counter() - t0) * 1000)
            peak_rss = max(peak_rss, rss_mb())
        wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
        db.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        out = {
            "turns": n,
            "latency": stats(latencies),
            "first_quartile_p50_ms": round(percentile(latencies[: n // 4], 50), 3),
            "last_quartile_p50_ms": round(percentile(latencies[-(n // 4):], 50), 3),
            "throughput_turns_per_s": round(n / wall, 2),
            "cpu_s": round(cpu, 2),
            "wall_s": round(wall, 2),
            "cpu_utilisation": round(cpu / wall, 3) if wall else None,
            "peak_rss_mb": round(peak_rss, 1),
            "rss_start_mb": round(start_rss, 1),
            "rss_end_mb": round(rss_mb(), 1),
            "rss_growth_mb": round(rss_mb() - start_rss, 1),
            "db_kb": round(os.path.getsize(path) / 1024, 1),
            "episodic_rows": controller.ama.episodic.count() if controller.ama else None,
            "errors": errors,
            "arithmetic_steps_ok": arithmetic_ok,
            "arithmetic_turns": arithmetic_total,
        }
    finally:
        controller.close()
    return out


def _server_models(host: str) -> list[dict]:
    return [{"name": item["name"], "size_mb": round(item["size"] / 1e6, 1),
             "vram_mb": round(item["size_vram"] / 1e6, 1)}
            for item in running_models(host)]


def bench_real_model(config_path: str = "config/ashura.ollama.toml", turns: int = 24,
                     arithmetic_turns: int = 8, cold_start: bool = False) -> dict:
    """Optional local-model mixed load. Not part of the default fast benchmark."""
    cfg = load_model_config(config_path)
    if cfg.backend != "ollama":
        raise ValueError(f"{config_path}: expected backend='ollama', got {cfg.backend!r}")
    if cold_start:
        unload(cfg.host, cfg.model)
    server_before = _server_models(cfg.host)
    init0 = time.perf_counter()
    model = OllamaModel(cfg)
    init_ms = (time.perf_counter() - init0) * 1000

    path = os.path.join(tempfile.mkdtemp(prefix="exp015_real_"), "real.db")
    db = Database(path)
    controller = make_controller(db)
    controller.model = model
    general, arithmetic = [], []
    errors = 0
    language_steps = 0
    empty_responses = 0
    answer_chars = []
    generated_tokens = 0
    prompt_tokens = 0
    eval_ns = 0
    start_rss = rss_mb()
    wall0, cpu0 = time.perf_counter(), time.process_time()
    try:
        # First real turn includes model load; keep it out of the steady-state samples.
        t0 = time.perf_counter()
        controller.handle("Answer briefly: name three primary colors.")
        load_ms = (time.perf_counter() - t0) * 1000
        load_stats = model.last_stats

        for i in range(turns):
            text = f"Answer briefly with one sentence: what is one useful fact about topic {i}?"
            t0 = time.perf_counter()
            try:
                response = controller.handle(text)
                if response.trace.step("language") is not None:
                    language_steps += 1
                answer_chars.append(len(response.text))
                if not response.text.strip():
                    empty_responses += 1
                generated_tokens += model.last_stats.eval_count
                prompt_tokens += model.last_stats.prompt_eval_count
                eval_ns += model.last_stats.eval_duration_ns
            except Exception:  # noqa: BLE001 - a failed turn is measured
                errors += 1
            general.append((time.perf_counter() - t0) * 1000)

        for i in range(arithmetic_turns):
            t0 = time.perf_counter()
            try:
                controller.handle(f"what is {i + 1}+{i + 2}")
            except Exception:  # noqa: BLE001
                errors += 1
            arithmetic.append((time.perf_counter() - t0) * 1000)

        wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
        out = {
            "model": cfg.model,
            "digest": model.digest[:12],
            "config": config_path,
            "cold_start": cold_start,
            "init_ms": round(init_ms, 2),
            "first_turn_load_ms": round(load_ms, 2),
            "ollama_load_ms": round(load_stats.load_duration_ns / 1e6, 2),
            "general": stats(general),
            "arithmetic": stats(arithmetic),
            "general_turns": turns,
            "arithmetic_turns": arithmetic_turns,
            "language_steps": language_steps,
            "empty_responses": empty_responses,
            "answer_chars_p50": round(percentile(answer_chars, 50), 1) if answer_chars else None,
            "answer_chars_max": max(answer_chars) if answer_chars else None,
            "errors": errors,
            "generated_tokens": generated_tokens,
            "prompt_tokens": prompt_tokens,
            "generated_tokens_per_s": (round(generated_tokens / (eval_ns / 1e9), 2)
                                       if eval_ns else None),
            "wall_s": round(wall, 2),
            "cpu_utilisation": round(cpu / wall, 3) if wall else None,
            "rss_start_mb": round(start_rss, 1),
            "rss_end_mb": round(rss_mb(), 1),
            "server_before": server_before,
            "server_after": _server_models(cfg.host),
        }
    finally:
        controller.close()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="ASHURA module-cost and sustained-load benchmark")
    ap.add_argument("--real-model", action="store_true",
                    help="also run an optional local Ollama mixed-load measurement")
    ap.add_argument("--real-config", default="config/ashura.ollama.toml")
    ap.add_argument("--real-turns", type=int, default=24)
    ap.add_argument("--real-arithmetic-turns", type=int, default=8)
    ap.add_argument("--real-cold", action="store_true",
                    help="unload the model first so the first turn measures a cold start")
    args = ap.parse_args()

    language = None
    try:
        costs = json.loads(Path("config/module_costs.json").read_text(encoding="utf-8"))
        language = {"source": "config/module_costs.json (measured by the Ollama baseline; not re-run here)",
                    "model": costs.get("model"), **costs.get("language", {})}
    except (OSError, ValueError):
        language = {"source": "config/module_costs.json unavailable"}

    out = {
        "experiment": "EXP-015",
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "language_model_reference": language,
        "exact_arithmetic": bench_exact(),
        "memory": bench_memory(),
        "controller": bench_controller(),
        "learning_worker": bench_worker(),
        "learning_loop": bench_learning_loop(),
        "sustained_load": bench_sustained(),
        "limits": [
            "single machine, single process, no concurrency",
            "EchoModel is a plumbing stub; these controller numbers are not tony:7b latency",
            "the learning loop trains the NumPy adaptive memory, not the language model",
            "the sustained mix is synthetic; database growth is not a production forecast",
            "the optional real-model run is a short local mixed load, not a long-duration production soak",
        ],
    }
    if args.real_model:
        out["real_model"] = bench_real_model(args.real_config, args.real_turns,
                                             args.real_arithmetic_turns, args.real_cold)
    RESULT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    summary = {
        "environment": out["environment"],
        "exact_arithmetic_slowest_evaluate_p50_ms": out["exact_arithmetic"]["evaluate_p50_slowest_case_ms"],
        "memory": {k: out["memory"][k] for k in ("admit", "fts_search", "ama_retrieve", "db_kb")},
        "controller": {k: out["controller"][k] for k in
                       ("arithmetic", "general", "arithmetic_verified", "errors")},
        "learning_worker": out["learning_worker"],
        "learning_loop": out["learning_loop"],
        "sustained_load": out["sustained_load"],
    }
    if "real_model" in out:
        summary["real_model"] = out["real_model"]
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
