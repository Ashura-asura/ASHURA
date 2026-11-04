"""Regression tests for the production-hardening pass. Each test pins a bug that existed before."""
import json
import sqlite3
import sys
import threading
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pytest

from app.main import build, parse_command, resolve_config
from brain.need_field import Task
from foundation.model_config import ModelConfig, load_model_config
from foundation.ollama_model import OllamaError, list_models
from learning.dream import DreamConfig
from learning.replay import ReplayBuffer
from memory.adaptive_memory import AMemConfig, AdaptiveMemory
from memory.database import Database
from memory.episodic import EpisodicMemory, Experience
from plasticity.slow_weights import CheckpointStore
from skills.arithmetic import exact, neural_expert
from skills.arithmetic.parser import extract_expression, is_pure_arithmetic


# ---------------------------------------------------------------- arithmetic
def test_huge_exact_result_is_formatted_not_a_crash():
    text = exact.format_value(exact.evaluate("2**20000"))          # 6021 digits: str() used to raise ValueError
    assert text.startswith("3.98") and "e+6020" in text and "6021 digits" in text
    assert exact.format_value(exact.evaluate("2**100")) == str(2 ** 100)   # normal sizes are printed in full


def test_format_value_does_not_touch_the_global_decimal_context():
    import decimal
    before = decimal.getcontext().prec
    exact.format_value(exact.evaluate("1/3"))
    exact.verify("1/3", exact.evaluate("1/3"))
    assert decimal.getcontext().prec == before


@pytest.mark.parametrize("bad", ["(" * 5000 + "1" + ")" * 5000, "1" * 5000 + "+1", "9**9**9", "\x00 1+1"])
def test_pathological_expressions_raise_arithmetic_error_only(bad):
    with pytest.raises(ArithmeticError):
        exact.evaluate(bad)


def test_chained_multiplication_cannot_exhaust_memory():
    # Each power is inside the per-operation limit; only the multiplication chain can exceed it.
    expr = "(2**100000)*(2**100000)"
    with pytest.raises(ArithmeticError, match="too large"):
        exact.evaluate(expr)


@pytest.mark.parametrize("text", ["what is the date 2026-11-05", "it happened on 11/05/2026", "call 555-123-4567"])
def test_dates_and_phone_numbers_are_not_arithmetic(text):
    assert extract_expression(text) is None and not is_pure_arithmetic(text)


@pytest.mark.parametrize("text,expr", [("100-50-25", "100-50-25"), ("what is 2026 - 11 - 05", "2026 - 11 - 05"),
                                       ("what is 10/5/2", "10/5/2")])
def test_real_arithmetic_that_resembles_dates_still_works(text, expr):
    assert extract_expression(text) == expr


# ---------------------------------------------------------------- memory
def test_old_database_is_migrated_and_conflict_lookup_uses_the_index(tmp_path):
    path = str(tmp_path / "old.db")
    raw = sqlite3.connect(path)
    raw.executescript("""CREATE TABLE experiences (id TEXT PRIMARY KEY, ts REAL NOT NULL, input TEXT NOT NULL,
        output TEXT NOT NULL, task_category TEXT NOT NULL DEFAULT 'general', source TEXT NOT NULL DEFAULT 'interaction',
        verification_status TEXT NOT NULL DEFAULT 'unverified', reliability REAL NOT NULL DEFAULT 0.2,
        outcome TEXT NOT NULL DEFAULT 'unknown', content_hash TEXT NOT NULL, repeat_count INTEGER NOT NULL DEFAULT 1,
        related_ids TEXT NOT NULL DEFAULT '[]');
        INSERT INTO experiences(id,ts,input,output,content_hash) VALUES ('a',1,'  Hello   World ','x','h');""")
    raw.commit(); raw.close()
    with Database(path) as db:
        mem = EpisodicMemory(db)
        assert [e.id for e in mem.find_by_input("hello world")] == ["a"]       # backfilled during migration
        plan = " ".join(r[3] for r in db.conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM experiences WHERE input_norm = ? AND task_category = COALESCE(?, task_category)",
            ("x", None)))
        assert "idx_exp_input_norm" in plan
    with Database(path):                                                        # migrating twice is harmless
        pass


