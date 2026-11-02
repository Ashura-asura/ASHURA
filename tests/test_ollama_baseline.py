import json

from evaluation.ollama_baseline import compare, main, sign_test_p, wilson, write_module_costs
from tests.test_ollama import Fake, host, TAGS  # noqa: F401  (fixture + fake server)


def _res(strict_flags):
    return {"rows": [{"id": f"q{i}", "strict": f} for i, f in enumerate(strict_flags)]}


def test_sign_test_and_wilson():
    assert sign_test_p(0, 0) == 1.0
    assert sign_test_p(8, 0) < 0.01 and sign_test_p(5, 4) > 0.5
    lo, hi = wilson(8, 16)
    assert lo < 0.5 < hi and 0.0 <= lo and hi <= 1.0


def test_small_gaps_are_not_called_differences():
    ref = _res([True] * 8 + [False] * 8)
    better_by_two = _res([True] * 10 + [False] * 6)          # 2 wins, 0 losses -> p = 0.5
    much_better = _res([True] * 16)                           # 8 wins, 0 losses -> p ~ 0.008
    c = compare({"ref": ref, "a": better_by_two, "b": much_better}, "ref")
    assert c["a"]["verdict"] == "no detectable difference from reference"
    assert c["b"]["verdict"] == "better than reference"


def test_end_to_end_with_fake_server(host, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evaluation" / "benchmarks").mkdir(parents=True)
    suite = tmp_path / "suite.jsonl"
    suite.write_text(json.dumps({"id": "a1", "prompt": "What is 17 * 23?", "accept": ["391"], "category": "arithmetic"}) + "\n"
                     + json.dumps({"id": "a2", "prompt": "What is 2 + 2?", "accept": ["4"], "category": "arithmetic"}) + "\n")
    rc = main(["--host", host, "--suite", str(suite), "--models", "lfm3:latest", "--out-dir", str(tmp_path / "res"),
               "--calibrate", "lfm3:latest"])
    assert rc == 0
    report = json.loads(next((tmp_path / "res").glob("baseline_*.json")).read_text())
    assert set(report["results"]) == {"ref-base:7b", "lfm3:latest"}            # reference is always included
    assert report["results"]["ref-base:7b"]["strict"] == 0.5                  # fake server always answers 391
    assert (tmp_path / "config" / "module_costs.json").exists()


def test_unknown_model_is_reported_not_crashed(host, tmp_path):
    assert main(["--host", host, "--models", "does-not-exist:7b", "--out-dir", str(tmp_path)]) == 2
