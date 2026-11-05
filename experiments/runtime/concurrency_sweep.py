"""Run F-047's concurrency matrix on a private Ollama server.

For each `OLLAMA_NUM_PARALLEL` value it starts a dedicated server on `--port`, runs the benchmark
against it, stops the whole server process tree, and moves to the next value. The normal desktop
Ollama server is left alone; only the benchmark model is loaded, one server at a time.

    python -m experiments.runtime.concurrency_sweep --parallel 1 2 4

Precondition: no other model is loaded on the desktop server (11434), otherwise two models can be
resident at once on the 16 GB laptop. The runner prints the desktop server state before it starts.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

from evaluation.concurrency_bench import run, server_info


def _call(host: str, path: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(host.rstrip("/") + path, timeout=timeout) as response:
        return json.loads(response.read().decode())


def _wait_up(host: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            _call(host, "/api/version", timeout=2)
            return True
        except Exception:  # noqa: BLE001 - server is still starting
            time.sleep(0.5)
    return False


def _stop_tree(process: subprocess.Popen) -> None:
    try:
        parent = psutil.Process(process.pid)
        processes = [parent, *parent.children(recursive=True)]
    except psutil.NoSuchProcess:
        return
    for proc in reversed(processes):
        try:
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _, alive = psutil.wait_procs(processes, timeout=10)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _existing_server(port: int) -> list[dict]:
    found = []
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            if "ollama" not in (proc.info["name"] or "").lower():
                continue
            env = proc.environ()
            host = env.get("OLLAMA_HOST", "")
            if host.endswith(f":{port}"):
                found.append({"pid": proc.pid, "host": host,
                              "num_parallel": env.get("OLLAMA_NUM_PARALLEL")})
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F-047 private-server concurrency sweep")
    parser.add_argument("--model", default="tony:7b-gpa3")
    parser.add_argument("--port", type=int, default=11435)
    parser.add_argument("--parallel", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--max-queue", type=int, default=8)
    parser.add_argument("--clients", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmup-rounds", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--n-ctx", type=int, default=2048)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", default="experiments/runtime/concurrency_sweep.json")
    args = parser.parse_args(argv)

    executable = shutil.which("ollama")
    if not executable:
        print("ollama executable not found", file=sys.stderr)
        return 1
    host = f"http://127.0.0.1:{args.port}"
    primary = "http://127.0.0.1:11434"
    try:
        primary_models = [item.get("name") for item in _call(primary, "/api/ps", timeout=5).get("models", [])]
    except Exception:  # noqa: BLE001 - primary server may be absent
        primary_models = []
    if primary_models:
        print(f"refusing to start: the desktop server still has {primary_models} loaded; "
              f"unload them first", file=sys.stderr)
        return 2

    existing = _existing_server(args.port)
    if existing:
        print(f"port {args.port} already has an Ollama server: {existing}", file=sys.stderr)
        return 2

    results = []
    for parallel in args.parallel:
        env = os.environ.copy()
        env.update({
            "OLLAMA_HOST": f"127.0.0.1:{args.port}",
            "OLLAMA_NUM_PARALLEL": str(parallel),
            "OLLAMA_MAX_QUEUE": str(args.max_queue),
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_KEEP_ALIVE": "5m",
        })
        log_path = Path(args.output).parent / f"concurrency_server_p{parallel}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log = open(log_path, "w", encoding="utf-8")
        process = subprocess.Popen([executable, "serve"], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, cwd=Path.cwd())
        try:
            if not _wait_up(host):
                print(f"server with OLLAMA_NUM_PARALLEL={parallel} did not start; see {log_path}",
                      file=sys.stderr)
                return 3
            info = server_info(host)
            print(f"running OLLAMA_NUM_PARALLEL={parallel}, pid={info.get('pid')}, "
                  f"max_queue={info.get('max_queue')}", flush=True)
            result = run(host, args.model, args.clients, args.rounds, args.warmup_rounds,
                         args.max_tokens, args.n_ctx, args.timeout)
            results.append({"num_parallel": parallel, "max_queue": args.max_queue,
                            "server": info, "result": result})
            for level in result["levels"]:
                print(f"  clients={level['clients']}: p50={level['latency_ms_p50']:.0f} ms, "
                      f"{level['tokens_per_s']:.2f} tok/s, "
                      f"x{level.get('throughput_scale_vs_1', 0):.2f} throughput, "
                      f"failures={level['failures']}", flush=True)
        finally:
            _stop_tree(process)
            log.close()
            time.sleep(2)

    payload = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": platform.platform(),
        "model": args.model,
        "clients": args.clients,
        "rounds": args.rounds,
        "warmup_rounds": args.warmup_rounds,
        "max_tokens": args.max_tokens,
        "n_ctx": args.n_ctx,
        "configs": results,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"raw data: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
