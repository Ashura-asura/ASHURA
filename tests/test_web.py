import base64
import http.client
import json
import threading
import time
from http.cookies import SimpleCookie

import pytest

from app.sessions import SessionStore
from app.web import AppHTTPServer, WebApp, static_file
from app.worker import ControllerWorker, WorkerQueueFull
from brain.controller import Controller
from foundation.language_model import EchoModel
from learning.ama import AMA
from memory.database import Database


class RecordingModel(EchoModel):
    """Echo stub that remembers the prompts it received."""

    def __init__(self):
        self.prompts = []

    def generate(self, prompt, max_tokens=128):
        self.prompts.append(prompt)
        return super().generate(prompt, max_tokens)


class SlowStreamModel(EchoModel):
    """Streams one chunk, waits for a test signal, then streams another."""

    def __init__(self):
        self.first_chunk = threading.Event()
        self.release = threading.Event()

    def stream(self, prompt, max_tokens=128):
        yield "[echo] first"
        self.first_chunk.set()
        self.release.wait(3)
        yield " second"


def build_web(model=None, token="test-token", csrf="test-csrf"):
    db = Database(":memory:")
    controller = Controller(model or EchoModel(), ama=AMA(db))
    sessions = SessionStore(":memory:")
    app = WebApp(controller, "config/ashura.toml", sessions=sessions,
                 token=token, csrf=csrf)
    return app


@pytest.fixture
def web():
    app = build_web()
    yield app
    app.close()


@pytest.fixture
def server(web):
    httpd = AppHTTPServer(("127.0.0.1", 0), web)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()
    thread.join(timeout=3)


def test_status_reports_model_memory_and_worker(web):
    status = web.status()
    assert status["model"] == "echo-stub"
    assert status["counts"]["experiences"] == 0
    assert status["counts"]["fts_rows"] == 0
    assert status["worker"]["alive"] is True
    assert status["worker"]["max_queue"] == 8
    assert status["csrf"] == "test-csrf"
    assert status["capabilities"]["streaming"] is True


def test_chat_persists_session_messages_and_trace(web):
    result = web.chat("hello local memory")
    assert "[echo]" in result["text"]
    assert result["trace"]["steps"]
    assert result["session_id"]
    assert result["assistant_message_id"]

    detail = web.get_session(result["session_id"])
    assert detail["session"]["title"] == "hello local memory"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["meta"]["trace"]["steps"]
    assert detail["messages"][1]["meta"]["model"] == "echo-stub"

    found = web.memory("hello", limit=5)
    assert any("hello local memory" in item["input"] for item in found["items"])


def test_chat_history_is_injected_into_the_language_prompt():
    model = RecordingModel()
    app = build_web(model)
    try:
        first = app.chat("first question")
        app.chat("second question", first["session_id"])
        assert len(model.prompts) == 2
        assert "first question" in model.prompts[1]
        assert "[echo] first question" in model.prompts[1]
        assert "Question: second question" in model.prompts[1]
    finally:
        app.close()


def test_empty_chat_is_rejected(web):
    with pytest.raises(ValueError, match="empty"):
        web.chat("   ")


def test_streaming_chat_emits_tokens_then_done_and_persists(web):
    session = web.create_session()
    _, job = web.start_chat("stream this", session["id"], stream=True)
    events = []
    while True:
        kind, data = job.events.get(timeout=5)
        events.append((kind, data))
        if kind in {"done", "error", "cancelled"}:
            break
    tokens = "".join(data for kind, data in events if kind == "token")
    assert tokens == "[echo] stream this"
    kind, done = events[-1]
    assert kind == "done"
    assert done["session_id"] == session["id"]
    assert len(web.get_session(session["id"])["messages"]) == 2


def test_cancelling_a_stream_does_not_persist_an_assistant_message():
    model = SlowStreamModel()
    app = build_web(model)
    try:
        session = app.create_session()
        _, job = app.start_chat("cancel me", session["id"], stream=True)
        first_kind, first_data = job.events.get(timeout=5)
        assert (first_kind, first_data) == ("token", "[echo] first")
        job.cancel()
        model.release.set()
        terminal = None
        while True:
            kind, data = job.events.get(timeout=5)
            if kind in {"done", "error", "cancelled"}:
                terminal = (kind, data)
                break
        assert terminal[0] == "cancelled"
        messages = app.get_session(session["id"])["messages"]
        assert [m["role"] for m in messages] == ["user"]
    finally:
        model.release.set()
        app.close()


def test_ocr_rejects_invalid_base64(web):
    with pytest.raises(ValueError, match="base64"):
        web.ocr("scan.png", "not-base64")


def test_ocr_accepts_a_tiny_png_and_persists(web):
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode()
    result = web.ocr("tiny.png", png)
    assert "trace" in result  # OCR may be unavailable; the request path must not crash
    assert result["kind"] == "ocr"
    messages = web.get_session(result["session_id"])["messages"]
    assert messages[0]["content"] == "[image: tiny.png]"
    assert len(messages) == 2


