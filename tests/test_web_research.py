import gzip
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from skills.web import (WebConfig, WebError, WebFactStore, WebPage, WebResult, WebSearch,
                        looks_uncertain, needs_web)
from foundation.language_model import EchoModel
from skills.web import _NoRedirect, _decode_body, _validate_url


def test_config_rejects_invalid_providers_and_limits():
    with pytest.raises(ValueError, match="provider"):
        WebConfig(provider="bing")
    with pytest.raises(ValueError, match="searx_url"):
        WebConfig(provider="searxng")
    with pytest.raises(ValueError, match="max_results"):
        WebConfig(max_results=50)
    with pytest.raises(ValueError, match="max_fetch_pages"):
        WebConfig(max_fetch_pages=9)
    with pytest.raises(ValueError, match="unknown key"):
        WebConfig.from_dict({"enabled": True, "providerr": "duckduckgo"})
    assert WebConfig.from_dict({"enabled": True, "max_results": 3}).max_results == 3


def test_url_guard_rejects_non_http_private_and_credentialed_urls():
    for value in ("file:///etc/passwd", "ftp://example.com/x", "",
                  "http://user:pass@example.com/", "http://127.0.0.1:8080/",
                  "http://localhost/", "http://10.0.0.5/", "http://[::1]/"):
        with pytest.raises(WebError):
            _validate_url(value, allow_private=False)
    assert _validate_url("https://example.com", allow_private=False) == "https://example.com/"


def test_redirect_handler_is_disabled():
    handler = _NoRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "http://example.com") is None


