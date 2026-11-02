"""OllamaModel against a fake local Ollama server (no real Ollama needed)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from foundation.language_model import build_model
from foundation.model_config import ModelConfig
from foundation.ollama_model import OllamaError, OllamaModel, list_models, running_models

TAGS = {"models": [
    {"name": "ref-base:7b", "digest": "130777f43a36" + "0" * 52, "size": 4_700_000_000},
    {"name": "lfm3:latest", "digest": "b36a103fe2f8" + "0" * 52, "size": 1_100_000_000},
]}


class Fake(BaseHTTPRequestHandler):
    calls: list = []

    def log_message(self, *a):  # silence
        pass

    def _send(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/tags":
            self._send(TAGS)
        elif self.path == "/api/ps":
            self._send({"models": [{"name": "ref-base:7b", "size": 5_000_000_000, "size_vram": 0}]})
        else:
            self.send_error(404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.calls.append(body)
        self._send({"response": " 391 ", "eval_count": 10, "eval_duration": 500_000_000, "prompt_eval_count": 5,
                    "load_duration": 1, "total_duration": 2})


@pytest.fixture()
def host():
    Fake.calls = []
    srv = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_list_and_ps(host):
    assert [m["name"] for m in list_models(host)] == ["ref-base:7b", "lfm3:latest"]
    assert running_models(host)[0]["size"] == 5_000_000_000


def test_generate_is_greedy_and_records_stats(host):
    m = OllamaModel(ModelConfig(backend="ollama", model="ref-base:7b", host=host, digest="130777f43a36", n_ctx=4096))
    assert m.generate("Question: 17*23", max_tokens=32) == "391"
    opts = Fake.calls[-1]["options"]
    assert opts["temperature"] == 0 and opts["seed"] == 0 and opts["num_predict"] == 32 and opts["num_ctx"] == 4096
    assert Fake.calls[-1]["stream"] is False
    assert m.last_stats.eval_count == 10 and m.last_stats.tokens_per_s == pytest.approx(20.0)


def test_digest_mismatch_is_refused(host):
    with pytest.raises(RuntimeError, match="digest mismatch"):
        OllamaModel(ModelConfig(backend="ollama", model="ref-base:7b", host=host, digest="deadbeef0000"))


def test_missing_model_and_dead_server_give_clear_errors(host):
    with pytest.raises(OllamaError, match="not installed"):
        OllamaModel(ModelConfig(backend="ollama", model="nope:7b", host=host))
    with pytest.raises(OllamaError, match="ollama serve"):
        list_models("http://127.0.0.1:9")


def test_build_model_dispatches_to_ollama_and_pinning_uses_digest(host):
    cfg = ModelConfig(backend="ollama", model="lfm3:latest", host=host, digest="b36a103fe2f8", licence="check")
    assert isinstance(build_model(cfg), OllamaModel) and cfg.is_pinned
    assert not ModelConfig(backend="ollama", model="lfm3:latest", host=host).is_pinned
