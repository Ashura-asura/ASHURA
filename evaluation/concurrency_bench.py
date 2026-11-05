"""F-047: measure local Ollama concurrency, queueing and aggregate throughput.

This is a serving benchmark, not a capability test. It sends identical short counting prompts from
N threads that start together, after a warmup, and records per-request latency, generated tokens,
round wall time and aggregate throughput. The server's real parallel-slot setting
(`OLLAMA_NUM_PARALLEL`) is read from the Ollama process environment when available.

    python -m evaluation.concurrency_bench --model tony:7b-gpa3 --clients 1 2 4 --rounds 3

The command does not change the server environment. Start a dedicated server with the desired
`OLLAMA_NUM_PARALLEL`/`OLLAMA_MAX_QUEUE` values first; see research/EXP-019_concurrency.md.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .latency import percentile, rss_mb

PROMPT = "Answer directly. Count from 1 to 30, separated by commas."


def _call(host: str, path: str, payload: dict | None = None, timeout: float = 300.0) -> dict:
    url = host.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"},
                                 method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Ollama HTTP {exc.code} for {path}: "
                           f"{exc.read().decode(errors='replace')[:300]}") from exc
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"cannot reach Ollama at {host}: {exc}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"unexpected Ollama response for {path}: {type(body).__name__}")
    if body.get("error"):
        raise RuntimeError(f"Ollama error for {path}: {str(body['error'])[:300]}")
    return body


def _host_matches(env: dict, host: str) -> bool:
    configured = env.get("OLLAMA_HOST", "")
    if configured:
        configured = configured.replace("http://", "").replace("https://", "")
        target = host.replace("http://", "").replace("https://", "")
        return configured == target or configured.endswith(":" + target.rsplit(":", 1)[-1])
    return host.rstrip("/").endswith(":11434")


def server_info(host: str) -> dict:
    """Version, running model, and the server process environment if it is visible."""
    info: dict = {"host": host, "version": None, "pid": None, "num_parallel": None,
                  "max_queue": None, "max_loaded_models": None, "env": {}, "models": []}
    try:
        info["version"] = _call(host, "/api/version", timeout=10).get("version")
        info["models"] = _call(host, "/api/ps", timeout=10).get("models", [])
    except RuntimeError as exc:
        info["error"] = str(exc)
    try:
        import psutil
    except ImportError:  # pragma: no cover
        return info
    for proc in psutil.process_iter(["name", "cmdline", "pid"]):
        try:
            name = (proc.info["name"] or "").lower()
            if "ollama" not in name:
                continue
            env = proc.environ()
            if not _host_matches(env, host):
                continue
            info["pid"] = proc.pid
            info["env"] = {k: v for k, v in env.items() if k.startswith("OLLAMA")}
            for key, field in (("OLLAMA_NUM_PARALLEL", "num_parallel"),
                               ("OLLAMA_MAX_QUEUE", "max_queue"),
                               ("OLLAMA_MAX_LOADED_MODELS", "max_loaded_models")):
                try:
                    info[field] = int(env[key]) if key in env else None
                except ValueError:
                    info[field] = env[key]
            break
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return info


def _process_rss_mb(pid: int | None) -> float | None:
    """RSS of the server process tree (the `llama-server` runner is a child)."""
    if pid is None:
        return None
    try:
        import psutil
        parent = psutil.Process(pid)
        processes = [parent, *parent.children(recursive=True)]
        return round(sum(proc.memory_info().rss for proc in processes) / 1e6, 1)
    except Exception:  # noqa: BLE001 - a dead/denied process is not a benchmark failure
        return None


class Sampler(threading.Thread):
    def __init__(self, pid: int | None = None) -> None:
        super().__init__(daemon=True)
        self.pid = pid
        self.stop_event = threading.Event()
        self.samples: list[dict] = []

    def run(self) -> None:
        try:
            import psutil
        except ImportError:  # pragma: no cover
            return
        psutil.cpu_percent(interval=None)
        while not self.stop_event.is_set():
            memory = psutil.virtual_memory()
            self.samples.append({
                "t_s": round(time.perf_counter(), 2),
                "cpu_percent": psutil.cpu_percent(interval=None),
                "ram_percent": memory.percent,
                "ollama_rss_mb": _process_rss_mb(self.pid) or 0.0,
                "client_rss_mb": round(rss_mb(), 1),
            })
            self.stop_event.wait(0.5)

    def summary(self) -> dict:
        if not self.samples:
            return {"samples": 0}
        return {
            "samples": len(self.samples),
            "cpu_percent_max": max(s["cpu_percent"] for s in self.samples),
            "ram_percent_max": max(s["ram_percent"] for s in self.samples),
            "ollama_rss_mb_max": max(s["ollama_rss_mb"] for s in self.samples),
            "client_rss_mb_max": max(s["client_rss_mb"] for s in self.samples),
        }


def _generate(host: str, model: str, prompt: str, max_tokens: int, n_ctx: int,
              timeout: float) -> dict:
    body = {
        "model": model, "prompt": prompt, "stream": False, "keep_alive": "5m",
        "options": {"temperature": 0, "seed": 0, "top_p": 0.9,
                    "num_predict": max_tokens, "num_ctx": n_ctx},
    }
    started = time.perf_counter()
    response = _call(host, "/api/generate", body, timeout=timeout)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "ms": round(elapsed_ms, 3),
        "eval_count": int(response.get("eval_count", 0)),
        "eval_ms": round(response.get("eval_duration", 0) / 1e6, 3),
        "prompt_eval_count": int(response.get("prompt_eval_count", 0)),
        "prefill_ms": round(response.get("prompt_eval_duration", 0) / 1e6, 3),
        "load_ms": round(response.get("load_duration", 0) / 1e6, 3),
        "chars": len(response.get("response", "")),
        "text": response.get("response", "")[:120],
    }


def _round(host: str, model: str, clients: int, round_id: int, max_tokens: int,
           n_ctx: int, timeout: float) -> tuple[float, list[dict]]:
    barrier = threading.Barrier(clients)

    def task(index: int) -> dict:
        barrier.wait()
        prompt = f"Case {clients}-{round_id}-{index}. {PROMPT}"
        try:
            result = _generate(host, model, prompt, max_tokens, n_ctx, timeout)
            return {"ok": True, **result}
        except Exception as exc:  # noqa: BLE001 - a failure is a measurement
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        rows = list(pool.map(task, range(clients)))
    return time.perf_counter() - started, rows


def _summarize(rows: list[dict], walls: list[float], clients: int) -> dict:
    ok = [row for row in rows if row["ok"]]
    latencies = [row["ms"] for row in ok]
    total_tokens = sum(row["eval_count"] for row in ok)
    wall_total = sum(walls)
    return {
        "clients": clients,
        "rounds": len(walls),
        "wall_s_each": [round(value, 3) for value in walls],
        "wall_s_median": round(statistics.median(walls), 3) if walls else None,
        "wall_s_total": round(wall_total, 3),
        "requests": len(rows),
        "failures": len(rows) - len(ok),
        "failure_examples": [row.get("error", "") for row in rows if not row["ok"]][:5],
        "latency_ms_p50": round(percentile(latencies, 50), 3) if latencies else None,
        "latency_ms_p95": round(percentile(latencies, 95), 3) if latencies else None,
        "latency_ms_max": round(max(latencies), 3) if latencies else None,
        "eval_ms_p50": round(percentile([row["eval_ms"] for row in ok], 50), 3) if ok else None,
        "prefill_ms_p50": round(percentile([row["prefill_ms"] for row in ok], 50), 3) if ok else None,
        "generated_tokens": total_tokens,
        "tokens_per_s": round(total_tokens / wall_total, 3) if wall_total else None,
        "requests_per_s": round(len(ok) / wall_total, 4) if wall_total else None,
        "max_load_ms": round(max((row["load_ms"] for row in ok), default=0.0), 3),
        "rows": rows,
    }


def run(host: str, model: str, clients_levels: list[int], rounds: int, warmup_rounds: int,
        max_tokens: int, n_ctx: int, timeout: float) -> dict:
    installed = _call(host, "/api/tags", timeout=10).get("models", [])
    match = next((item for item in installed if item.get("name") == model), None)
    if match is None:
        raise RuntimeError(f"model {model!r} is not installed; installed: "
                           f"{sorted(item.get('name') for item in installed)}")
    info = server_info(host)
    sampler = Sampler(info.get("pid"))
    sampler.start()
    started = time.time()
    try:
        for index in range(2):
            _generate(host, model, f"Case warm-{index}. {PROMPT}", max_tokens, n_ctx, timeout)
        levels = []
        for level in clients_levels:
            rows: list[dict] = []
            walls: list[float] = []
            for round_id in range(warmup_rounds + rounds):
                wall, batch = _round(host, model, level, round_id, max_tokens, n_ctx, timeout)
                if round_id >= warmup_rounds:
                    walls.append(wall)
                    rows.extend(batch)
            levels.append(_summarize(rows, walls, level))
    finally:
        sampler.stop_event.set()
        sampler.join(timeout=2)
    baseline = next((item for item in levels if item["clients"] == 1), None)
    for item in levels:
        if baseline and baseline["tokens_per_s"]:
            item["throughput_scale_vs_1"] = round(item["tokens_per_s"] / baseline["tokens_per_s"], 3)
            item["parallel_efficiency"] = round(item["throughput_scale_vs_1"] / item["clients"], 3)
        if baseline and baseline["latency_ms_p50"]:
            item["latency_amplification_vs_1"] = round(
                item["latency_ms_p50"] / baseline["latency_ms_p50"], 3)
    return {
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
        "runtime_s": round(time.time() - started, 2),
        "machine": platform.platform(),
        "host": host,
        "model": model,
        "digest": (match.get("digest") or "")[:12],
        "server": {key: value for key, value in info.items() if key != "models"},
        "running_before": [
            {"name": item.get("name"), "size_mb": round(item.get("size", 0) / 1e6, 1),
             "vram_mb": round(item.get("size_vram", 0) / 1e6, 1)}
            for item in info.get("models", [])
        ],
        "running_after": [
            {"name": item.get("name"), "size_mb": round(item.get("size", 0) / 1e6, 1),
             "vram_mb": round(item.get("size_vram", 0) / 1e6, 1)}
            for item in _call(host, "/api/ps", timeout=10).get("models", [])
        ],
        "options": {"rounds": rounds, "warmup_rounds": warmup_rounds, "max_tokens": max_tokens,
                    "n_ctx": n_ctx, "timeout_s": timeout, "prompt": PROMPT},
        "resources": sampler.summary(),
        "levels": levels,
    }


def markdown(result: dict) -> str:
    server = result["server"]
    lines = [
        f"# Concurrency benchmark - {result['started_at']}",
        "",
        f"Model `{result['model']}` ({result['digest']}), host `{result['host']}`, "
        f"server `{server.get('version')}` with `OLLAMA_NUM_PARALLEL="
        f"{server.get('num_parallel', 'unknown')}`, `OLLAMA_MAX_QUEUE="
        f"{server.get('max_queue', 'unknown')}`. Runtime {result['runtime_s']} s.",
        "",
        f"Options: {json.dumps(result['options'])}. Machine: {result['machine']}.",
        "",
        "| clients | rounds | p50 ms | p95 ms | tokens/s | req/s | throughput x1 | latency x1 | efficiency | failures |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for level in result["levels"]:
        lines.append(
            f"| {level['clients']} | {level['rounds']} | {level['latency_ms_p50']:.0f} | "
            f"{level['latency_ms_p95']:.0f} | {level['tokens_per_s']:.2f} | "
            f"{level['requests_per_s']:.3f} | {level.get('throughput_scale_vs_1', float('nan')):.2f} | "
            f"{level.get('latency_amplification_vs_1', float('nan')):.2f} | "
            f"{level.get('parallel_efficiency', float('nan')):.2f} | {level['failures']} |")
    resources = result.get("resources", {})
    lines += ["", f"Resources: {json.dumps(resources)}", "",
              "Read `throughput x1` as aggregate tokens/s divided by the one-client value, and "
              "`latency x1` as p50 divided by the one-client p50. A flat throughput and rising "
              "latency means the server is queueing; a throughput gain near the client count means "
              "parallel serving; an intermediate value is the number of effective slots."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F-047 local concurrency benchmark")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="tony:7b-gpa3")
    parser.add_argument("--clients", type=int, nargs="+", default=[1, 2, 4])
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--warmup-rounds", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=32)
    parser.add_argument("--n-ctx", type=int, default=2048)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--output", default="results/concurrency_bench.json")
    parser.add_argument("--inspect", action="store_true", help="print server info and exit")
    args = parser.parse_args(argv)

    if args.inspect:
        print(json.dumps(server_info(args.host), indent=2))
        return 0
    result = run(args.host, args.model, args.clients, args.rounds, args.warmup_rounds,
                 args.max_tokens, args.n_ctx, args.timeout)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(markdown(result))
    print(f"\nRaw data: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
