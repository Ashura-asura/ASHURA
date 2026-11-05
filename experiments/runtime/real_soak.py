"""EXP-016: bounded real-model concurrency, reload, restart and soak (F-046).

Scope is deliberately small and local: four concurrent ASHURA client processes, one forced
``tony:7b`` unload/reload, one fresh ASHURA process that reads a record written by the previous
process, and 80 mixed turns (60 general, 20 exact arithmetic). It is not a production endurance
test and it does not make the background worker durable (F-045 stays separate).

    python -m experiments.runtime.real_soak
    python -m experiments.runtime.real_soak --smoke
    python -m experiments.runtime.real_soak --verify-restart <db> --verify-question "..."
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import psutil

from brain.controller import Controller, default_registry
from brain.need_field import NeedField
from evaluation.latency import percentile, rss_mb
from foundation.language_model import EchoModel
from foundation.model_config import load_model_config
from foundation.ollama_model import OllamaModel, running_models, unload
from learning.ama import AMA
from learning.cage import CAGE
from memory.database import Database
from memory.text import normalize

RESULT = Path("experiments/runtime/real_soak.json")
MARKER_QUESTION = "what is 8642097531+1357902468"
MEMORY_WRITE = "Remember that the launch marker is BLUE-FALCON-42."
MEMORY_QUERY = "What did I tell you to remember about the launch marker?"
PROBE_QUESTION = "Answer briefly: name three primary colors."


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


def _controller(db: Database, model) -> Controller:
    ama = AMA(db)
    nfd = NeedField(default_registry(), cpu_fn=lambda: 5.0, ram_fn=lambda: 16000.0)
    return Controller(model, ama=ama, nfd=nfd, cage=CAGE())


def _one_turn(controller: Controller, model: OllamaModel, prompt: str, kind: str) -> dict:
    started = time.perf_counter()
    try:
        response = controller.handle(prompt)
        elapsed = (time.perf_counter() - started) * 1000
        language = response.trace.step("language")
        last = model.last_stats if kind == "general" else None
        return {
            "kind": kind,
            "ms": round(elapsed, 3),
            "ok": True,
            "language": language is not None,
            "empty": not response.text.strip(),
            "chars": len(response.text),
            "eval_count": last.eval_count if last else 0,
            "prompt_eval_count": last.prompt_eval_count if last else 0,
            "load_ms": round(last.load_duration_ns / 1e6, 3) if last else 0.0,
            "routing": response.trace.routing.get("selected", []) if response.trace.routing else [],
        }
    except Exception as e:  # noqa: BLE001 - a failed turn is a measurement
        return {"kind": kind, "ms": round((time.perf_counter() - started) * 1000, 3),
                "ok": False, "error": f"{type(e).__name__}: {e}"}


def run_client(job: tuple) -> dict:
    """Run one isolated client process for one phase. Must stay top-level for Windows spawn."""
    client_id, phase, db_path, config_path, general, arithmetic, start_at = job
    cfg = load_model_config(config_path)
    model = OllamaModel(cfg)
    db = Database(db_path)
    controller = _controller(db, model)
    delay = start_at - time.time()
    if delay > 0:
        time.sleep(delay)
    samples: list[dict] = []
    start_rss = rss_mb()
    wall0, cpu0 = time.perf_counter(), time.process_time()
    try:
        for i in range(general):
            prompt = (f"Answer briefly with one sentence: what is one useful fact about "
                      f"topic {phase}-{client_id}-{i}?")
            samples.append(_one_turn(controller, model, prompt, "general"))
        for i in range(arithmetic):
            left = 1000 * client_id + 100 * phase + i + 17
            right = 2000 + 10 * client_id + i
            samples.append(_one_turn(controller, model, f"what is {left}+{right}", "arithmetic"))
    finally:
        controller.close()
    return {
        "client_id": client_id,
        "phase": phase,
        "pid": os.getpid(),
        "wall_s": round(time.perf_counter() - wall0, 2),
        "cpu_s": round(time.process_time() - cpu0, 2),
        "rss_start_mb": round(start_rss, 1),
        "rss_end_mb": round(rss_mb(), 1),
        "samples": samples,
    }


def _ollama_process_stats() -> dict:
    cpu_s, rss = 0.0, 0
    count = 0
    for proc in psutil.process_iter(["name"]):
        try:
            name = (proc.info["name"] or "").lower()
            if "ollama" not in name and "llama" not in name:
                continue
            times = proc.cpu_times()
            cpu_s += times.user + times.system
            rss += proc.memory_info().rss
            count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return {"processes": count, "cpu_s": round(cpu_s, 2), "rss_mb": round(rss / 1e6, 1)}


def _aggregate(samples: list[dict]) -> dict:
    general = [s["ms"] for s in samples if s["kind"] == "general" and s["ok"]]
    arithmetic = [s["ms"] for s in samples if s["kind"] == "arithmetic" and s["ok"]]
    failed = [s for s in samples if not s["ok"]]
    return {
        "turns": len(samples),
        "general": stats(general),
        "arithmetic": stats(arithmetic),
        "failures": len(failed),
        "failure_examples": [s.get("error", "") for s in failed[:5]],
        "empty_responses": sum(1 for s in samples if s.get("empty")),
        "language_steps": sum(1 for s in samples if s.get("language")),
        "generated_tokens": sum(s.get("eval_count", 0) for s in samples),
        "prompt_tokens": sum(s.get("prompt_eval_count", 0) for s in samples),
    }


def run_phase(phase: int, args, workdir: str, general: int, arithmetic: int) -> dict:
    start_at = time.time() + 5.0
    jobs = [
        (i, phase, os.path.join(workdir, f"phase{phase}_client{i}.db"), args.config,
         general, arithmetic, start_at)
        for i in range(args.clients)
    ]
    server_before = _ollama_process_stats()
    wall0 = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.clients) as pool:
        clients = list(pool.map(run_client, jobs))
    wall = time.perf_counter() - wall0
    server_after = _ollama_process_stats()
    cfg = load_model_config(args.config)
    model_memory = _server_models(cfg.host)
    samples = [s for client in clients for s in client["samples"]]
    server_cpu = max(0.0, server_after["cpu_s"] - server_before["cpu_s"])
    return {
        "phase": phase,
        "wall_s": round(wall, 2),
        "clients": [{k: v for k, v in client.items() if k != "samples"} for client in clients],
        "samples": samples,
        "summary": {
            **_aggregate(samples),
            "throughput_turns_per_s": round(len(samples) / wall, 3) if wall else None,
            "client_cpu_s": round(sum(client["cpu_s"] for client in clients), 2),
            "server_cpu_s": round(server_cpu, 2),
            "server_cpu_utilisation": round(server_cpu / wall, 3) if wall else None,
            "rss_start_mb": min(client["rss_start_mb"] for client in clients),
            "rss_end_mb": max(client["rss_end_mb"] for client in clients),
            "inference_process_rss_mb": server_after["rss_mb"],
            "model_footprint_mb": sum(item["size_mb"] for item in model_memory),
        },
    }


def _wait_unloaded(host: str, model: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not any(item["name"] == model for item in running_models(host)):
            return True
        time.sleep(0.5)
    return False


def _server_models(host: str) -> list[dict]:
    return [{"name": item["name"], "size_mb": round(item["size"] / 1e6, 1),
             "vram_mb": round(item["size_vram"] / 1e6, 1)}
            for item in running_models(host)]


def reload_probe(cfg, label: str) -> dict:
    """Unload the model, then measure one request that must load it again."""
    unload(cfg.host, cfg.model)
    unloaded = _wait_unloaded(cfg.host, cfg.model)
    before = _server_models(cfg.host)
    model = OllamaModel(cfg)
    db = Database(":memory:")
    controller = _controller(db, model)
    started = time.perf_counter()
    try:
        response = controller.handle(PROBE_QUESTION)
        wall_ms = (time.perf_counter() - started) * 1000
        last = model.last_stats
        return {
            "label": label,
            "unloaded": unloaded,
            "wall_ms": round(wall_ms, 2),
            "ollama_load_ms": round(last.load_duration_ns / 1e6, 2),
            "eval_count": last.eval_count,
            "chars": len(response.text),
            "server_before": before,
            "server_after": _server_models(cfg.host),
        }
    finally:
        controller.close()


def _temperature_c() -> dict:
    try:
        groups = psutil.sensors_temperatures()
        values = [t.current for group in groups.values() for t in group
                  if t.current is not None]
        if values:
            return {"c": round(max(values), 1), "source": "psutil"}
    except (AttributeError, OSError):
        pass
    if platform.system() == "Windows":
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
                 "| Select-Object -ExpandProperty CurrentTemperature"],
                capture_output=True, text=True, timeout=5)
            values = [float(x) for x in proc.stdout.split() if x.strip()]
            if values:
                return {"c": round(max(values) / 10.0 - 273.15, 1), "source": "wmi"}
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
    return {"c": None, "source": "unavailable"}


def _cpu_freq_mhz() -> float | None:
    try:
        freq = psutil.cpu_freq()
        return round(freq.current, 1) if freq and freq.current else None
    except (AttributeError, OSError):
        return None


class Sampler(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.samples: list[dict] = []
        self.overheated = False
        self._t0 = time.perf_counter()
        self._last_temp = {"c": None, "source": "unavailable"}

    def run(self) -> None:
        psutil.cpu_percent(interval=None)
        n = 0
        while not self.stop_event.is_set():
            if n % 5 == 0:
                self._last_temp = _temperature_c()
            memory = psutil.virtual_memory()
            sample = {
                "t_s": round(time.perf_counter() - self._t0, 2),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "ram_percent": memory.percent,
                "ashura_rss_mb": round(rss_mb(), 1),
                "cpu_freq_mhz": _cpu_freq_mhz(),
                "temperature_c": self._last_temp["c"],
                "temperature_source": self._last_temp["source"],
            }
            self.samples.append(sample)
            if sample["temperature_c"] is not None and sample["temperature_c"] >= 95:
                self.overheated = True
            if sample["ram_percent"] >= 95:
                self.overheated = True
            n += 1
            self.stop_event.wait(2.0)

    def summary(self) -> dict:
        temps = [s["temperature_c"] for s in self.samples if s["temperature_c"] is not None]
        freqs = [s["cpu_freq_mhz"] for s in self.samples if s["cpu_freq_mhz"] is not None]
        return {
            "samples": self.samples,
            "sample_count": len(self.samples),
            "cpu_percent_max": max((s["cpu_percent"] for s in self.samples), default=None),
            "ram_percent_max": max((s["ram_percent"] for s in self.samples), default=None),
            "ashura_rss_max_mb": max((s["ashura_rss_mb"] for s in self.samples), default=None),
            "temperature_c_max": max(temps) if temps else None,
            "temperature_source": (self.samples[-1]["temperature_source"]
                                   if self.samples else "unavailable"),
            "cpu_freq_mhz_min": min(freqs) if freqs else None,
            "cpu_freq_mhz_max": max(freqs) if freqs else None,
            "overheated": self.overheated,
        }


def _db_size_kb(path: str) -> float:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        try:
            total += os.path.getsize(path + suffix)
        except OSError:
            pass
    return round(total / 1024, 1)


def restart_check(workdir: str, question: str = MARKER_QUESTION) -> dict:
    """Write a verified record, close the database, then verify it from a fresh process."""
    path = os.path.join(workdir, "restart.db")
    db = Database(path)
    controller = _controller(db, EchoModel())
    try:
        response = controller.handle(question)
        memory = controller.handle(MEMORY_WRITE)
        written = {
            "pid": os.getpid(),
            "verified": response.verified,
            "text": response.text,
            "admission": response.admission,
            "memory_admission": memory.admission,
        }
    finally:
        controller.close()

    root = str(Path(__file__).resolve().parents[2])
    command = [sys.executable, "-m", "experiments.runtime.real_soak",
               "--verify-restart", path, "--verify-question", question]
    proc = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=120)
    try:
        child = json.loads(proc.stdout.strip().splitlines()[-1])
    except (IndexError, json.JSONDecodeError):
        child = {"error": "child did not return JSON", "stdout": proc.stdout[-500:]}
    return {
        "question": question,
        "written": written,
        "child": child,
        "returncode": proc.returncode,
        "stderr_tail": proc.stderr[-500:],
        "db_kb": _db_size_kb(path),
    }


def verify_restart(path: str, question: str) -> dict:
    """Fresh-process side of the persistence check."""
    db = Database(path)
    ama = AMA(db)
    items = ama.retrieve(question, limit=3)
    arithmetic_found = any(normalize(item.experience.input) == normalize(question)
                           for item in items)
    memory_items = ama.retrieve(MEMORY_QUERY, limit=3)
    memory_found = any(normalize(item.experience.input) == normalize(MEMORY_WRITE)
                       for item in memory_items)
    controller = _controller(db, EchoModel())
    try:
        response = controller.handle(MEMORY_QUERY)
        retrieval = response.trace.step("exact_retrieval")
        return {
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "found": arithmetic_found and memory_found,
            "arithmetic_found": arithmetic_found,
            "memory_found": memory_found,
            "retrieval_count": len(items),
            "retrieved_inputs": [item.experience.input for item in items],
            "memory_retrieval_count": len(memory_items),
            "memory_retrieved_inputs": [item.experience.input for item in memory_items],
            "memory_controller_retrieval": retrieval.output if retrieval else None,
            "routing": response.trace.routing,
            "steps": [{"module": step.module, "ok": step.ok, "note": step.note}
                      for step in response.trace.steps],
            "response_text": response.text,
            "verified": response.verified,
            "db_kb": _db_size_kb(path),
        }
    finally:
        controller.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-016 bounded real-model soak")
    parser.add_argument("--config", default="config/ashura.ollama.toml")
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--phase1-general", type=int, default=5)
    parser.add_argument("--phase1-arithmetic", type=int, default=2)
    parser.add_argument("--phase2-general", type=int, default=10)
    parser.add_argument("--phase2-arithmetic", type=int, default=3)
    parser.add_argument("--output", default=str(RESULT))
    parser.add_argument("--skip-reload", action="store_true")
    parser.add_argument("--smoke", action="store_true",
                        help="one client and one turn of each kind per phase")
    parser.add_argument("--verify-restart", metavar="DB")
    parser.add_argument("--verify-question", default=MARKER_QUESTION)
    args = parser.parse_args()

    if args.verify_restart:
        result = verify_restart(args.verify_restart, args.verify_question)
        print(json.dumps(result))
        return 0 if result["found"] else 1

    if args.smoke:
        args.clients = 1
        args.phase1_general = args.phase1_arithmetic = 1
        args.phase2_general = args.phase2_arithmetic = 1
        args.skip_reload = True

    cfg = load_model_config(args.config)
    if cfg.backend != "ollama":
        raise ValueError(f"{args.config}: expected backend='ollama', got {cfg.backend!r}")
    workdir = tempfile.mkdtemp(prefix="exp016_soak_")
    sampler = Sampler()
    sampler.start()
    cold = forced = phase1 = phase2 = None
    stopped_early = False
    try:
        cold = reload_probe(cfg, "cold_load")
        if not sampler.overheated:
            phase1 = run_phase(1, args, workdir, args.phase1_general, args.phase1_arithmetic)
        else:
            stopped_early = True
        if not sampler.overheated and not args.skip_reload:
            forced = reload_probe(cfg, "forced_reload")
        if not sampler.overheated:
            phase2 = run_phase(2, args, workdir, args.phase2_general, args.phase2_arithmetic)
        else:
            stopped_early = True
        restart = restart_check(workdir)
    finally:
        sampler.stop_event.set()
        sampler.join(timeout=10)
        server_after = _server_models(cfg.host)

    resources = sampler.summary()
    phases = [p for p in (phase1, phase2) if p is not None]
    samples = [s for phase in phases for s in phase["samples"]]
    out = {
        "experiment": "EXP-016",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "clients": args.clients,
        },
        "config": args.config,
        "model": cfg.model,
        "digest": OllamaModel(cfg).digest[:12],
        "cold_load": cold,
        "phase1": phase1,
        "forced_reload": forced,
        "phase2": phase2,
        "restart": restart,
        "summary": {
            "planned_turns": args.clients * (args.phase1_general + args.phase1_arithmetic
                                             + args.phase2_general + args.phase2_arithmetic),
            "completed_turns": len(samples),
            **_aggregate(samples),
            "stopped_early": stopped_early,
        },
        "resources": resources,
        "server_after": server_after,
        "limits": [
            "bounded local run, not production endurance testing",
            "four concurrent client processes with isolated SQLite databases; the shared "
            "contended resource is the local Ollama server",
            "one forced unload/reload and one fresh-process persistence check",
            "worker durability, crash recovery and durable job queues remain F-045",
            "temperature is reported only where the OS exposes it; a null value is not a "
            "cooling claim",
        ],
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({
        "model": out["model"],
        "digest": out["digest"],
        "cold_load_ms": cold["wall_ms"] if cold else None,
        "forced_reload_ms": forced["wall_ms"] if forced else None,
        "phase1": phase1["summary"] if phase1 else None,
        "phase2": phase2["summary"] if phase2 else None,
        "restart_found": restart["child"].get("found") if restart else None,
        "restart_pids": {
            "write": restart["written"]["pid"] if restart else None,
            "verify": restart["child"].get("pid") if restart else None,
        },
        "resources": {k: v for k, v in resources.items() if k != "samples"},
        "stopped_early": stopped_early,
    }, indent=2))
    return 0 if (restart and restart["child"].get("found") and not stopped_early) else 1


if __name__ == "__main__":
    raise SystemExit(main())
