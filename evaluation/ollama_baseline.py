"""Phase 0 baseline against real local models served by Ollama.

    python -m evaluation.ollama_baseline                        # every installed model vs ref-base:7b
    python -m evaluation.ollama_baseline --models ref-base:7b tony_control:7b lfm3:latest
    python -m evaluation.ollama_baseline --calibrate ref-base:7b   # also write config/module_costs.json

What it measures, per model: strict and lenient accuracy (Wilson 95% interval), per-category strict
accuracy, request latency p50/p95, generation tokens/s, model load time, and *server-side* memory from
`ollama ps` (the Python process's own RSS says nothing about a model that lives in the Ollama server).
Models are unloaded between runs so each footprint is measured on its own.

The verdict against the reference is deliberately conservative: a model is only called better or worse
if a two-sided exact sign test on the paired per-question results gives p < 0.05. With a 16-question suite
that needs a large gap; "no detectable difference" is the expected honest answer for small differences.
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import sys
import time
from pathlib import Path

from foundation.model_config import ModelConfig
from foundation.ollama_model import OllamaModel, list_models, running_models, unload

from .benchmark_runner import load_suite, suite_hash
from .judge import judge_both
from .latency import percentile

DEFAULT_SUITE = "evaluation/benchmarks/baseline_v2.jsonl"
DEFAULT_REFERENCE = "ref-base:7b"


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, centre - half), min(1.0, centre + half))


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact binomial (sign) test on discordant pairs."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    p = 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, p)


def run_model(host: str, tag: str, suite: list[dict], max_tokens: int, n_ctx: int, digests: dict) -> dict:
    cfg = ModelConfig(backend="ollama", model=tag, host=host, n_ctx=n_ctx, keep_alive="10m", timeout_s=600)
    model = OllamaModel(cfg)
    rows, lat, tps, load_ms = [], [], [], 0.0
    for i, item in enumerate(suite):
        t0 = time.perf_counter()
        out = model.generate(f"Question: {item['prompt']}", max_tokens)
        ms = (time.perf_counter() - t0) * 1000
        st = model.last_stats
        if i == 0:
            load_ms = st.load_duration_ns / 1e6      # first call pays the model load; exclude it from latency
        else:
            lat.append(ms)
            if st.tokens_per_s == st.tokens_per_s:
                tps.append(st.tokens_per_s)
        v = judge_both(out, item, prompt=item["prompt"])
        rows.append({"id": item["id"], "category": item["category"], "lenient": v["lenient"], "strict": v["strict"],
                     "ms": round(ms, 1), "gen_tokens": st.eval_count, "output": out[:300]})
    ps = {m["name"]: m for m in running_models(host)}.get(tag, {})
    n = len(rows)
    ks, kl = sum(r["strict"] for r in rows), sum(r["lenient"] for r in rows)
    cats: dict[str, list[bool]] = {}
    for r in rows:
        cats.setdefault(r["category"], []).append(r["strict"])
    return {
        "model": tag, "digest": digests.get(tag, "")[:12], "n": n,
        "strict": ks / n, "strict_ci95": wilson(ks, n), "lenient": kl / n, "lenient_ci95": wilson(kl, n),
        "per_category_strict": {c: sum(v) / len(v) for c, v in cats.items()},
        "latency_ms_p50_excl_first": percentile(lat, 50) if lat else float("nan"),
        "latency_ms_p95_excl_first": percentile(lat, 95) if lat else float("nan"),
        "tokens_per_s_median": statistics.median(tps) if tps else float("nan"),
        "load_ms": load_ms, "server_mem_mb": ps.get("size", 0) / 1e6, "server_vram_mb": ps.get("size_vram", 0) / 1e6,
        "mean_gen_tokens": statistics.mean(r["gen_tokens"] for r in rows), "rows": rows,
    }


def compare(results: dict[str, dict], reference: str, alpha: float = 0.05) -> dict[str, dict]:
    """Paired comparison of every model against the reference on strict per-question results."""
    ref = {r["id"]: r["strict"] for r in results[reference]["rows"]}
    out = {}
    for tag, res in results.items():
        if tag == reference:
            continue
        wins = sum(r["strict"] and not ref[r["id"]] for r in res["rows"])
        losses = sum((not r["strict"]) and ref[r["id"]] for r in res["rows"])
        p = sign_test_p(wins, losses)
        verdict = ("better than reference" if wins > losses else "worse than reference") if p < alpha \
            else "no detectable difference from reference"
        out[tag] = {"wins": wins, "losses": losses, "p_value": p, "verdict": verdict}
    return out


def markdown(results: dict, comparison: dict, reference: str, suite_path: str) -> str:
    L = [f"# Ollama baseline - {time.strftime('%Y-%m-%d %H:%M')}", "",
         f"Suite: `{suite_path}` (hash {suite_hash(suite_path)}), n={next(iter(results.values()))['n']}, greedy decoding, "
         f"reference = `{reference}`. Machine: {platform.platform()}.", "",
         "| model | strict | 95% CI | lenient | p50 ms | p95 ms | tok/s | load s | server MB | vs reference (wins/losses, p) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for tag, r in results.items():
        c = comparison.get(tag)
        vs = "reference" if tag == reference else f"{c['verdict']} ({c['wins']}/{c['losses']}, p={c['p_value']:.2f})"
        lo, hi = r["strict_ci95"]
        L.append(f"| {tag} | {r['strict']:.2f} | {lo:.2f}-{hi:.2f} | {r['lenient']:.2f} | {r['latency_ms_p50_excl_first']:.0f} | "
                 f"{r['latency_ms_p95_excl_first']:.0f} | {r['tokens_per_s_median']:.1f} | {r['load_ms'] / 1000:.1f} | "
                 f"{r['server_mem_mb']:.0f} | {vs} |")
    L += ["", "Per-category strict accuracy:", "", "| model | " + " | ".join(next(iter(results.values()))["per_category_strict"]) + " |",
          "|---|" + "---|" * len(next(iter(results.values()))["per_category_strict"])]
    for tag, r in results.items():
        L.append(f"| {tag} | " + " | ".join(f"{v:.2f}" for v in r["per_category_strict"].values()) + " |")
    L += ["", "Read this with care: 16 questions cannot separate models that differ by less than ~3-4 questions, "
          "and the suite was written by the same author as the rest of ASHURA. Large `lenient - strict` gaps mean "
          "the model is chatty (answer not in the first line) rather than wrong."]
    return "\n".join(L)


def write_module_costs(res: dict, path: str) -> None:
    """Replace the placeholder 'language' cost with measured values (read by brain.controller.default_registry)."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({
        "source": f"measured by evaluation.ollama_baseline on {platform.node() or 'this machine'}",
        "model": res["model"], "measured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "language": {"est_latency_ms": round(res["latency_ms_p50_excl_first"], 1),
                     "est_ram_mb": round(res["server_mem_mb"], 1)}}, indent=2))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="http://127.0.0.1:11434")
    ap.add_argument("--models", nargs="*", help="tags to run (default: every installed model)")
    ap.add_argument("--exclude", nargs="*", default=[], help="tags to skip")
    ap.add_argument("--reference", default=DEFAULT_REFERENCE)
    ap.add_argument("--suite", default=DEFAULT_SUITE)
    ap.add_argument("--max-tokens", type=int, default=64)
    ap.add_argument("--n-ctx", type=int, default=2048)
    ap.add_argument("--out-dir", default="results")
    ap.add_argument("--calibrate", metavar="TAG", help="write config/module_costs.json from this model's run")
    a = ap.parse_args(argv)

    installed = {m["name"]: m["digest"] for m in list_models(a.host)}
    tags = [t for t in (a.models or list(installed)) if t not in a.exclude]
    missing = [t for t in tags + [a.reference] if t not in installed]
    if missing:
        print(f"not installed: {missing}\ninstalled: {sorted(installed)}", file=sys.stderr)
        return 2
    if a.reference not in tags:
        tags.insert(0, a.reference)
    suite = load_suite(a.suite)

    results = {}
    for t in tags:
        print(f"[{len(results) + 1}/{len(tags)}] {t} ...", flush=True)
        for m in running_models(a.host):                      # measure each model's footprint alone
            unload(a.host, m["name"])
        results[t] = run_model(a.host, t, suite, a.max_tokens, a.n_ctx, installed)
        r = results[t]
        print(f"    strict {r['strict']:.2f}  lenient {r['lenient']:.2f}  p50 {r['latency_ms_p50_excl_first']:.0f} ms  "
              f"{r['tokens_per_s_median']:.1f} tok/s  {r['server_mem_mb']:.0f} MB", flush=True)
        unload(a.host, t)

    comp = compare(results, a.reference)
    out = Path(a.out_dir); out.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    (out / f"baseline_{stamp}.json").write_text(json.dumps({"results": results, "comparison": comp, "reference": a.reference,
                                                          "suite_hash": suite_hash(a.suite)}, indent=2))
    md = markdown(results, comp, a.reference, a.suite)
    (out / f"baseline_{stamp}.md").write_text(md)
    print("\n" + md)
    if a.calibrate:
        write_module_costs(results[a.calibrate], "config/module_costs.json")
        print(f"\nwrote config/module_costs.json from {a.calibrate}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
