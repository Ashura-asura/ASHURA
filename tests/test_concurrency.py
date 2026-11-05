"""F-047: bounded client-side concurrency and Ollama wiring."""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from foundation.concurrency import ConcurrencyGate, QueueFullError, QueueTimeoutError
from foundation.model_config import ModelConfig, load_model_config
from foundation import ollama_model as om


def test_shipped_ollama_profiles_have_a_bounded_gate():
    for path in ("config/ashura.ollama.toml", "config/ashura.ollama.private.toml"):
        cfg = load_model_config(path)
        assert (cfg.max_inflight, cfg.max_queue, cfg.queue_timeout_s) == (1, 8, 60)


def test_gate_limits_in_flight_and_releases():
    gate = ConcurrencyGate(max_inflight=1, max_queue=4, queue_timeout_s=2)
    gate.acquire()
    assert gate.snapshot().in_flight == 1

    def worker():
        gate.acquire()
        time.sleep(0.05)
        gate.release()

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.02)
    assert gate.snapshot().queued == 1
    gate.release()
    t.join(timeout=2)
    assert not t.is_alive()
    snap = gate.snapshot()
    assert snap.in_flight == 0 and snap.served == 2 and snap.max_in_flight_seen == 1
    assert snap.wait_samples == 2


def test_gate_rejects_a_full_queue_immediately():
    gate = ConcurrencyGate(max_inflight=1, max_queue=0, queue_timeout_s=2)
    gate.acquire()
    with pytest.raises(QueueFullError, match="queue is full"):
        gate.acquire()
    assert gate.snapshot().rejected_full == 1
    gate.release()


def test_gate_times_out_instead_of_waiting_forever():
    gate = ConcurrencyGate(max_inflight=1, max_queue=1, queue_timeout_s=0.05)
    gate.acquire()
    with pytest.raises(QueueTimeoutError, match="no inference slot"):
        gate.acquire()
    assert gate.snapshot().rejected_timeout == 1
    gate.release()


def test_gate_releases_after_an_exception_and_rejects_unpaired_release():
    gate = ConcurrencyGate(max_inflight=1, max_queue=0, queue_timeout_s=1)
    with pytest.raises(ValueError):
        with gate.slot():
            raise ValueError("boom")
    assert gate.snapshot().in_flight == 0
    with pytest.raises(RuntimeError, match="without a matching"):
        gate.release()


def test_ollama_model_applies_the_gate(monkeypatch):
    monkeypatch.setattr(om, "list_models", lambda host: [{"name": "fake:7b", "digest": "a" * 64}])
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_call(host, path, payload=None, timeout=30.0):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return {"response": "ok", "eval_count": 1, "eval_duration": 1_000_000}

    monkeypatch.setattr(om, "_call", fake_call)
    model = om.OllamaModel(ModelConfig(backend="ollama", model="fake:7b", host="http://fake",
                                       max_inflight=1, max_queue=4, queue_timeout_s=2))
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: model.generate("p"), range(8))) == ["ok"] * 8
    assert peak == 1
    assert model.gate.snapshot().served == 8


def test_unlimited_model_has_no_gate(monkeypatch):
    monkeypatch.setattr(om, "list_models", lambda host: [{"name": "fake:7b", "digest": "a" * 64}])
    model = om.OllamaModel(ModelConfig(backend="ollama", model="fake:7b", host="http://fake"))
    assert model.gate is None