def test_compressed_response_cannot_bypass_the_byte_limit():
    payload = b"a" * 10_000
    assert len(_decode_body(gzip.compress(payload), "gzip", 20_000)) == len(payload)
    with pytest.raises(WebError, match="expands beyond"):
        _decode_body(gzip.compress(payload), "gzip", 100)
    with pytest.raises(WebError, match="could not decompress"):
        _decode_body(b"not-gzip", "gzip", 100)


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # keep test output quiet
        pass

    def do_GET(self):
        if self.path == "/page":
            body = (b"<html><head><title>Demo page</title></head><body>"
                    b"<h1>Heading</h1><p>Readable body.</p><script>bad()</script>"
                    b"</body></html>")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        elif self.path == "/json":
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/binary":
            body = b"\x89PNG\r\n\x1a\n"
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
        elif self.path == "/redirect-private":
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
            body = b""
        elif self.path == "/redirect-page":
            self.send_response(302)
            self.send_header("Location", "/page")
            body = b""
        else:
            body = b"missing"
            self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def local_http(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # The guard normally rejects loopback. Allow the test server while still treating the
    # cloud metadata address as private, so redirect validation is exercised honestly.
    import skills.web as web_module

    real = web_module._is_private_host

    def fake(host):
        if host in {"127.0.0.1", "localhost"}:
            return False
        if host == "169.254.169.254":
            return True
        return real(host)

    monkeypatch.setattr(web_module, "_is_private_host", fake)
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def _search(enabled=True, **overrides):
    config = WebConfig(enabled=enabled, **overrides)
    web = WebSearch(config)
    web._throttle = lambda: None
    return web


def test_fetch_is_disabled_without_operator_opt_in():
    with pytest.raises(WebError, match="disabled"):
        _search(enabled=False).fetch("https://example.com")
    with pytest.raises(WebError, match="disabled"):
        _search(enabled=False).search("anything")


def test_fetch_extracts_text_and_respects_content_type(local_http):
    web = _search()
    page = web.fetch(local_http + "/page")
    assert page.title == "Demo page"
    assert "Readable body." in page.text
    assert "bad()" not in page.text
    assert page.content_type.startswith("text/html")

    payload = web.fetch(local_http + "/json")
    assert json.loads(payload.text) == {"ok": True}

    with pytest.raises(WebError, match="non-text"):
        web.fetch(local_http + "/binary")


def test_redirects_are_followed_only_after_revalidation(local_http):
    web = _search()
    page = web.fetch(local_http + "/redirect-page")
    assert "Readable body." in page.text

    with pytest.raises(WebError, match="loopback, private"):
        web.fetch(local_http + "/redirect-private")


def test_fact_store_dedupes_and_resolves_gaps(tmp_path):
    store = WebFactStore(":memory:")
    first = store.record_gap("What changed today?", "I do not know.", session_id="s1")
    again = store.record_gap("what changed TODAY?", "Still unsure.", session_id="s1")
    assert first == again
    assert store.stats()["open_gaps"] == 1

    sources = [{"title": "Source", "url": "https://example.com/a", "snippet": "s"}]
    fact = store.record_fact("What changed today?", "A new release shipped.", sources,
                             session_id="s1", provider="duckduckgo")
    duplicate = store.record_fact("What changed today?", "A new release shipped.", sources,
                                  session_id="s1", provider="duckduckgo")
    assert fact == duplicate
    assert store.stats() == {"facts": 1, "candidates": 1, "verified": 0,
                             "gaps": 1, "open_gaps": 0}
    stored = store.list_facts()
    assert stored[0]["sources"] == sources


def test_review_status_changes_counters_without_claiming_verification():
    store = WebFactStore(":memory:")
    fact = store.record_fact("Question?", "Answer.", [{"url": "https://example.com"}])
    store.set_status(fact, "verified", "operator checked the source")
    assert store.stats()["verified"] == 1
    assert store.list_facts(status="verified")[0]["review_note"] == "operator checked the source"
    with pytest.raises(KeyError):
        store.set_status(9999, "verified")
    with pytest.raises(ValueError):
        store.set_status(fact, "trusted")


def test_export_is_reviewable_and_never_training_ready(tmp_path):
    store = WebFactStore(":memory:")
    keep = store.record_fact("Kept question", "Kept answer",
                             [{"title": "T", "url": "https://example.com/keep"}])
    dropped = store.record_fact("Rejected question", "Rejected answer", [])
    store.set_status(keep, "verified")
    store.set_status(dropped, "rejected")

    result = store.export_dataset(tmp_path)
    assert result["training_ready"] is False
    rows = [json.loads(line) for line in
            (tmp_path / "web_training.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["question"] == "Kept question"
    assert rows[0]["training_ready"] is False
    assert rows[0]["review_required"] is True
    assert rows[0]["verification_status"] == "unverified_web_source"
    manifest = json.loads((tmp_path / "web_training_manifest.json").read_text(encoding="utf-8"))
    assert manifest["training_ready"] is False
    assert manifest["records"] == 1

    included = store.export_dataset(tmp_path, include_rejected=True)
    assert included["records"] == 2


def test_uncertainty_and_web_cues_are_conservative():
    assert looks_uncertain("I do not know the answer.")
    assert looks_uncertain("That is beyond my knowledge cutoff.")
    assert not looks_uncertain("Paris is the capital of France.")
    assert needs_web("What is the latest release?")
    assert needs_web("Search the web for this error")
    assert not needs_web("Explain the difference between lists and tuples")


class _FakeWeb(WebSearch):
    def __init__(self):
        super().__init__(WebConfig(enabled=True))

    def search(self, query, limit=None):
        return [WebResult("Python release", "https://example.com/python",
                          "The page says Python 3.14 is current.", "fake")]

    def fetch(self, url, *, max_chars=20_000):
        return WebPage(url, "Python release", "Python 3.14 is the current release.",
                       "text/html", False)


class _UncertainThenGrounded(EchoModel):
    def __init__(self):
        self.prompts = []

    def generate(self, prompt, max_tokens=128):
        self.prompts.append(prompt)
        if "Web research (external text" in prompt:
            return "The current release is Python 3.14, according to the fetched page."
        return "I do not know the current Python release."


class _ToolCallingModel(EchoModel):
    def __init__(self):
        self.rounds = []

    def chat(self, messages, tools=None, max_tokens=128):
        self.rounds.append({"messages": list(messages), "tools": tools})
        if len(self.rounds) == 1:
            return {"content": "", "finish_reason": "stop", "tool_calls": [
                {"function": {"name": "list_files", "arguments": {"path": "."}}}]}
        return {"content": "The workspace contains README.md.", "finish_reason": "stop",
                "tool_calls": []}


class _TruncatedThenContinued(EchoModel):
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, max_tokens=128):
        self.calls += 1
        if self.calls == 1:
            self.last_finish_reason = "length"
            return "Step 1: begin the derivation."
        self.last_finish_reason = "stop"
        return "Step 2: finish the derivation."


def test_controller_web_fallback_records_a_gap_then_a_candidate_fact():
    from brain.controller import Controller
    from brain.need_field import Task
    from foundation.language_model import EchoModel
    from learning.ama import AMA
    from memory.database import Database

    store = WebFactStore(":memory:")
    model = _UncertainThenGrounded()
    controller = Controller(model, ama=AMA(Database(":memory:")),
                            web=_FakeWeb(), fact_store=store)
    try:
        response = controller.handle(Task("What is the internal ASHURA release codename?"))
        assert "3.14" in response.text
        assert response.web["auto_fallback"] is True
        assert response.web["gap_id"] is not None
        assert response.web["fact_id"] is not None
        assert len(response.sources) == 1
        assert len(model.prompts) == 2
        stats = store.stats()
        assert stats["facts"] == 1
        assert stats["candidates"] == 1
        assert stats["open_gaps"] == 0
        assert any(step.module == "web_fallback" for step in response.trace.steps)
    finally:
        controller.close()


def test_controller_executes_a_tool_round_and_emits_the_tool_observation(tmp_path):
    from brain.controller import Controller
    from brain.need_field import Task
    from brain.tools import ToolRegistry
    from learning.ama import AMA
    from memory.database import Database

    (tmp_path / "README.md").write_text("# Project\n", encoding="utf-8")
    model = _ToolCallingModel()
    controller = Controller(model, ama=AMA(Database(":memory:")),
                            tools=ToolRegistry(tmp_path))
    try:
        chunks = []
        response = controller.handle(Task("List the files in this workspace"), chunks.append)
        assert "README.md" in response.text
        assert response.tool_calls and response.tool_calls[0]["name"] == "list_files"
        assert response.tool_calls[0]["ok"] is True
        assert any(step.module == "tool:list_files" for step in response.trace.steps)
        assert "".join(chunks) == response.text
    finally:
        controller.close()


def test_controller_continues_a_length_truncated_answer():
    from brain.controller import Controller
    from brain.need_field import Task
    from learning.ama import AMA
    from memory.database import Database

    model = _TruncatedThenContinued()
    controller = Controller(model, ama=AMA(Database(":memory:")))
    try:
        response = controller.handle(Task("Explain step by step how routing works"))
        assert "Step 1" in response.text and "Step 2" in response.text
        assert response.truncated is False
        assert model.calls == 2
        assert any("continued 1 time" in (step.note or "") for step in response.trace.steps)
    finally:
        controller.close()
