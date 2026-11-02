import os

from evaluation.benchmark_runner import run_benchmark
from evaluation.latency import percentile
from foundation.language_model import EchoModel
from foundation.model_config import load_model_config, protect_checkpoint, sha256_file, verify_checkpoint

SUITE = "evaluation/benchmarks/baseline_v1.jsonl"


def test_benchmark_is_repeatable():
    a, b = run_benchmark(EchoModel(), SUITE), run_benchmark(EchoModel(), SUITE)
    assert a["suite_hash"] == b["suite_hash"] and a["accuracy"] == b["accuracy"] and a["n"] == 16
    assert [r["ok"] for r in a["rows"]] == [r["ok"] for r in b["rows"]]


def test_percentiles():
    assert percentile([1, 2, 3, 4, 5], 50) == 3 and percentile([1, 2, 3, 4, 5], 95) > 4.5


def test_default_config_is_not_pinned_yet():
    assert load_model_config().is_pinned is False      # honest: no checkpoint chosen yet


def test_checkpoint_hash_and_readonly(tmp_path):
    p = tmp_path / "m.gguf"
    p.write_bytes(b"weights")
    h = sha256_file(p)
    assert verify_checkpoint(p, h) and not verify_checkpoint(p, "0" * 64)
    protect_checkpoint(p)
    assert not os.access(p, os.W_OK) or os.geteuid() == 0     # root ignores mode bits