def test_database_sets_a_busy_timeout(tmp_path):
    with Database(str(tmp_path / "t.db")) as db:
        assert db.conn.execute("PRAGMA busy_timeout").fetchone()[0] >= 1000


# ---------------------------------------------------------------- Ollama / config
def _serve(body: bytes):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize("body,match", [(b"<html>not json</html>", "invalid JSON"), (b"[1, 2]", "JSON object"),
                                        (b'{"error": "model crashed"}', "model crashed")])
def test_ollama_bad_responses_become_ollama_error(body, match):
    srv = _serve(body)
    try:
        with pytest.raises(OllamaError, match=match):
            list_models(f"http://127.0.0.1:{srv.server_port}")
    finally:
        srv.shutdown()


def test_config_typos_and_bad_values_give_clear_errors(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text('[foundation]\nbackend = "echo"\nchekpoint = "x"\n')
    with pytest.raises(ValueError, match="unknown .*chekpoint"):
        load_model_config(f)
    f.write_text("[memory]\n")
    with pytest.raises(ValueError, match="missing the .foundation. section"):
        load_model_config(f)
    with pytest.raises(ValueError, match="backend"):
        ModelConfig(backend="gpt")
    with pytest.raises(ValueError):
        ModelConfig(n_ctx=0)


# ---------------------------------------------------------------- CLI
def test_cli_builds_from_config_and_applies_working_memory_settings(tmp_path):
    f = tmp_path / "c.toml"
    f.write_text(f'[foundation]\nbackend = "echo"\n[memory]\ndb_path = "{(tmp_path / "m.db").as_posix()}"\n'
                 "working_memory_slots = 3\nworking_memory_ttl_s = 42\n")
    with build(str(f)) as c:
        assert c.wm.slots == 3 and c.wm.ttl_s == 42        # these config keys used to be silently ignored


def test_cli_closes_the_database_when_startup_fails(tmp_path, monkeypatch):
    f = tmp_path / "c.toml"
    f.write_text(f'[foundation]\nbackend = "echo"\n[memory]\ndb_path = "{(tmp_path / "m.db").as_posix()}"\n')
    closed = []
    real_close = Database.close
    monkeypatch.setattr(Database, "close", lambda self: (closed.append(1), real_close(self))[1])
    monkeypatch.setattr("app.main.build_model", lambda cfg: (_ for _ in ()).throw(RuntimeError("model missing")))
    with pytest.raises(RuntimeError):
        build(str(f))
    assert closed


def test_cli_ocr_command_forces_the_module_and_other_commands_parse():
    t = parse_command("/ocr \"C:/some dir/a.png\"")
    assert isinstance(t, Task) and t.image_path == "C:/some dir/a.png" and t.force == ("ocr",)
    assert parse_command("/ocr") is None and parse_command("/help") is None
    assert parse_command("what is 2+2") == "what is 2+2"
    with pytest.raises(SystemExit):
        parse_command("/quit")


def test_config_is_found_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_config("config/ashura.toml").name == "ashura.toml"
    with pytest.raises(FileNotFoundError):
        resolve_config("config/nope.toml")


# ---------------------------------------------------------------- checkpoints / DREAM
def test_checkpoint_names_cannot_escape_the_store(tmp_path):
    store = CheckpointStore(tmp_path / "ck")
    art = tmp_path / "a.npz"; art.write_bytes(b"x")
    for bad in ["../evil.npz", "sub/dir.npz", "..", ""]:
        with pytest.raises(ValueError):
            store.stage(art, bad)


def test_promote_refuses_to_overwrite_a_different_stable_file(tmp_path):
    from evaluation.ngr import NGRResult
    store = CheckpointStore(tmp_path / "ck")
    ok = NGRResult(True, ["ok"], {})
    a = tmp_path / "m.npz"; a.write_bytes(b"one")
    store.stage(a, "m.npz"); store.promote("m.npz", ok)
    (store.root / "candidates" / "m.npz").write_bytes(b"two")          # same name, different content
    with pytest.raises(FileExistsError):
        store.promote("m.npz", ok)
    assert (store.root / "stable" / "m.npz").read_bytes() == b"one"    # stable artifact untouched
    assert not list((store.root / "stable").glob("*.tmp"))


def test_corrupt_manifest_gives_a_clear_error(tmp_path):
    store = CheckpointStore(tmp_path / "ck")
    store.manifest.write_text("{not json")
    with pytest.raises(RuntimeError, match="corrupt"):
        store.current()


@pytest.mark.parametrize("ratio", [0.0, -1.0, 1.5])
def test_dream_and_replay_reject_invalid_new_ratio(ratio):
    with pytest.raises(ValueError):
        DreamConfig(new_ratio=ratio)
    with pytest.raises(ValueError):
        ReplayBuffer().replay_set("new", new_ratio=ratio)


# ---------------------------------------------------------------- neural candidate / adaptive memory
def _trained_checkpoint(tmp_path):
    e = neural_expert.NeuralAdditionExpert()
    e.train(neural_expert.AdditionExpertConfig(a_min=-20, a_max=20, b_min=-20, b_max=20), n=4000)
    p = tmp_path / "addition.npz"; e.save(str(p))
    return p


def test_neural_checkpoint_is_loaded_once_and_reloaded_on_change(tmp_path, monkeypatch):
    p = _trained_checkpoint(tmp_path)
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(p))
    neural_expert._cache.clear()
    loads = []
    real = neural_expert.NeuralAdditionExpert.load_if_available
    monkeypatch.setattr(neural_expert.NeuralAdditionExpert, "load_if_available",
                        classmethod(lambda cls, path=None: (loads.append(1), real.__func__(cls, path))[1]))
    for _ in range(5):
        assert neural_expert.try_neural_addition("2+3") == Fraction(5)
    assert len(loads) == 1                                              # was: one disk read per request
    p.write_bytes(p.read_bytes()); import os; os.utime(p, (p.stat().st_atime, p.stat().st_mtime + 5))
    neural_expert.try_neural_addition("2+3")
    assert len(loads) == 2                                              # a replaced checkpoint is picked up


