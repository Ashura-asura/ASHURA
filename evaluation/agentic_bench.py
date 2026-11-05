"""Native Ollama tool-use benchmark (agentic3 vs gpa3).

Frozen 12-item suite, greedy decoding, one model resident at a time. Tools are Ollama-native
`/api/chat` tools, so this measures the deployed tool-calling path rather than a hand-written
JSON protocol. The suite is author-written; it is a controlled comparison, not an independent
capability estimate.

    python -m evaluation.agentic_bench --models tony:7b-gpa3 tony:7b-agentic3

Pre-registered decision: replace gpa3 as the tool-use preference only if agentic3 wins at least
3 more items on `agentic_success`, loses at most 1, and finishes every item without a model
failure. Otherwise keep gpa3 and record the negative result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path

from foundation.ollama_model import GenStats, OllamaError, _call, list_models, running_models, unload
from skills.arithmetic.exact import evaluate, format_value

from .judge import judge
from .latency import percentile
from .ollama_baseline import sign_test_p, wilson

DEFAULT_SUITE = "evaluation/benchmarks/agentic_tools_v1.jsonl"
DEFAULT_MODELS = ("tony:7b-gpa3", "tony:7b-agentic3")
DEFAULT_REFERENCE = "tony:7b-gpa3"
CATEGORIES = ("calc", "lookup", "text", "multi", "recovery", "direct")
CATALOG = {"orion": "ORION-7", "vega": "VEGA-3", "atlas": "ATLAS-9",
           "base-count": "48", "fallback-key": "FALLBACK-42"}

SYSTEM = ("You are ASHURA's local tool-using assistant. Use the provided tools when they are "
          "needed, never invent a tool result, and finish with a short answer.")
TOOLS = [
    {"type": "function", "function": {
        "name": "calc", "description": "Evaluate an exact arithmetic expression.",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "e.g. 37*24+19"}},
            "required": ["expression"]}}},
    {"type": "function", "function": {
        "name": "lookup", "description": "Look up a value in the local catalog.",
        "parameters": {"type": "object", "properties": {
            "key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {
        "name": "text_stats", "description": "Count words and characters in a string.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"}}, "required": ["text"]}}},
]


def load_suite(path: str) -> list[dict]:
    items = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
             if line.strip()]
    seen: set[str] = set()
    for item in items:
        missing = [key for key in ("id", "category", "prompt", "accept", "required_tools",
                                   "allowed_tools", "min_calls", "max_calls", "max_steps")
                   if key not in item]
        if missing:
            raise ValueError(f"{path}: item {item.get('id', '?')} is missing {missing}")
        if item["id"] in seen:
            raise ValueError(f"{path}: duplicate id {item['id']!r}")
        if item["category"] not in CATEGORIES:
            raise ValueError(f"{path}: unknown category {item['category']!r}")
        if not set(item["required_tools"]) <= set(item["allowed_tools"]):
            raise ValueError(f"{path}: {item['id']} requires an unallowed tool")
        seen.add(item["id"])
    if not items:
        raise ValueError(f"{path}: empty suite")
    return items


def suite_sha256(path: str) -> str:
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def execute_tool(name: str, args: dict) -> tuple[str, bool, bool]:
    """Return (observation, executed, domain_error)."""
    if name == "calc":
        expr = args.get("expression") if isinstance(args, dict) else None
        if not isinstance(expr, str) or not expr.strip():
            return '{"error": "calc needs a non-empty expression"}', False, False
        try:
            return json.dumps({"value": format_value(evaluate(expr))}), True, False
        except Exception as error:
            return json.dumps({"error": f"{type(error).__name__}: {str(error)[:120]}"}), True, True
    if name == "lookup":
        key = args.get("key") if isinstance(args, dict) else None
        if not isinstance(key, str) or not key.strip():
            return '{"error": "lookup needs a non-empty key"}', False, False
        value = CATALOG.get(key.strip().lower())
        if value is None:
            return json.dumps({"error": "key not found", "key": key}), True, True
        return json.dumps({"key": key, "value": value}), True, False
    if name == "text_stats":
        text = args.get("text") if isinstance(args, dict) else None
        if not isinstance(text, str):
            return '{"error": "text_stats needs a string"}', False, False
        return json.dumps({"words": len(text.split()), "chars": len(text)}), True, False
    return json.dumps({"error": f"unknown tool {name!r}"}), False, False


def chat_once(host: str, model: str, messages: list[dict], max_tokens: int,
              n_ctx: int) -> tuple[dict, GenStats]:
    payload = {"model": model, "messages": messages, "tools": TOOLS, "stream": False,
               "keep_alive": "10m",
               "options": {"temperature": 0, "seed": 0, "top_p": 0.9,
                           "num_predict": max_tokens, "num_ctx": n_ctx}}
    response = _call(host, "/api/chat", payload, timeout=900)
    stats = GenStats(response.get("eval_count", 0), response.get("eval_duration", 0),
                     response.get("prompt_eval_count", 0),
                     response.get("prompt_eval_duration", 0),
                     response.get("load_duration", 0), response.get("total_duration", 0))
    return response, stats


def run_task(host: str, model: str, item: dict, max_tokens: int, n_ctx: int) -> dict:
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": item["prompt"]}]
    used: list[str] = []
    events: list[dict] = []
    invalid = errors = steps = 0
    gen_tokens = prompt_tokens = 0
    eval_ns = load_ns = 0
    final = last_content = ""
    turn_limit = False
    started = time.perf_counter()
    for step in range(item["max_steps"]):
        response, stats = chat_once(host, model, messages, max_tokens, n_ctx)
        steps += 1
        gen_tokens += stats.eval_count
        prompt_tokens += stats.prompt_eval_count
        eval_ns += stats.eval_duration_ns
        if step == 0:
            load_ns = stats.load_duration_ns
        message = response.get("message") or {}
        content = str(message.get("content") or "").strip()
        if content:
            last_content = content
        calls = message.get("tool_calls") or []
        if not calls:
            final = content
            break
        messages.append(message)
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name") or ""
            args = function.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            args = args if isinstance(args, dict) else {}
            used.append(name)
            observation, executed, domain_error = execute_tool(name, args)
            invalid += int(not executed)
            errors += int(domain_error)
            events.append({"name": name, "args": args, "executed": executed,
                           "domain_error": domain_error, "result": observation[:200]})
            messages.append({"role": "tool", "tool_name": name, "content": observation})
    else:
        turn_limit = True
        final = last_content

    recovered = False
    saw_error = False
    for event in events:
        if event["domain_error"]:
            saw_error = True
        elif saw_error and event["executed"]:
            recovered = True
    required, allowed = set(item["required_tools"]), set(item["allowed_tools"])
    tool_correct = (required <= set(used) and set(used) <= allowed
                    and item["min_calls"] <= len(used) <= item["max_calls"])
    answer_correct = bool(final) and judge(final, item, item["prompt"])
    expect_recovery = bool(item.get("expect_recovery"))
    agentic_success = (answer_correct and tool_correct and not turn_limit
                       and (recovered if expect_recovery else True))
    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "id": item["id"], "category": item["category"],
        "answer_correct": answer_correct, "tool_correct": tool_correct,
        "agentic_success": agentic_success,
        "clean": bool(final) and not turn_limit and invalid == 0,
        "recovered": recovered if expect_recovery else None,
        "steps": steps, "tool_calls": len(used), "invalid_calls": invalid,
        "tool_errors": errors, "ms": round(elapsed_ms, 1),
        "gen_tokens": gen_tokens, "prompt_tokens": prompt_tokens,
        "load_ms": round(load_ns / 1e6, 1),
        "tokens_per_s": round(gen_tokens / (eval_ns / 1e9), 2) if eval_ns else None,
        "used": used, "events": events, "final": final[:300],
    }


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else None


def summarize(rows: list[dict]) -> dict:
    latencies = [row["ms"] for row in rows[1:]]
    speeds = [row["tokens_per_s"] for row in rows if row["tokens_per_s"] is not None]
    per_category: dict[str, dict] = {}
    for category in CATEGORIES:
        members = [row for row in rows if row["category"] == category]
        if members:
            per_category[category] = {
                "n": len(members),
                "answer": _mean([float(row["answer_correct"]) for row in members]),
                "agentic": _mean([float(row["agentic_success"]) for row in members]),
            }
    recovery = [row for row in rows if row["category"] == "recovery"]
    total_ns = sum(row["gen_tokens"] / row["tokens_per_s"] for row in rows
                   if row["tokens_per_s"]) if speeds else 0
    return {
        "n": len(rows),
        "answer_accuracy": _mean([float(row["answer_correct"]) for row in rows]),
        "tool_accuracy": _mean([float(row["tool_correct"]) for row in rows]),
        "agentic_success": _mean([float(row["agentic_success"]) for row in rows]),
        "clean_rate": _mean([float(row["clean"]) for row in rows]),
        "recovery_rate": _mean([float(bool(row["recovered"])) for row in recovery]) if recovery else None,
        "latency_ms_p50_excl_first": round(percentile(latencies, 50), 1) if latencies else None,
        "latency_ms_p95_excl_first": round(percentile(latencies, 95), 1) if latencies else None,
        "mean_steps": _mean([float(row["steps"]) for row in rows]),
        "mean_tool_calls": _mean([float(row["tool_calls"]) for row in rows]),
        "tokens_per_s_median": round(statistics.median(speeds), 2) if speeds else None,
        "total_tokens_per_s": round(sum(row["gen_tokens"] for row in rows) / total_ns, 2)
        if total_ns else None,
        "mean_gen_tokens": _mean([float(row["gen_tokens"]) for row in rows]),
        "per_category": per_category,
    }


def run_model(host: str, tag: str, suite: list[dict], max_tokens: int, n_ctx: int,
              digests: dict[str, str]) -> dict:
    rows = [run_task(host, tag, item, max_tokens, n_ctx) for item in suite]
    server = {model["name"]: model for model in running_models(host)}.get(tag, {})
    return {
        "model": tag, "digest": digests.get(tag, "")[:12],
        "load_ms": rows[0]["load_ms"], "server_mem_mb": round(server.get("size", 0) / 1e6, 1),
        "server_vram_mb": round(server.get("size_vram", 0) / 1e6, 1),
        **summarize(rows), "rows": rows,
    }


def _paired(result: dict, reference: dict, key: str) -> dict:
    base = {row["id"]: row for row in reference["rows"]}
    pairs = [(row, base[row["id"]]) for row in result["rows"] if row["id"] in base]
    wins = sum(1 for candidate, old in pairs if candidate[key] and not old[key])
    losses = sum(1 for candidate, old in pairs if not candidate[key] and old[key])
    return {"wins": wins, "losses": losses, "ties": len(pairs) - wins - losses,
            "p_value": round(sign_test_p(wins, losses), 4)}


def compare(results: dict[str, dict], reference: str, alpha: float = 0.05) -> dict[str, dict]:
    out = {}
    for tag, result in results.items():
        if tag == reference:
            continue
        agentic = _paired(result, results[reference], "agentic_success")
        if agentic["p_value"] < alpha and agentic["wins"] > agentic["losses"]:
            verdict = "better than reference"
        elif agentic["p_value"] < alpha and agentic["losses"] > agentic["wins"]:
            verdict = "worse than reference"
        else:
            verdict = "no detectable difference from reference"
        out[tag] = {"verdict": verdict, "agentic": agentic,
                    "answer": _paired(result, results[reference], "answer_correct"),
                    "tool": _paired(result, results[reference], "tool_correct")}
    return out


def decision(results: dict, reference: str) -> dict:
    candidate = "tony:7b-agentic3"
    if candidate not in results or reference not in results or candidate == reference:
        return {"adopt_agentic3": False, "reason": "candidate or reference missing"}
    comparison = compare(results, reference)[candidate]
    wins, losses = comparison["agentic"]["wins"], comparison["agentic"]["losses"]
    candidate_clean = results[candidate]["clean_rate"]
    reference_clean = results[reference]["clean_rate"]
    adopt = (wins >= losses + 3 and losses <= 1 and candidate_clean >= reference_clean)
    return {
        "adopt_agentic3": adopt,
        "wins": wins, "losses": losses,
        "candidate_clean": candidate_clean, "reference_clean": reference_clean,
        "reason": ("meets win/clean rule" if adopt else
                   "does not meet the pre-registered 3-win and clean-rate rule"),
    }


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def markdown(results: dict, comparison: dict, reference: str, suite_path: str,
             digest: str, options: dict, verdict: dict) -> str:
    lines = [
        f"# Native tool-use benchmark - {time.strftime('%Y-%m-%d %H:%M')}", "",
        f"Suite: `{suite_path}` (sha256 `{digest}`), n={next(iter(results.values()))['n']}, "
        f"reference = `{reference}`. Machine: {platform.platform()}, "
        f"Python {sys.version.split()[0]}. Options: `{json.dumps(options, sort_keys=True)}`.", "",
        "| model | answer | tool | agentic | clean | recovery | p50 ms | p95 ms | steps | calls | tok/s | load s | server MB | VRAM MB | vs reference |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for tag, result in results.items():
        if tag == reference:
            versus = "reference"
        else:
            comp = comparison[tag]
            versus = (f"{comp['verdict']} (agentic {comp['agentic']['wins']}/"
                      f"{comp['agentic']['losses']}, p={comp['agentic']['p_value']:.3f})")
        lines.append(
            f"| {tag} | {_fmt(result['answer_accuracy'])} | {_fmt(result['tool_accuracy'])} | "
            f"{_fmt(result['agentic_success'])} | {_fmt(result['clean_rate'])} | "
            f"{_fmt(result['recovery_rate'])} | {_fmt(result['latency_ms_p50_excl_first'], 0)} | "
            f"{_fmt(result['latency_ms_p95_excl_first'], 0)} | {_fmt(result['mean_steps'], 1)} | "
            f"{_fmt(result['mean_tool_calls'], 1)} | {_fmt(result['tokens_per_s_median'], 1)} | "
            f"{result['load_ms'] / 1000:.1f} | {result['server_mem_mb']:.0f} | "
            f"{result['server_vram_mb']:.0f} | {versus} |")
    lines += ["", "Per-category agentic success:", "",
              "| model | " + " | ".join(CATEGORIES) + " |",
              "|---|" + "---|" * len(CATEGORIES)]
    for tag, result in results.items():
        lines.append(f"| {tag} | " + " | ".join(
            _fmt(result["per_category"].get(category, {}).get("agentic"))
            for category in CATEGORIES) + " |")
    failures = [(tag, row) for tag, result in results.items() for row in result["rows"]
                if not row["agentic_success"]]
    lines += ["", "## Failures", ""]
    if not failures:
        lines.append("None.")
    else:
        lines.append("| model | item | used tools | final |")
        lines.append("|---|---|---|---|")
        for tag, row in failures:
            lines.append(f"| {tag} | {row['id']} | {row['used']} | {row['final'][:90]!r} |")
    lines += ["", "## Decision", "",
              f"Adopt `tony:7b-agentic3` for tool use: **{verdict['adopt_agentic3']}**. "
              f"{verdict['reason']} (wins {verdict.get('wins')}, losses {verdict.get('losses')}, "
              f"clean {verdict.get('candidate_clean')} vs {verdict.get('reference_clean')}).", "",
              "Limitations: 12 author-written items, one run per model, hand-written local tools. "
              "This measures this harness on this laptop, not general agentic ability. The models "
              "share a Qwen2 7.6B Q4_K_M base and spill from the 2 GB GPU; memory is not dedicated "
              "VRAM residency. No privacy claim."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Native Ollama tool-use comparison")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--max-tokens", type=int, default=240)
    parser.add_argument("--n-ctx", type=int, default=4096)
    parser.add_argument("--out-dir", default="results")
    args = parser.parse_args(argv)

    installed = {model["name"]: model["digest"] for model in list_models(args.host)}
    if args.reference not in installed:
        print(f"reference {args.reference!r} is not installed; installed: {sorted(installed)}",
              file=sys.stderr)
        return 2
    tags = list(args.models) if args.models else [tag for tag in DEFAULT_MODELS if tag in installed]
    if args.reference not in tags:
        tags.insert(0, args.reference)
    missing = [tag for tag in tags if tag not in installed]
    if missing:
        print(f"not installed: {missing}; installed: {sorted(installed)}", file=sys.stderr)
        return 2
    suite = load_suite(args.suite)
    digest = suite_sha256(args.suite)
    options = {"temperature": 0, "seed": 0, "top_p": 0.9, "num_predict": args.max_tokens,
               "num_ctx": args.n_ctx, "protocol": "ollama /api/chat native tools"}
    print(f"suite {args.suite} sha256 {digest} n={len(suite)}", flush=True)

    results: dict[str, dict] = {}
    started = time.perf_counter()
    for index, tag in enumerate(tags, 1):
        print(f"[{index}/{len(tags)}] {tag} ...", flush=True)
        for running in running_models(args.host):
            try:
                unload(args.host, running["name"])
            except OllamaError:
                pass
        try:
            results[tag] = run_model(args.host, tag, suite, args.max_tokens, args.n_ctx, installed)
        except OllamaError as error:
            print(f"    FAILED: {error}", file=sys.stderr)
            if tag == args.reference:
                return 1
            continue
        result = results[tag]
        print(f"    answer {result['answer_accuracy']:.2f}  tool {result['tool_accuracy']:.2f}  "
              f"agentic {result['agentic_success']:.2f}  clean {result['clean_rate']:.2f}  "
              f"p50 {result['latency_ms_p50_excl_first']} ms  "
              f"{result['tokens_per_s_median']} tok/s", flush=True)
        try:
            unload(args.host, tag)
        except OllamaError:
            pass

    comparison = compare(results, args.reference)
    verdict = decision(results, args.reference)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "experiment": "AGENTIC-001",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "suite": args.suite, "suite_sha256": digest, "options": options,
        "reference": args.reference,
        "environment": {"platform": platform.platform(), "python": sys.version.split()[0],
                        "host": args.host},
        "runtime_s": round(time.perf_counter() - started, 2),
        "results": results, "comparison": comparison, "decision": verdict,
    }
    (out_dir / f"agentic_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = markdown(results, comparison, args.reference, args.suite, digest, options, verdict)
    (out_dir / f"agentic_{stamp}.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