def test_session_rename_export_and_delete(web):
    result = web.chat("export this chat")
    session_id = result["session_id"]
    renamed = web.rename_session(session_id, "Renamed chat")
    assert renamed["title"] == "Renamed chat"
    body, content_type, filename = web.export_session(session_id, "md")
    assert "text/markdown" in content_type
    assert filename.endswith(".md")
    assert "Renamed chat" in body.decode()
    assert "export this chat" in body.decode()
    assert web.delete_session(session_id) is True
    with pytest.raises(KeyError):
        web.get_session(session_id)


def test_worker_serializes_jobs_and_bounds_the_queue():
    worker = ControllerWorker(object(), max_queue=1)
    release = threading.Event()
    started = threading.Event()
    active = 0
    max_active = 0
    lock = threading.Lock()

    def blocking(emit):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        started.set()
        release.wait(5)
        with lock:
            active -= 1
        return "first"

    def quick(emit):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return "second"

    try:
        first = worker.submit(blocking, kind="test")
        assert started.wait(3)
        second = worker.submit(quick, kind="test")
        with pytest.raises(WorkerQueueFull):
            worker.submit(quick, kind="test")
        release.set()
        assert first.wait(5) == "first"
        assert second.wait(5) == "second"
        assert max_active == 1
        assert worker.stats()["rejected"] == 1
    finally:
        release.set()
        worker.close()


def test_session_store_survives_reopen(tmp_path):
    path = tmp_path / "sessions.db"
    store = SessionStore(str(path))
    session = store.create("Persistent")
    store.append(session["id"], "user", "remember me")
    store.append(session["id"], "assistant", "remembered")
    store.close()

    reopened = SessionStore(str(path))
    try:
        detail = reopened.get(session["id"])
        assert detail["title"] == "Persistent"
        assert [m["role"] for m in reopened.messages(session["id"])] == ["user", "assistant"]
        assert reopened.history(session["id"]) == [("remember me", "remembered")]
    finally:
        reopened.close()


def test_static_paths_are_confined_to_the_static_directory():
    assert static_file("/static/style.css").name == "style.css"
    assert static_file("/static/../web.py") is None
    assert static_file("/static/%2e%2e/web.py") is None
    assert static_file("/static/missing.js") is None


# ---- HTTP surface ---------------------------------------------------------------------

def request(server, method, path, *, body=None, headers=None, cookie=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    headers = dict(headers or {})
    if cookie:
        headers["Cookie"] = cookie
    payload = None
    if body is not None:
        payload = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response, raw
    finally:
        connection.close()


def login(server):
    response, raw = request(server, "POST", "/api/login", body={"token": "test-token"})
    assert response.status == 200
    set_cookie = response.getheader("Set-Cookie")
    jar = SimpleCookie()
    jar.load(set_cookie)
    cookie = f"ashura_auth={jar['ashura_auth'].value}"
    payload = json.loads(raw)
    return cookie, payload["csrf"]


def test_http_index_has_security_headers_and_no_auth_required(server):
    response, raw = request(server, "GET", "/")
    assert response.status == 200
    assert b"<title>ASHURA</title>" in raw
    assert "default-src 'self'" in response.getheader("Content-Security-Policy")
    assert response.getheader("X-Frame-Options") == "DENY"
    assert response.getheader("X-Content-Type-Options") == "nosniff"
    assert response.getheader("Referrer-Policy") == "no-referrer"
    assert response.getheader("X-Request-ID")


def test_http_api_requires_auth_and_login_sets_cookie(server):
    response, raw = request(server, "GET", "/api/status")
    assert response.status == 401
    assert "authentication required" in raw.decode()

    response, _ = request(server, "POST", "/api/login", body={"token": "wrong"})
    assert response.status == 401

    cookie, csrf = login(server)
    response, raw = request(server, "GET", "/api/status", cookie=cookie)
    assert response.status == 200
    status = json.loads(raw)
    assert status["model"] == "echo-stub"
    assert csrf == status["csrf"]


def test_http_chat_requires_csrf_and_persists(server):
    cookie, csrf = login(server)
    response, raw = request(server, "POST", "/api/chat", body={"message": "http chat"},
                            cookie=cookie)
    assert response.status == 403
    assert "CSRF" in raw.decode()

    response, raw = request(server, "POST", "/api/chat", body={"message": "http chat"},
                            cookie=cookie, headers={"X-CSRF-Token": csrf})
    assert response.status == 200
    chat = json.loads(raw)
    assert "[echo] http chat" in chat["text"]
    assert chat["session_id"]

    response, raw = request(server, "GET", f"/api/sessions/{chat['session_id']}", cookie=cookie)
    assert response.status == 200
    detail = json.loads(raw)
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]


