"""Frozen subject-tutor comparison for local Ollama models.

This is a model-evaluation harness, not a training run. The suite is hashed before any model is
called; both models receive identical prompts and greedy decoding. Each item has an exact-answer
accept list plus an optional explanation rubric. `quality` requires the final answer to be correct
and, when a rubric exists, at least two of its three terms to appear in the explanation.

    python -m evaluation.subject_bench
    python -m evaluation.subject_bench --models tony:7b-gpa3 tony:7b --reference tony:7b

The suite is author-written. It is a controlled comparison between local checkpoints, not an
independently authored capability estimate and not a privacy test.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import statistics
import sys
import time
from pathlib import Path

from foundation.model_config import ModelConfig
from foundation.ollama_model import OllamaError, OllamaModel, list_models, running_models, unload

from .judge import _contains, strip_echo, words
from .latency import percentile
from .ollama_baseline import sign_test_p, wilson

DEFAULT_SUITE = "evaluation/benchmarks/subject_tutor_v1.jsonl"
DEFAULT_MODELS = ("tony:7b-gpa3", "tony:7b")
DEFAULT_REFERENCE = "tony:7b"
CATEGORIES = ("physics", "maths", "biology", "programming", "coding", "devops", "debugging")
_FINAL = re.compile(r"(?im)^\s*\**\s*final\s+answer\s*\**\s*[:\-]\s*(.+?)\s*$")


def load_suite(path: str) -> list[dict]:
    items = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()
             if line.strip()]
    seen: set[str] = set()
    for item in items:
        missing = [key for key in ("id", "category", "prompt", "accept") if not item.get(key)]
        if missing:
            raise ValueError(f"{path}: item {item.get('id', '?')} is missing {missing}")
        if item["id"] in seen:
            raise ValueError(f"{path}: duplicate id {item['id']!r}")
        if item["category"] not in CATEGORIES:
            raise ValueError(f"{path}: unknown category {item['category']!r}")
        seen.add(item["id"])
    if not items:
        raise ValueError(f"{path}: empty suite")
    return items


def suite_sha256(path: str) -> str:
    """Hash the canonical suite content, independent of checkout line endings.

    Git may check the JSONL out with CRLF on Windows while Linux keeps LF. The suite is the same
    sequence of JSON records in both cases, so the frozen hash is defined over LF-normalised bytes.
    """
    data = Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def final_answer(output: str) -> tuple[str, bool]:
    """Return (answer text, format_ok). Fall back to the first non-empty line."""
    match = _FINAL.search(output)
    if match:
        return match.group(1).strip().strip("*").strip(), True
    for line in output.splitlines():
        if line.strip():
            return line.strip(), False
    return "", False


def _subject_match(text: str, item: dict, min_run: int = 6) -> bool:
    """Match an accept phrase after removing only long prompt echoes.

    The general judge strips 3-word echoes. That wrongly removes conceptual answers such as
    "a race condition" or "base case" because the question contains the same short phrase. A
    6-word threshold keeps the echo defence for copied sentences while preserving key terms.
    """
    cleaned = [word for word in strip_echo(words(text), item["prompt"], min_run=min_run)
               if word != "\x00"]
    return any(_contains(cleaned, words(accept)) for accept in item["accept"])


def rubric_coverage(output: str, item: dict) -> float | None:
    terms = [words(term) for term in item.get("rubric", [])]
    if not terms:
        return None
    cleaned = strip_echo(words(output), item["prompt"], min_run=6)
    return sum(1 for term in terms if _contains(cleaned, term)) / len(terms)


def score_item(output: str, item: dict) -> dict:
    final, formatted = final_answer(output)
    answer_text = final if formatted else output
    strict_text = final if formatted else answer_text.splitlines()[0] if answer_text else ""
    coverage = rubric_coverage(output, item)
    answer_correct = _subject_match(answer_text, item)
    strict_correct = _subject_match(strict_text, item)
    quality = answer_correct and (coverage is None or coverage >= 2 / 3)
    return {
        "format_ok": formatted,
        "answer_correct": answer_correct,
        "strict_correct": strict_correct,
        "quality": quality,
        "rubric_coverage": coverage,
        "final_answer": final[:160],
    }


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    latencies = [row["ms"] for row in rows[1:]]
    speeds = [row["tokens_per_s"] for row in rows if row.get("tokens_per_s") == row.get("tokens_per_s")]
    categories: dict[str, list[dict]] = {}
    for row in rows:
        categories.setdefault(row["category"], []).append(row)
    per_category = {}
    for category, members in sorted(categories.items()):
        per_category[category] = {
            "n": len(members),
            "answer": _mean([float(m["answer_correct"]) for m in members]),
            "strict": _mean([float(m["strict_correct"]) for m in members]),
            "quality": _mean([float(m["quality"]) for m in members]),
        }
    rubric = [row["rubric_coverage"] for row in rows if row["rubric_coverage"] is not None]
    return {
        "n": n,
        "answer_accuracy": _mean([float(row["answer_correct"]) for row in rows]),
        "strict_accuracy": _mean([float(row["strict_correct"]) for row in rows]),
        "format_rate": _mean([float(row["format_ok"]) for row in rows]),
        "quality_accuracy": _mean([float(row["quality"]) for row in rows]),
        "rubric_coverage_mean": _mean(rubric),
        "latency_ms_p50_excl_first": round(percentile(latencies, 50), 1) if latencies else None,
        "latency_ms_p95_excl_first": round(percentile(latencies, 95), 1) if latencies else None,
        "tokens_per_s_median": round(statistics.median(speeds), 2) if speeds else None,
        "mean_gen_tokens": _mean([float(row["gen_tokens"]) for row in rows]),
        "per_category": per_category,
    }


def run_model(host: str, tag: str, suite: list[dict], max_tokens: int, n_ctx: int,
              digests: dict[str, str]) -> dict:
    cfg = ModelConfig(backend="ollama", model=tag, host=host, n_ctx=n_ctx,
                      keep_alive="10m", timeout_s=900)
    model = OllamaModel(cfg)
    rows: list[dict] = []
    load_ms = 0.0
    for index, item in enumerate(suite):
        prompt = (item["prompt"] + "\n\nAnswer concisely. Put the final answer on its own line "
                  "exactly as: Final answer: <answer>")
        started = time.perf_counter()
        output = model.generate(prompt, max_tokens)
        elapsed_ms = (time.perf_counter() - started) * 1000
        stats = model.last_stats
        if index == 0:
            load_ms = stats.load_duration_ns / 1e6
        scored = score_item(output, item)
        rows.append({
            "id": item["id"],
            "category": item["category"],
            **scored,
            "ms": round(elapsed_ms, 1),
            "gen_tokens": stats.eval_count,
            "tokens_per_s": stats.tokens_per_s,
            "output": output[:600],
        })
    server = {m["name"]: m for m in running_models(host)}.get(tag, {})
    result = {
        "model": tag,
        "digest": digests.get(tag, "")[:12],
        "load_ms": round(load_ms, 1),
        "server_mem_mb": round(server.get("size", 0) / 1e6, 1),
        "server_vram_mb": round(server.get("size_vram", 0) / 1e6, 1),
        **summarize(rows),
        "rows": rows,
    }
    return result


def _paired(res: dict, reference: dict, key: str) -> dict:
    ref = {row["id"]: row for row in reference["rows"]}
    pairs = [(row, ref[row["id"]]) for row in res["rows"] if row["id"] in ref]
    wins = sum(1 for candidate, base in pairs if candidate[key] and not base[key])
    losses = sum(1 for candidate, base in pairs if not candidate[key] and base[key])
    ties = len(pairs) - wins - losses
    return {"wins": wins, "losses": losses, "ties": ties, "p_value": round(sign_test_p(wins, losses), 4)}


def compare(results: dict[str, dict], reference: str, alpha: float = 0.05) -> dict[str, dict]:
    out = {}
    base = results[reference]
    for tag, res in results.items():
        if tag == reference:
            continue
        quality = _paired(res, base, "quality")
        if quality["p_value"] < alpha and quality["wins"] > quality["losses"]:
            verdict = "better than reference"
        elif quality["p_value"] < alpha and quality["losses"] > quality["wins"]:
            verdict = "worse than reference"
        else:
            verdict = "no detectable difference from reference"
        out[tag] = {
            "verdict": verdict,
            "quality": quality,
            "answer": _paired(res, base, "answer_correct"),
            "strict": _paired(res, base, "strict_correct"),
        }
    return out


def _fmt(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def markdown(results: dict, comparison: dict, reference: str, suite_path: str, digest: str,
             options: dict) -> str:
    first = next(iter(results.values()))
    categories = list(first["per_category"])
    lines = [
        f"# Subject tutor benchmark - {time.strftime('%Y-%m-%d %H:%M')}", "",
        f"Suite: `{suite_path}` (sha256 `{digest}`), n={first['n']}, categories={len(categories)}, "
        f"reference = `{reference}`. Machine: {platform.platform()}, Python {sys.version.split()[0]}.", "",
        f"Options: `{json.dumps(options, sort_keys=True)}`.", "",
        "| model | answer | strict | format | quality | 95% CI (quality) | p50 ms | p95 ms | tok/s | load s | server MB | VRAM MB | vs reference |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for tag, res in results.items():
        low, high = wilson(sum(1 for row in res["rows"] if row["quality"]), res["n"])
        if tag == reference:
            versus = "reference"
        else:
            comp = comparison[tag]
            versus = (f"{comp['verdict']} (quality {comp['quality']['wins']}/"
                      f"{comp['quality']['losses']}, p={comp['quality']['p_value']:.3f})")
        lines.append(
            f"| {tag} | {_fmt(res['answer_accuracy'])} | {_fmt(res['strict_accuracy'])} | "
            f"{_fmt(res['format_rate'])} | {_fmt(res['quality_accuracy'])} | "
            f"{low:.2f}-{high:.2f} | {_fmt(res['latency_ms_p50_excl_first'], 0)} | "
            f"{_fmt(res['latency_ms_p95_excl_first'], 0)} | {_fmt(res['tokens_per_s_median'], 1)} | "
            f"{res['load_ms'] / 1000:.1f} | {res['server_mem_mb']:.0f} | {res['server_vram_mb']:.0f} | {versus} |"
        )
    lines += ["", "Per-category quality accuracy:", "",
              "| model | " + " | ".join(categories) + " |",
              "|---|" + "---|" * len(categories)]
    for tag, res in results.items():
        lines.append(f"| {tag} | " + " | ".join(
            _fmt(res["per_category"][category]["quality"]) for category in categories) + " |")
    lines += ["", "Per-category answer accuracy:", "",
              "| model | " + " | ".join(categories) + " |",
              "|---|" + "---|" * len(categories)]
    for tag, res in results.items():
        lines.append(f"| {tag} | " + " | ".join(
            _fmt(res["per_category"][category]["answer"]) for category in categories) + " |")
    lines += [
        "", "Read this with care: 42 author-written items cannot establish general tutoring quality. "
        "The suite was frozen and hashed before either model ran; it was not independently authored. "
        "The base-model comparison was not run (no base checkpoint downloaded); base superiority is a "
        "user-reported prior result, not a measurement in this report. No privacy test was run.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frozen subject-tutor model comparison")
    parser.add_argument("--host", default="http://127.0.0.1:11434")
    parser.add_argument("--models", nargs="*", default=None)
    parser.add_argument("--reference", default=DEFAULT_REFERENCE)
    parser.add_argument("--suite", default=DEFAULT_SUITE)
    parser.add_argument("--max-tokens", type=int, default=160)
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
               "num_ctx": args.n_ctx}

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
        print(f"    answer {result['answer_accuracy']:.2f}  quality {result['quality_accuracy']:.2f}  "
              f"p50 {result['latency_ms_p50_excl_first']} ms  "
              f"{result['tokens_per_s_median']} tok/s  {result['server_mem_mb']:.0f} MB", flush=True)
        try:
            unload(args.host, tag)
        except OllamaError:
            pass

    comparison = compare(results, args.reference)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    report = {
        "experiment": "SUBJECT-001",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "suite": args.suite,
        "suite_sha256": digest,
        "options": options,
        "reference": args.reference,
        "environment": {"platform": platform.platform(), "python": sys.version.split()[0],
                        "host": args.host},
        "runtime_s": round(time.perf_counter() - started, 2),
        "results": results,
        "comparison": comparison,
    }
    (out_dir / f"subject_{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    text = markdown(results, comparison, args.reference, args.suite, digest, options)
    (out_dir / f"subject_{stamp}.md").write_text(text, encoding="utf-8")
    print("\n" + text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