def test_neural_candidate_declines_numbers_float64_cannot_represent(tmp_path, monkeypatch):
    monkeypatch.setenv("ASHURA_NEURAL_ADDITION_CHECKPOINT", str(_trained_checkpoint(tmp_path)))
    neural_expert._cache.clear()
    assert neural_expert.try_neural_addition(f"{10**400}+1") is None     # float(10**400) raised OverflowError before
    assert neural_expert.try_neural_addition(f"{2**60}+1") is None


def test_adaptive_memory_save_is_exact_path_atomic_and_seed_checked(tmp_path):
    cfg = AMemConfig(dim_k=32, dim_v=32, seed=7)
    m = AdaptiveMemory(cfg); m.write("alpha key", "red")
    path = str(tmp_path / "mem.ckpt")                                    # deliberately NOT ending in .npz
    m.save(path)
    assert (tmp_path / "mem.ckpt").exists() and not (tmp_path / "mem.ckpt.npz").exists()
    assert not (tmp_path / "mem.ckpt.tmp").exists()
    loaded = AdaptiveMemory.load(path, cfg)
    assert loaded.recall("alpha key", ["red", "blue"])[0] == "red"
    with pytest.raises(ValueError, match="seed"):
        AdaptiveMemory.load(path, AMemConfig(dim_k=32, dim_v=32, seed=8))   # used to load and silently scramble recall