def test_http_streaming_chat_sends_sse_events(server):
    cookie, csrf = login(server)
    response, raw = request(server, "POST", "/api/chat/stream",
                            body={"message": "stream over http"}, cookie=cookie,
                            headers={"X-CSRF-Token": csrf})
    assert response.status == 200
    assert response.getheader("Content-Type").startswith("text/event-stream")
    text = raw.decode()
    assert "event: meta" in text
    assert "event: token" in text
    assert "event: done" in text
    events = {}
    for block in text.strip().split("\n\n"):
        lines = block.splitlines()
        name = next((line[7:] for line in lines if line.startswith("event: ")), None)
        data = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if name and data:
            events[name] = json.loads(data)
    assert "stream over http" in events["done"]["text"]
    assert events["done"]["session_id"] == events["meta"]["session_id"]


def test_http_origin_mismatch_is_rejected(server):
    cookie, csrf = login(server)
    response, raw = request(server, "POST", "/api/chat", body={"message": "blocked"},
                            cookie=cookie, headers={"X-CSRF-Token": csrf,
                                                    "Origin": "http://evil.example"})
    assert response.status == 403


def test_http_rejects_a_foreign_host_header(server):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    try:
        connection.putrequest("GET", "/api/health", skip_host=True)
        connection.putheader("Host", "evil.example")
        connection.endheaders()
        response = connection.getresponse()
        assert response.status == 421
        assert b"invalid Host" in response.read()
    finally:
        connection.close()


def test_http_session_delete_and_export(server):
    cookie, csrf = login(server)
    response, raw = request(server, "POST", "/api/sessions", body={"title": "HTTP session"},
                            cookie=cookie, headers={"X-CSRF-Token": csrf})
    assert response.status == 201
    session_id = json.loads(raw)["session"]["id"]

    response, raw = request(server, "GET", f"/api/sessions/{session_id}/export?format=md",
                            cookie=cookie)
    assert response.status == 200
    assert "attachment" in response.getheader("Content-Disposition")
    assert "HTTP session" in raw.decode()

    response, _ = request(server, "DELETE", f"/api/sessions/{session_id}", cookie=cookie,
                          headers={"X-CSRF-Token": csrf})
    assert response.status == 200
    response, _ = request(server, "GET", f"/api/sessions/{session_id}", cookie=cookie)
    assert response.status == 404


def test_http_token_bootstrap_sets_cookie_and_redirects(server):
    response, _ = request(server, "GET", "/?token=test-token")
    assert response.status == 303
    assert response.getheader("Location") == "/"
    set_cookie = response.getheader("Set-Cookie")
    assert "HttpOnly" in set_cookie
    assert "SameSite=Strict" in set_cookie
    jar = SimpleCookie()
    jar.load(set_cookie)
    cookie = f"ashura_auth={jar['ashura_auth'].value}"

    response, raw = request(server, "GET", "/api/status", cookie=cookie)
    assert response.status == 200
    assert json.loads(raw)["model"] == "echo-stub"


def test_http_logout_requires_csrf_and_clears_cookie(server):
    cookie, csrf = login(server)
    response, _ = request(server, "POST", "/api/logout", cookie=cookie)
    assert response.status == 403

    response, raw = request(server, "POST", "/api/logout", cookie=cookie,
                            headers={"X-CSRF-Token": csrf})
    assert response.status == 200
    assert json.loads(raw)["ok"] is True
    assert "Max-Age=0" in response.getheader("Set-Cookie")


def test_http_memory_endpoint_returns_admission(server):
    cookie, csrf = login(server)
    request(server, "POST", "/api/chat", body={"message": "remember this http fact"},
            cookie=cookie, headers={"X-CSRF-Token": csrf})
    response, raw = request(server, "GET", "/api/memory?q=remember&limit=5", cookie=cookie)
    assert response.status == 200
    payload = json.loads(raw)
    assert payload["query"] == "remember"
    assert any("remember this http fact" in item["input"] for item in payload["items"])


def test_http_ocr_accepts_an_upload(server):
    cookie, csrf = login(server)
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode()
    response, raw = request(server, "POST", "/api/ocr",
                            body={"filename": "tiny.png", "data": png},
                            cookie=cookie, headers={"X-CSRF-Token": csrf})
    assert response.status == 200
    payload = json.loads(raw)
    assert payload["kind"] == "ocr"
    response, raw = request(server, "GET", f"/api/sessions/{payload['session_id']}",
                            cookie=cookie)
    assert response.status == 200
    detail = json.loads(raw)
    assert detail["messages"][0]["content"] == "[image: tiny.png]"


def test_export_includes_the_whole_transcript_beyond_the_ui_page():
    store = SessionStore(":memory:")
    session = store.create("Long transcript")
    for index in range(205):
        role = "user" if index % 2 == 0 else "assistant"
        store.append(session["id"], role, f"message-{index:03d}")
    assert len(store.messages(session["id"])) == 200
    assert len(store.messages(session["id"], limit=None)) == 205

    app = WebApp(Controller(EchoModel(), ama=AMA(Database(":memory:"))),
                 "config/ashura.toml", sessions=store, token="t", csrf="c")
    try:
        body, content_type, _ = app.export_session(session["id"], "md")
        text = body.decode()
        assert "text/markdown" in content_type
        assert "message-000" in text
        assert "message-204" in text
    finally:
        app.close()
