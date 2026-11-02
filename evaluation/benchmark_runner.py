"""Fixed baseline benchmark (Phase 0). Same suite + greedy decoding => comparable repeated runs."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

from foundation.language_model import LanguageModel

from .judge import judge_both
from .latency import LatencyRecorder


def load_suite(path: str) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def suite_hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def judge(output: str, item: dict) -> bool:
    """Backward-compatible lenient judge; see evaluation/judge.py (echo-stripped, whole-token)."""
    return judge_both(output, item)["lenient"]


def run_benchmark(model: LanguageModel, suite_path: str, max_tokens: int = 64) -> dict:
    suite = load_suite(suite_path)
    rec, per_cat, rows = LatencyRecorder(), {}, []
    rec.start()
    for item in suite:
        out = rec.time(model.generate, f"Question: {item['prompt']}", max_tokens)
        v = judge_both(out, item, prompt=item["prompt"])
        ok = v["lenient"]
        per_cat.setdefault(item["category"], []).append(v["strict"])
        rows.append({"id": item["id"], "ok": ok, "strict_ok": v["strict"], "output": out[:200],
                     "gen_tokens": getattr(getattr(model, "last_stats", None), "eval_count", None)})
    return {
        "model": model.name, "suite": suite_path, "suite_hash": suite_hash(suite_path), "n": len(suite),
        "accuracy": sum(r["ok"] for r in rows) / len(rows),                 # lenient
        "accuracy_strict": sum(r["strict_ok"] for r in rows) / len(rows),   # first-line / first-word
        "per_category_strict": {c: sum(v) / len(v) for c, v in per_cat.items()},
        "latency": rec.summary(), "rows": rows,
        "env": {"python": sys.version.split()[0], "platform": platform.platform(), "time": time.strftime("%Y-%m-%d %H:%M:%S")},
    }
