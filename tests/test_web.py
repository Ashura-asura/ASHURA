import base64
import json

import pytest

from app.web import WebApp, static_file
from brain.controller import Controller
from foundation.language_model import EchoModel
from learning.ama import AMA
from memory.database import Database


@pytest.fixture
def web():
    db = Database(":memory:")
    controller = Controller(EchoModel(), ama=AMA(db))
    yield WebApp(controller, "config/ashura.toml")
    controller.close()


def test_status_reports_model_and_memory_counts(web):
    status = web.status()
    assert status["model"] == "echo-stub"
    assert status["counts"]["experiences"] == 0
    assert status["counts"]["fts_rows"] == 0


def test_chat_returns_text_and_trace_and_is_searchable(web):
    result = web.chat("hello local memory")
    assert "[echo]" in result["text"]
    assert result["trace"]["steps"]
    assert result["trace"]["total_ms"] >= 0

    found = web.memory("hello", limit=5)
    assert any("hello local memory" in item["input"] for item in found["items"])


def test_empty_chat_is_rejected(web):
    with pytest.raises(ValueError, match="empty"):
        web.chat("   ")


def test_ocr_rejects_invalid_base64(web):
    with pytest.raises(ValueError, match="base64"):
        web.ocr("scan.png", "not-base64")


def test_ocr_accepts_a_tiny_png(web):
    png = base64.b64encode(
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    ).decode()
    result = web.ocr("tiny.png", png)
    assert "trace" in result  # OCR may be unavailable; the request path must not crash


def test_static_paths_are_confined_to_the_static_directory():
    assert static_file("/static/style.css").name == "style.css"
    assert static_file("/static/../web.py") is None
    assert static_file("/static/missing.js") is None
