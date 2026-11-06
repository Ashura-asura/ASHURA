"""Local web interface for ASHURA.

A stdlib-only, loopback-only operator console over the same ``Controller`` as the CLI. It adds
the things a usable local interface needs without turning ASHURA into a multi-user service:

* a single-writer :class:`~app.worker.ControllerWorker` (the Controller and its SQLite connection
  are never touched by two HTTP threads);
* token authentication with an HttpOnly, SameSite=Strict cookie, CSRF checks and a strict
  Content-Security-Policy;
* SSE streaming with cooperative cancellation, bounded queues, request IDs, rate limits and
  structured JSON access logs;
* persistent chat sessions in a separate SQLite database, trace metadata and Markdown export.

Run it with::

    python -m app.web --config config/ashura.ollama.toml --open
    ashura-web --config config/ashura.ollama.toml

The server binds to a loopback address only. It is still a local tool, not an internet-facing
service; put a real authenticating reverse proxy in front of it if that requirement ever changes.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import ipaddress
import json
import logging
import mimetypes
import os
import queue
import re
import secrets
import socket
import sys
import tempfile
import threading
import time
import tomllib
import webbrowser
from collections import deque
from dataclasses import replace
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from app.main import build, resolve_config
from app.sessions import SessionStore
from app.token_store import TokenStoreError, load_or_create_token
from app.worker import ControllerWorker, Job, WorkerQueueFull
from brain.need_field import Task
from foundation.language_model import GenerationCancelled
from foundation.model_config import load_config
from foundation.ollama_model import OllamaError, OllamaModel, list_models, unload
from skills.perception import SUPPORTED_SUFFIXES, document_info, is_supported
from skills.web import WebError

VERSION = "0.2"
STATIC = Path(__file__).with_name("static")
COOKIE = "ashura_auth"
COOKIE_MAX_AGE = 7 * 24 * 60 * 60

MAX_JSON = 1024 * 1024
MAX_OCR_BODY = 24 * 1024 * 1024
MAX_UPLOAD = 16 * 1024 * 1024
BODY_DRAIN_TIMEOUT = 1.0
MAX_MESSAGE = 16_000
JOB_TIMEOUT = 300.0
STREAM_DEADLINE = 600.0

SESSION_RE = re.compile(r"^[0-9a-f]{32}$")
logger = logging.getLogger("ashura.web")

SECURITY_HEADERS = (
    ("Content-Security-Policy",
     "default-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; "
     "form-action 'self'; img-src 'self' data: blob:; connect-src 'self'; "
     "script-src 'self'; style-src 'self'; font-src 'self'"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "no-referrer"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
    ("Cross-Origin-Resource-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"),
)


class HTTPError(Exception):
    """An error that should become a JSON response, not a traceback."""

    def __init__(self, message: str, status: int = 400, headers: list[tuple[str, str]] | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.headers = headers or []


class ModelNotInstalled(ValueError):
    """The requested Ollama tag is not present in the local model list."""


class ModelSwitchUnavailable(RuntimeError):
    """Model switching is unavailable or could not be completed."""


class RateLimiter:
    """Small in-process sliding-window limiter, keyed by client and bucket."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float = 60.0) -> bool:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits.setdefault(key, deque())
            while bucket and now - bucket[0] >= window:
                bucket.popleft()
            if len(bucket) >= limit:
                return False
            bucket.append(now)
            if len(self._hits) > 2048:
                for name in [name for name, values in self._hits.items() if not values]:
                    self._hits.pop(name, None)
            return True


def serialize_response(response, model: str | None = None) -> dict:
    """Convert a Controller Response into JSON-safe data for the UI and session store."""
    trace = response.trace
    verification = getattr(response.verification, "value", response.verification)
    return {
        "text": response.text,
        "verified": response.verified,
        "verification": verification,
        "admission": response.admission,
        "attribution": response.attribution,
        "correction": response.correction,
        "sources": getattr(response, "sources", None) or [],
        "truncated": bool(getattr(response, "truncated", False)),
        "tool_calls": getattr(response, "tool_calls", None) or [],
        "document": getattr(response, "document", None),
        "web": getattr(response, "web", None),
        "model": model,
        "trace": {
            "routing": trace.routing,
            "routing_ms": round(trace.routing_ms, 3),
            "total_ms": round(trace.total_ms, 3),
            "steps": [{
                "module": step.module,
                "input": str(step.input)[:300],
                "output": str(step.output)[:800],
                "ms": round(step.ms, 3),
                "ok": step.ok,
                "note": step.note,
                "verification": step.verification,
            } for step in trace.steps],
        },
    }


def static_file(path: str) -> Path | None:
    """Resolve /static/<name> without allowing traversal outside app/static."""
    if not path.startswith("/static/") or "\x00" in path:
        return None
    root = STATIC.resolve()
    try:
        candidate = (root / unquote(path[len("/static/"):])).resolve()
    except (OSError, ValueError):
        return None
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _read_counts(controller) -> dict:
    """Read aggregate counts. Call only from the ControllerWorker thread."""
    def count(sql: str) -> int | None:
        try:
            return int(controller.ama.db.conn.execute(sql).fetchone()[0])
        except Exception:  # noqa: BLE001 - status must never take down the UI
            return None

    return {
        "experiences": count("SELECT COUNT(*) FROM experiences"),
        "facts": count("SELECT COUNT(*) FROM facts"),
        "conflicts_open": count("SELECT COUNT(*) FROM conflicts WHERE status = 'open'"),
        "fts_rows": count("SELECT COUNT(*) FROM fts_index"),
    }


def _message_meta(payload: dict) -> dict:
    return {
        "kind": "chat",
        "model": payload.get("model"),
        "verified": payload.get("verified"),
        "verification": payload.get("verification"),
        "admission": payload.get("admission"),
        "attribution": payload.get("attribution"),
        "correction": payload.get("correction"),
        "trace": payload.get("trace"),
        "total_ms": (payload.get("trace") or {}).get("total_ms"),
        "sources": payload.get("sources") or [],
        "truncated": bool(payload.get("truncated", False)),
        "tool_calls": payload.get("tool_calls") or [],
        "document": payload.get("document"),
        "web": payload.get("web"),
    }


class WebApp:
    """State shared by the HTTP handler: auth, sessions, worker and cached status."""

    def __init__(self, controller, config_path: str, *, sessions: SessionStore | None = None,
                 worker: ControllerWorker | None = None, token: str | None = None,
                 csrf: str | None = None, session_db: str | None = None,
                 max_queue: int = 8, started: float | None = None):
        self.controller = controller
        self.config_path = str(config_path)
        self.sessions = sessions if sessions is not None else SessionStore(
            session_db or "data/ui_sessions.db")
        self.worker = worker if worker is not None else ControllerWorker(controller, max_queue=max_queue)
        self.token = token or secrets.token_urlsafe(32)
        self.csrf = csrf or secrets.token_urlsafe(24)
        self.started = started or time.time()
        self.rate = RateLimiter()
        self._counts: dict | None = None
        self._counts_lock = threading.Lock()
        self._closed = False
        # Warm the cached counts from the worker thread. Status polling then never queues behind a
        # long model call; the cache is refreshed after every chat/OCR job.
        try:
            self.refresh_counts()
        except Exception:  # noqa: BLE001 - an empty/unavailable database must not stop the server
            pass

    # ---- auth ------------------------------------------------------------------------------
    def authenticated(self, token: str | None) -> bool:
        return bool(token) and secrets.compare_digest(token, self.token)

    # ---- status ----------------------------------------------------------------------------
    def refresh_counts(self, timeout: float = 15.0) -> dict | None:
        job = self.worker.submit(lambda emit: self._collect_counts(), kind="status")
        return job.wait(timeout)

    def _collect_counts(self) -> dict | None:
        counts = _read_counts(self.controller)
        with self._counts_lock:
            self._counts = counts
        return counts

    def _collect_counts_safe(self) -> None:
        try:
            self._collect_counts()
        except Exception:  # noqa: BLE001 - a stale counter is not a reason to lose an answer
            pass

    def _web_summary(self) -> dict:
        web, store = self._web_state()
        if web is None:
            return {"enabled": False, "provider": None, "stats": None}
        stats = None
        if store is not None:
            try:
                stats = store.stats()
            except Exception as error:  # noqa: BLE001 - a stale counter must not break status
                stats = {"error": f"{type(error).__name__}: {error}"}
        return {"enabled": True, "provider": web.config.provider, "stats": stats,
                "dataset_dir": web.config.dataset_dir}

    def status(self) -> dict:
        with self._counts_lock:
            counts = dict(self._counts) if self._counts is not None else None
        try:
            session_count = self.sessions.count()
        except Exception:  # noqa: BLE001
            session_count = None
        web = self._web_summary()
        tools_enabled = bool(getattr(self.controller, "tools", None) is not None
                             and callable(getattr(self.controller.model, "chat", None)))
        return {
            "version": VERSION,
            "model": getattr(self.controller.model, "name", type(self.controller.model).__name__),
            "config": self.config_path,
            "database": getattr(getattr(self.controller.ama, "db", None), "path", None),
            "sessions_db": self.sessions.path,
            "uptime_s": round(time.time() - self.started, 1),
            "counts": counts,
            "sessions": session_count,
            "worker": self.worker.stats(),
            "csrf": self.csrf,
            "web": web,
            "capabilities": {
                "streaming": True,
                "sessions": True,
                "ocr": True,
                "documents": True,
                "memory": True,
                "export": True,
                "tools": tools_enabled,
                "web": bool(web["enabled"]),
                "model_switch": isinstance(self.controller.model, OllamaModel),
            },
        }

    # ---- local model runtime ---------------------------------------------------------------
    def _model_catalog(self) -> dict[str, dict]:
        """Read the optional, informational model roles shipped beside the config."""
        path = Path(self.config_path).with_name("models.toml")
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return {}
        entries = data.get("model")
        if not isinstance(entries, list):
            return {}
        return {
            str(entry["tag"]): entry
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("tag"), str) and entry["tag"]
        }

    def _ollama_model(self) -> OllamaModel | None:
        model = self.controller.model
        return model if isinstance(model, OllamaModel) else None

    def models(self) -> dict:
        """List installed Ollama models. This never downloads or invents a model."""
        active_model = getattr(self.controller.model, "name", type(self.controller.model).__name__)
        model = self._ollama_model()
        if model is None:
            return {
                "available": False,
                "runtime": type(self.controller.model).__name__,
                "active": active_model,
                "reason": ("Model switching requires the Ollama backend. This process was started "
                           "with a different model backend."),
                "models": [],
            }
        try:
            installed = list_models(model.cfg.host)
        except OllamaError as error:
            return {
                "available": False,
                "runtime": "ollama",
                "host": model.cfg.host,
                "active": model.cfg.model,
                "reason": str(error),
                "models": [],
            }
        catalog = self._model_catalog()
        items = []
        for entry in installed:
            name = entry.get("name")
            if not isinstance(name, str) or not name:
                continue
            documented = catalog.get(name, {})
            documented_id = str(documented.get("id") or "")
            digest = str(entry.get("digest") or "")
            items.append({
                "name": name,
                "digest": digest,
                "size": entry.get("size", 0),
                "active": name == model.cfg.model,
                "role": str(documented.get("role") or "No documented role in this build."),
                "note": str(documented.get("note") or ""),
                "documented": bool(documented),
                "matches_catalog": (digest.startswith(documented_id)
                                    if documented and documented_id else None),
            })
        items.sort(key=lambda item: (not item["active"], item["name"]))
        return {
            "available": True,
            "runtime": "ollama",
            "host": model.cfg.host,
            "active": model.cfg.model,
            "digest": model.digest,
            "models": items,
            "notes": [
                "The list is read from the configured Ollama endpoint; nothing is downloaded here.",
                "Switching affects this process only. The launch configuration is not rewritten.",
                "A response already streaming finishes on the model that started it.",
            ],
        }

    def _switch_model(self, name: str) -> dict:
        """Worker-thread operation: validate, unload the previous tag, then swap the model."""
        current = self._ollama_model()
        if current is None:
            raise ModelSwitchUnavailable("Model switching requires the Ollama backend.")
        installed = {item["name"]: item for item in list_models(current.cfg.host)
                     if isinstance(item.get("name"), str)}
        entry = installed.get(name)
        if entry is None:
            raise ModelNotInstalled(
                f"Model {name!r} is not installed. Only tags returned by the local Ollama "
                "endpoint can be selected."
            )
        digest = str(entry.get("digest") or "")
        if not digest:
            raise ModelSwitchUnavailable(f"Ollama did not report a digest for {name!r}; refusing to switch.")
        new_config = replace(current.cfg, model=name, digest=digest)
        new_model = OllamaModel(new_config)
        warning = None
        previous_unloaded = False
        try:
            unload(current.cfg.host, current.cfg.model)
            previous_unloaded = True
        except OllamaError as error:
            warning = f"The previous model was not unloaded: {error}"
        self.controller.model = new_model
        return {
            "ok": True,
            "changed": True,
            "active": name,
            "model": new_model.name,
            "previous": current.cfg.model,
            "previous_unloaded": previous_unloaded,
            "warning": warning,
            "message": "Model switched for subsequent turns. The launch configuration is unchanged.",
        }

    def select_model(self, name: str) -> dict:
        if not isinstance(name, str):
            raise ValueError("model must be a string")
        name = name.strip()
        if not name or len(name) > 200:
            raise ValueError("model must be a non-empty tag of at most 200 characters")
        current = self._ollama_model()
        if current is None:
            raise ModelSwitchUnavailable("Model switching requires the Ollama backend.")
        if name == current.cfg.model:
            return {
                "ok": True,
                "changed": False,
                "active": name,
                "message": "That model is already active.",
            }
        job = self.worker.submit(lambda emit: self._switch_model(name), kind="model")
        try:
            return job.wait(timeout=120)
        except TimeoutError:
            raise ModelSwitchUnavailable(
                "The model switch did not finish within 120 s. It may still be queued behind a "
                "running turn; check the model list before retrying."
            ) from None

    # ---- sessions --------------------------------------------------------------------------
    def _resolve_session(self, session_id: str | None) -> tuple[dict, bool]:
        if session_id:
            if not SESSION_RE.fullmatch(session_id):
                raise ValueError("invalid session id")
            session = self.sessions.get(session_id)
            if session is None:
                raise KeyError(f"session {session_id} not found")
            return session, False
        return self.sessions.create(), True

    def list_sessions(self, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        return self.sessions.list(limit)

    def get_session(self, session_id: str, limit: int = 200,
                    before: int | None = None) -> dict:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid session id")
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"session {session_id} not found")
        messages = self.sessions.messages(session_id, limit=limit, before=before)
        try:
            total = self.sessions.count_messages(session_id)
        except Exception:  # noqa: BLE001 - a count failure must not hide the transcript
            total = None
        has_more = bool(messages) and self.sessions.has_older(session_id, messages[0]["id"])
        return {"session": session, "messages": messages,
                "has_more": has_more, "total": total}

    def create_session(self, title: str = "New chat") -> dict:
        return self.sessions.create(title)

    def rename_session(self, session_id: str, title: str) -> dict:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid session id")
        session = self.sessions.rename(session_id, title)
        if session is None:
            raise KeyError(f"session {session_id} not found")
        return session

    def delete_session(self, session_id: str) -> bool:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid session id")
        if not self.sessions.delete(session_id):
            raise KeyError(f"session {session_id} not found")
        return True

    def export_session(self, session_id: str, fmt: str = "md") -> tuple[bytes, str, str]:
        if not SESSION_RE.fullmatch(session_id):
            raise ValueError("invalid session id")
        session = self.sessions.get(session_id)
        if session is None:
            raise KeyError(f"session {session_id} not found")
        messages = self.sessions.messages(session_id, limit=None)
        payload = {"session": session, "messages": messages}
        if fmt == "json":
            body = json.dumps(payload, indent=2, default=str, ensure_ascii=False).encode("utf-8")
            return body, "application/json; charset=utf-8", f"ashura-{session_id[:8]}.json"
        if fmt != "md":
            raise ValueError("format must be md or json")
        lines = [f"# {session.get('title') or 'ASHURA chat'}", ""]
        for message in messages:
            role = "You" if message.get("role") == "user" else "ASHURA"
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(message.get("ts") or time.time()))
            lines.append(f"## {role} · {stamp}")
            lines.append("")
            lines.append(message.get("content") or "")
            meta = message.get("meta") or {}
            badges = []
            if meta.get("verified") is True:
                badges.append("verified")
            elif meta.get("verified") is False:
                badges.append("unverified")
            if meta.get("admission"):
                badges.append(str(meta["admission"]))
            if meta.get("model"):
                badges.append(str(meta["model"]))
            if badges:
                lines.append("")
                lines.append("`" + " · ".join(badges) + "`")
            lines.append("")
        body = ("\n".join(lines) + "\n").encode("utf-8")
        return body, "text/markdown; charset=utf-8", f"ashura-{session_id[:8]}.md"

    # ---- chat / OCR ------------------------------------------------------------------------
    def start_chat(self, message: str, session_id: str | None = None, *, stream: bool = False,
                   cancel_event: threading.Event | None = None,
                   force: tuple[str, ...] = ()) -> tuple[dict, Job]:
        if not isinstance(message, str):
            raise ValueError("message must be a string")
        message = message.strip()
        if not message:
            raise ValueError("message must not be empty")
        if len(message) > MAX_MESSAGE:
            raise ValueError(f"message is too long (max {MAX_MESSAGE} characters)")
        session, created = self._resolve_session(session_id)
        sid = session["id"]

        def work(emit):
            try:
                # Read history and append inside the worker, so concurrent submissions to one
                # session are ordered exactly as the single queue executes them.
                history = self.sessions.history(sid)
                user_message = self.sessions.append(sid, "user", message)
                task = Task(message, history=tuple(history), session_id=sid, force=force)
                response = self.controller.handle(task, on_token=emit if stream else None)
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelled()
                payload = serialize_response(response, self.controller.model.name)
                payload["session_id"] = sid
                payload["user_message_id"] = user_message["id"]
                assistant = self.sessions.append(
                    sid, "assistant", payload["text"], meta=_message_meta(payload))
                payload["assistant_message_id"] = assistant["id"]
                return payload
            finally:
                self._collect_counts_safe()

        try:
            job = self.worker.submit(work, kind="chat", cancel_event=cancel_event)
        except Exception:
            if created:
                self.sessions.delete(sid)
            raise
        return session, job

    def start_ocr(self, filename: str, encoded: str, session_id: str | None = None,
                  prompt: str | None = None) -> tuple[dict, Job]:
        if prompt is not None and not isinstance(prompt, str):
            raise ValueError("prompt must be a string")
        prompt = (prompt or "").strip()
        if len(prompt) > MAX_MESSAGE:
            raise ValueError(f"prompt is too long (max {MAX_MESSAGE} characters)")
        if not isinstance(encoded, str):
            raise ValueError("file data must be a base64 string")
        if encoded.startswith("data:") and "," in encoded:
            encoded = encoded.split(",", 1)[1]
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("invalid base64 file data") from error
        if not raw:
            raise ValueError("file is empty")
        if len(raw) > MAX_UPLOAD:
            raise ValueError(f"file is too large (max {MAX_UPLOAD // (1024 * 1024)} MB)")
        name = (filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:120] or "upload"
        info = document_info(name)
        if info.kind == "unsupported":
            supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
            raise ValueError(f"unsupported file type {info.suffix or '(none)'}; supported: {supported}")
        session, created = self._resolve_session(session_id)
        sid = session["id"]
        suffix = info.suffix or ".bin"
        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            if created:
                self.sessions.delete(sid)
            raise

        def work(emit):
            try:
                is_image = info.kind == "image"
                instruction = prompt or ("Read the text in this image." if is_image
                                          else "Read this document and summarize its key content.")
                user_message = self.sessions.append(
                    sid, "user", instruction,
                    meta={"kind": "ocr" if is_image else "document", "filename": name})
                if is_image:
                    task = Task(instruction, has_image=True, image_path=path,
                                document_name=name, session_id=sid, force=("ocr",))
                else:
                    task = Task(instruction,
                                has_document=True, document_path=path, document_name=name,
                                session_id=sid, force=("documents",))
                response = self.controller.handle(task)
                payload = serialize_response(response, self.controller.model.name)
                payload["session_id"] = sid
                payload["user_message_id"] = user_message["id"]
                payload["kind"] = "ocr" if is_image else "document"
                payload["filename"] = name
                assistant = self.sessions.append(
                    sid, "assistant", payload["text"],
                    meta={**_message_meta(payload), "kind": payload["kind"]})
                payload["assistant_message_id"] = assistant["id"]
                return payload
            finally:
                try:
                    os.unlink(path)
                except OSError:
                    pass
                self._collect_counts_safe()

        try:
            job = self.worker.submit(work, kind="ocr")
        except Exception:
            try:
                os.unlink(path)
            except OSError:
                pass
            if created:
                self.sessions.delete(sid)
            raise
        return session, job

    # ---- memory ----------------------------------------------------------------------------
    def chat(self, message: str, session_id: str | None = None) -> dict:
        """Synchronous convenience wrapper used by tests and small scripts."""
        _, job = self.start_chat(message, session_id, stream=False)
        return job.wait(JOB_TIMEOUT)

    def ocr(self, filename: str, encoded: str, session_id: str | None = None,
            prompt: str | None = None) -> dict:
        """Synchronous OCR wrapper. The HTTP API streams chat, not OCR."""
        _, job = self.start_ocr(filename, encoded, session_id, prompt)
        return job.wait(JOB_TIMEOUT)

    def memory(self, query: str = "", limit: int = 20) -> dict:
        limit = max(1, min(int(limit), 50))
        query = (query or "").strip()[:500]
        job = self.worker.submit(lambda emit: self._memory(query, limit), kind="memory")
        return job.wait(60)

    def _memory(self, query: str, limit: int) -> dict:
        ama = self.controller.ama
        if ama is None:
            return {"query": query, "items": []}
        if query:
            items = ama.retrieve(query, limit=limit, min_reliability=0.0,
                                 include_unverified=True)
            rows = [{
                "id": item.experience.id,
                "input": item.experience.input,
                "output": item.experience.output,
                "category": item.experience.task_category,
                "status": item.experience.verification_status,
                "method": item.experience.verification_method,
                "reliability": item.experience.reliability,
                "label": item.label,
                "conflict": item.conflict,
                "ts": item.experience.ts,
            } for item in items]
        else:
            rows = [dict(row) for row in ama.db.conn.execute(
                """SELECT id, input, output, task_category AS category,
                          verification_status AS status, verification_method AS method,
                          reliability, ts, related_ids
                   FROM experiences ORDER BY ts DESC LIMIT ?""", (limit,))]
            for row in rows:
                try:
                    related = json.loads(row.pop("related_ids") or "[]")
                except (TypeError, json.JSONDecodeError):
                    related = []
                row["conflict"] = bool(related)
                row["label"] = row["status"]
        self._collect_counts_safe()
        return {"query": query, "items": rows}

    # ---- web research and candidate facts ----------------------------------------------------
    def _web_state(self) -> tuple[object | None, object | None]:
        web = getattr(self.controller, "web", None)
        store = getattr(self.controller, "fact_store", None)
        if web is None or not getattr(web, "enabled", False):
            return None, None
        return web, store

    def web_status(self) -> dict:
        """Capabilities and counters for the web research panel."""
        web, store = self._web_state()
        if web is None:
            return {"enabled": False, "provider": None,
                    "reason": "Web research is disabled in this configuration.",
                    "stats": None, "facts": [], "gaps": []}
        config = web.config
        stats = None
        if store is not None:
            try:
                stats = store.stats()
            except Exception as error:  # noqa: BLE001 - status must survive a locked database
                stats = {"error": f"{type(error).__name__}: {error}"}
        return {
            "enabled": True,
            "provider": config.provider,
            "host": getattr(config, "searx_url", "") or None,
            "auto_on_uncertainty": bool(config.auto_on_uncertainty),
            "max_results": config.max_results,
            "max_fetch_pages": config.max_fetch_pages,
            "dataset_dir": config.dataset_dir,
            "stats": stats,
            "facts": store.list_facts(limit=25) if store is not None else [],
            "gaps": store.list_gaps(limit=25, unresolved_only=True) if store is not None else [],
            "notes": [
                "Web text is external and untrusted. Answers are observations, not verified facts.",
                "Candidate facts are exported with training_ready=false until a human reviews them.",
                "Search runs on the server only; the browser keeps connect-src 'self'.",
            ],
        }

    def web_facts(self, limit: int = 50, status: str | None = None) -> dict:
        """Recent candidate facts and unresolved gaps, with honest review status."""
        web, store = self._web_state()
        if web is None or store is None:
            return {"enabled": False, "facts": [], "gaps": [], "stats": None}
        if status is not None and status not in {"candidate", "verified", "rejected"}:
            raise ValueError("status must be candidate, verified or rejected")
        return {
            "enabled": True,
            "provider": web.config.provider,
            "dataset_dir": web.config.dataset_dir,
            "stats": store.stats(),
            "facts": store.list_facts(limit=limit, status=status),
            "gaps": store.list_gaps(limit=limit, unresolved_only=True),
            "training_ready": False,
            "warning": ("These rows are web-sourced observations, not verified training labels. "
                        "Review is required before any training run."),
            "notes": [
                "Web text is external and untrusted.",
                "Review status is an operator decision, not independent fact verification.",
                "The JSONL export always marks rows training_ready=false.",
            ],
        }

    def review_web_fact(self, fact_id, status: str, note: str = "") -> dict:
        _, store = self._web_state()
        if store is None:
            raise ModelSwitchUnavailable("Web fact storage is not enabled in this configuration.")
        if not isinstance(fact_id, int) or isinstance(fact_id, bool) or fact_id < 1:
            raise ValueError("id must be a positive integer")
        if status not in {"candidate", "verified", "rejected"}:
            raise ValueError("status must be candidate, verified or rejected")
        if not isinstance(note, str):
            raise ValueError("note must be a string")
        try:
            store.set_status(fact_id, status, note)
        except KeyError as error:
            raise KeyError(str(error)) from None
        return {"ok": True, "id": fact_id, "status": status,
                "note": "Review status recorded. This does not by itself make the fact verified."}

    def export_web_facts(self, include_rejected: bool = False) -> tuple[bytes, str, str]:
        web, store = self._web_state()
        if store is None:
            raise ModelSwitchUnavailable("Web fact storage is not enabled in this configuration.")
        result = store.export_dataset(getattr(web.config, "dataset_dir", None),
                                      include_rejected=include_rejected)
        path = Path(result["path"])
        try:
            body = path.read_bytes()
        except OSError as error:
            raise ValueError(f"dataset export was written but could not be read: {error}") from error
        filename = f"ashura-web-candidates-{result['stamp']}.jsonl"
        return body, "application/x-ndjson; charset=utf-8", filename

    # ---- shutdown --------------------------------------------------------------------------
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if not self.worker.close(timeout=10):
            logger.warning(json.dumps({"event": "worker_stop_timeout"}))
        learning = getattr(self.controller, "learning_worker", None)
        if learning is not None:
            try:
                learning.close(timeout=5)
            except Exception:  # noqa: BLE001
                pass
        try:
            self.sessions.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self.controller.close()
        except Exception:  # noqa: BLE001
            pass


class Handler(BaseHTTPRequestHandler):
    server_version = f"ASHURA/{VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ---- request lifecycle ----------------------------------------------------------------
    def version_string(self) -> str:
        return self.server_version

    def handle_one_request(self) -> None:
        self.request_id = secrets.token_hex(8)
        self._responded = False
        self._body_consumed = False
        self._status_code = 0
        self._started = time.monotonic()
        try:
            super().handle_one_request()
        finally:
            self._log_access()

    def log_message(self, fmt, *args):  # noqa: D401 - keep BaseHTTPRequestHandler quiet
        return

    def _log_access(self) -> None:
        if not getattr(self, "command", None):
            return
        path = urlparse(self.path).path[:200]
        payload = {
            "event": "http",
            "request_id": self.request_id,
            "method": self.command,
            "path": path,
            "status": self._status_code or 0,
            "duration_ms": round((time.monotonic() - self._started) * 1000, 1),
            "client": self.client_address[0] if self.client_address else None,
        }
        if path.startswith("/api/") or (self._status_code or 0) >= 400:
            logger.info(json.dumps(payload))
        else:
            logger.debug(json.dumps(payload))

    def send_response(self, code, message=None):
        self._status_code = int(code)
        super().send_response(code, message)

    def end_headers(self) -> None:
        self.send_header("X-Request-ID", getattr(self, "request_id", ""))
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    # ---- host / auth / CSRF ---------------------------------------------------------------
    def _allowed_hosts(self) -> set[str]:
        port = self.server.server_port
        names = {"127.0.0.1", "localhost", "[::1]"}
        hosts = {f"{name}:{port}" for name in names}
        if port in (80, 443):
            hosts |= names
        return hosts

    def _check_host(self) -> None:
        host = (self.headers.get("Host") or "").strip().lower()
        if not host:
            raise HTTPError("missing Host header", 400)
        if host not in self._allowed_hosts():
            raise HTTPError("invalid Host header", 421)

    def _cookie_token(self) -> str | None:
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        jar = SimpleCookie()
        try:
            jar.load(raw)
        except CookieError:
            return None
        morsel = jar.get(COOKIE)
        return morsel.value if morsel is not None else None

    def _provided_token(self) -> str | None:
        header = self.headers.get("X-ASHURA-Token")
        if header:
            return header
        auth = self.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return self._cookie_token()

    def _authenticated(self) -> bool:
        return self.server.app.authenticated(self._provided_token())

    def _api_guard(self) -> None:
        client = self.client_address[0] if self.client_address else "?"
        if not self.server.app.rate.allow(f"{client}|api", 600):
            raise HTTPError("rate limit exceeded", 429, [("Retry-After", "60")])
        if not self._authenticated():
            raise HTTPError("authentication required", 401,
                            [("WWW-Authenticate", 'Bearer realm="ASHURA"')])

    def _csrf_guard(self) -> None:
        # A custom token header proves that a non-browser client is deliberately calling the API.
        if self.headers.get("X-ASHURA-Token") or self.headers.get("Authorization"):
            return
        origin = self.headers.get("Origin")
        if origin is not None and origin not in {f"http://{h}" for h in self._allowed_hosts()}:
            raise HTTPError("origin not allowed", 403)
        token = self.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, self.server.app.csrf):
            raise HTTPError("invalid CSRF token", 403)

    def _rate(self, bucket: str, limit: int) -> None:
        client = self.client_address[0] if self.client_address else "?"
        if not self.server.app.rate.allow(f"{client}|{bucket}", limit):
            raise HTTPError("rate limit exceeded", 429, [("Retry-After", "60")])

    def _prepare(self) -> bool:
        try:
            self._check_host()
        except HTTPError as error:
            self._error(error.message, error.status, error.headers)
            return False
        return True

    # ---- responses ------------------------------------------------------------------------
    def _json(self, payload: dict, status: int = 200,
              headers: list[tuple[str, str]] | None = None) -> None:
        if self._responded:
            self.close_connection = True
            return
        self._responded = True
        body = json.dumps(payload, default=str).encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in headers or []:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    def _error(self, message: str, status: int = 400,
               headers: list[tuple[str, str]] | None = None) -> None:
        if self._responded:
            self.close_connection = True
            logger.warning(json.dumps({"event": "late_error", "request_id": self.request_id,
                                       "error": message[:200]}))
            return
        # An error may be raised before the request body is read. Drain it first:
        # closing a socket with unread bytes can make Windows send RST, so the
        # client would see a connection abort instead of this 4xx response.
        self._drain_unread_body()
        self.close_connection = True
        self._json({"error": message, "request_id": getattr(self, "request_id", "")},
                   status, headers)

    def _file(self, path: Path, *, cache: bool = True) -> None:
        if self._responded:
            return
        try:
            stat = path.stat()
            body = path.read_bytes()
        except OSError:
            raise HTTPError("static file not found", 404) from None
        etag = f'"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if cache and self.headers.get("If-None-Match") == etag:
            self._responded = True
            self.send_response(304)
            self.send_header("ETag", etag)
            self.end_headers()
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {
                "application/javascript", "application/json", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if cache else "no-store")
        if cache:
            self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

    def _download(self, body: bytes, content_type: str, filename: str) -> None:
        if self._responded:
            return
        self._responded = True
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

    # ---- request body ---------------------------------------------------------------------
    def _drain_unread_body(self) -> None:
        """Consume a JSON body that an early error did not need."""
        if getattr(self, "_body_consumed", True):
            return
        if self.headers.get("Transfer-Encoding"):
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return
        if not 0 < length <= MAX_JSON:
            return
        remaining = length
        previous_timeout = self.connection.gettimeout()
        try:
            # Never let an early rejection pin a request thread forever when a
            # client advertises a body and then stops sending it.
            self.connection.settimeout(
                BODY_DRAIN_TIMEOUT if previous_timeout is None
                else min(previous_timeout, BODY_DRAIN_TIMEOUT)
            )
            while remaining:
                chunk = self.rfile.read(min(remaining, 64 * 1024))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            pass
        finally:
            try:
                self.connection.settimeout(previous_timeout)
            except OSError:
                pass
        self._body_consumed = remaining == 0

    def _body(self, limit: int = MAX_JSON) -> dict:
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type not in {"application/json", "application/x-json"} and not content_type.endswith("+json"):
            raise HTTPError("Content-Type must be application/json", 415)
        if self.headers.get("Transfer-Encoding"):
            raise HTTPError("chunked request bodies are not supported", 400)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise HTTPError("invalid Content-Length", 400) from None
        if length <= 0:
            raise HTTPError("request body is required", 400)
        if length > limit:
            raise HTTPError("request body is too large", 413)
        self._body_consumed = True
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise HTTPError("incomplete request body", 400)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise HTTPError(f"invalid JSON: {error.msg}", 400) from None
        if not isinstance(payload, dict):
            raise HTTPError("JSON body must be an object", 400)
        return payload

    def _discard_body(self, limit: int = MAX_JSON) -> None:
        """Consume a body that the route does not need, so keep-alive stays framed."""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise HTTPError("invalid Content-Length", 400) from None
        if length <= 0:
            return
        if length > limit:
            raise HTTPError("request body is too large", 413)
        self._body_consumed = True
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise HTTPError("incomplete request body", 400)

    # ---- dispatch -------------------------------------------------------------------------
    def do_GET(self):
        self._run(self._get)

    def do_POST(self):
        self._run(self._post)

    def do_PATCH(self):
        self._run(self._patch)

    def do_DELETE(self):
        self._run(self._delete)

    def do_OPTIONS(self):
        if not self._prepare():
            return
        self._responded = True
        self.send_response(204)
        self.send_header("Allow", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _run(self, target) -> None:
        if not self._prepare():
            return
        try:
            target()
        except HTTPError as error:
            self._error(error.message, error.status, error.headers)
        except WorkerQueueFull as error:
            self._error(str(error), 429, [("Retry-After", "5")])
        except TimeoutError:
            self._error("request timed out", 504)
        except KeyError as error:
            message = str(error.args[0]) if error.args else str(error)
            self._error(message, 404)
        except ValueError as error:
            self._error(str(error), 400)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as error:  # noqa: BLE001 - one request must not kill the server
            logger.exception(json.dumps({"event": "request_error", "request_id": self.request_id,
                                         "path": urlparse(self.path).path,
                                         "error": f"{type(error).__name__}: {error}"}))
            self._error("internal server error", 500)

    # ---- GET ------------------------------------------------------------------------------
    def _get(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/", "/index.html"}:
            return self._index(parsed)
        if path.startswith("/static/"):
            target = static_file(parsed.path)
            if target is None:
                raise HTTPError("static file not found", 404)
            return self._file(target)
        if path == "/favicon.ico":
            self._responded = True
            self.send_response(302)
            self.send_header("Location", "/static/favicon.svg")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/api/health":
            self._rate("health", 600)
            return self._json({"ok": True, "version": VERSION})
        if not path.startswith("/api/"):
            raise HTTPError("not found", 404)

        self._api_guard()
        if path == "/api/status":
            return self._json(self.server.app.status())
        if path == "/api/models":
            return self._json(self.server.app.models())
        if path == "/api/sessions":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["50"])[0])
            except (TypeError, ValueError):
                raise HTTPError("limit must be an integer", 400) from None
            return self._json({"sessions": self.server.app.list_sessions(limit)})
        if path == "/api/memory":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["20"])[0])
            except (TypeError, ValueError):
                raise HTTPError("limit must be an integer", 400) from None
            return self._json(self.server.app.memory(query.get("q", [""])[0], limit))
        if path == "/api/web/facts":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["50"])[0])
            except (TypeError, ValueError):
                raise HTTPError("limit must be an integer", 400) from None
            if not 1 <= limit <= 200:
                raise HTTPError("limit must be between 1 and 200", 400)
            status = query.get("status", [None])[0] or None
            return self._json(self.server.app.web_facts(limit, status))
        if path == "/api/web/export":
            include_rejected = parse_qs(parsed.query).get("include_rejected", ["0"])[0]
            if include_rejected not in {"0", "1"}:
                raise HTTPError("include_rejected must be 0 or 1", 400)
            try:
                body, content_type, filename = self.server.app.export_web_facts(
                    include_rejected == "1")
            except ModelSwitchUnavailable as error:
                raise HTTPError(str(error), 409) from None
            return self._download(body, content_type, filename)
        export = re.fullmatch(r"/api/sessions/([0-9a-f]{32})/export", path)
        if export:
            fmt = parse_qs(parsed.query).get("format", ["md"])[0].lower()
            body, content_type, filename = self.server.app.export_session(export.group(1), fmt)
            return self._download(body, content_type, filename)
        session = re.fullmatch(r"/api/sessions/([0-9a-f]{32})", path)
        if session:
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["200"])[0])
            except (TypeError, ValueError):
                raise HTTPError("limit must be an integer", 400) from None
            if not 1 <= limit <= 1000:
                raise HTTPError("limit must be between 1 and 1000", 400)
            before_raw = query.get("before", [None])[0]
            before = None
            if before_raw is not None:
                try:
                    before = int(before_raw)
                except (TypeError, ValueError):
                    raise HTTPError("before must be a message id", 400) from None
                if before < 1:
                    raise HTTPError("before must be a positive message id", 400)
            return self._json(self.server.app.get_session(
                session.group(1), limit=limit, before=before))
        raise HTTPError("not found", 404)

    def _index(self, parsed) -> None:
        token = parse_qs(parsed.query).get("token", [None])[0]
        if token and self.server.app.authenticated(token):
            self._responded = True
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Set-Cookie",
                             f"{COOKIE}={self.server.app.token}; Path=/; HttpOnly; "
                             f"SameSite=Strict; Max-Age={COOKIE_MAX_AGE}")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self._file(STATIC / "index.html", cache=False)

    # ---- POST -----------------------------------------------------------------------------
    def _post(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/login":
            return self._login()
        self._api_guard()
        self._csrf_guard()
        if path == "/api/logout":
            self._discard_body(limit=4096)
            self._responded = True
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", f"{COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")
            body = b'{"ok": true}'
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return self.wfile.write(body)
        if path == "/api/chat":
            return self._chat()
        if path == "/api/chat/stream":
            return self._chat_stream()
        if path == "/api/model":
            self._rate("model", 20)
            payload = self._body(limit=4096)
            try:
                return self._json(self.server.app.select_model(payload.get("model")))
            except ModelNotInstalled as error:
                raise HTTPError(str(error), 404) from None
            except ModelSwitchUnavailable as error:
                raise HTTPError(str(error), 409) from None
            except ValueError as error:
                raise HTTPError(str(error), 400) from None
            except OllamaError as error:
                raise HTTPError(str(error), 503) from None
            except RuntimeError as error:
                raise HTTPError(str(error), 503) from None
        if path == "/api/ocr":
            return self._ocr()
        if path == "/api/web/review":
            self._rate("web-review", 30)
            payload = self._body(limit=8192)
            fact_id = payload.get("id")
            status = payload.get("status")
            note = payload.get("note", "")
            if isinstance(fact_id, str) and fact_id.isdigit():
                fact_id = int(fact_id)
            if not isinstance(fact_id, int) or isinstance(fact_id, bool):
                raise HTTPError("id must be an integer", 400)
            if not isinstance(status, str):
                raise HTTPError("status must be a string", 400)
            if not isinstance(note, str):
                raise HTTPError("note must be a string", 400)
            try:
                return self._json(self.server.app.review_web_fact(fact_id, status, note))
            except KeyError as error:
                raise HTTPError(str(error.args[0]) if error.args else str(error), 404) from None
            except ModelSwitchUnavailable as error:
                raise HTTPError(str(error), 409) from None
        if path == "/api/sessions":
            payload = self._body()
            title = payload.get("title", "New chat")
            if not isinstance(title, str):
                raise HTTPError("title must be a string", 400)
            return self._json({"session": self.server.app.create_session(title)}, 201)
        raise HTTPError("not found", 404)

    def _login(self) -> None:
        self._rate("login", 10)
        payload = self._body(limit=4096)
        token = payload.get("token")
        if not isinstance(token, str) or not self.server.app.authenticated(token):
            raise HTTPError("invalid access token", 401)
        self._json({"ok": True, "csrf": self.server.app.csrf}, headers=[
            ("Set-Cookie", f"{COOKIE}={self.server.app.token}; Path=/; HttpOnly; "
                           f"SameSite=Strict; Max-Age={COOKIE_MAX_AGE}")])

    def _chat(self) -> None:
        self._rate("chat", 60)
        payload = self._body()
        message = payload.get("message")
        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise HTTPError("session_id must be a string", 400)
        if not isinstance(message, str):
            raise HTTPError("message must be a string", 400)
        web_search = payload.get("web_search", False)
        if not isinstance(web_search, bool):
            raise HTTPError("web_search must be a boolean", 400)
        _, job = self.server.app.start_chat(message, session_id, stream=False,
                                            force=("web",) if web_search else ())
        try:
            result = job.wait(JOB_TIMEOUT)
        except TimeoutError:
            job.cancel()
            raise HTTPError("model timed out", 504) from None
        self._json(result)

    def _chat_stream(self) -> None:
        self._rate("chat", 60)
        payload = self._body()
        message = payload.get("message")
        session_id = payload.get("session_id")
        if session_id is not None and not isinstance(session_id, str):
            raise HTTPError("session_id must be a string", 400)
        if not isinstance(message, str):
            raise HTTPError("message must be a string", 400)
        web_search = payload.get("web_search", False)
        if not isinstance(web_search, bool):
            raise HTTPError("web_search must be a boolean", 400)

        cancel = threading.Event()
        session, job = self.server.app.start_chat(
            message, session_id, stream=True, cancel_event=cancel,
            force=("web",) if web_search else ())
        self._responded = True
        self.close_connection = True
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
        except OSError:
            job.cancel()
            return

        def send_event(name: str, data: dict) -> None:
            body = f"event: {name}\ndata: {json.dumps(data, default=str)}\n\n".encode("utf-8")
            self.wfile.write(body)
            self.wfile.flush()

        try:
            send_event("meta", {
                "session_id": session["id"],
                "job_id": job.id,
                "model": self.server.app.status().get("model"),
                "queue_depth": self.server.app.worker.stats()["queue_depth"],
            })
            deadline = time.monotonic() + STREAM_DEADLINE
            while True:
                try:
                    kind, data = job.events.get(timeout=15)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        job.cancel()
                        send_event("error", {"error": "stream deadline exceeded"})
                        break
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    if job.done.is_set():
                        break
                    continue
                if kind == "token":
                    send_event("token", {"text": data})
                elif kind == "done":
                    send_event("done", data)
                    break
                elif kind == "error":
                    send_event("error", data)
                    break
                elif kind == "cancelled":
                    send_event("cancelled", data)
                    break
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            cancel.set()
            job.cancel()
        finally:
            if not job.done.is_set():
                job.cancel()

    def _ocr(self) -> None:
        self._rate("ocr", 30)
        payload = self._body(MAX_OCR_BODY)
        filename = payload.get("filename", "upload.png")
        data = payload.get("data")
        session_id = payload.get("session_id")
        prompt = payload.get("prompt")
        if not isinstance(filename, str):
            raise HTTPError("filename must be a string", 400)
        if not isinstance(data, str):
            raise HTTPError("data must be a base64 string", 400)
        if session_id is not None and not isinstance(session_id, str):
            raise HTTPError("session_id must be a string", 400)
        if prompt is not None and not isinstance(prompt, str):
            raise HTTPError("prompt must be a string", 400)
        _, job = self.server.app.start_ocr(filename, data, session_id, prompt)
        try:
            result = job.wait(JOB_TIMEOUT)
        except TimeoutError:
            job.cancel()
            raise HTTPError("OCR timed out", 504) from None
        self._json(result)

    # ---- PATCH / DELETE -------------------------------------------------------------------
    def _patch(self) -> None:
        self._api_guard()
        self._csrf_guard()
        match = re.fullmatch(r"/api/sessions/([0-9a-f]{32})", urlparse(self.path).path)
        if not match:
            raise HTTPError("not found", 404)
        payload = self._body()
        title = payload.get("title")
        if not isinstance(title, str):
            raise HTTPError("title must be a string", 400)
        self._json({"session": self.server.app.rename_session(match.group(1), title)})

    def _delete(self) -> None:
        self._api_guard()
        self._csrf_guard()
        match = re.fullmatch(r"/api/sessions/([0-9a-f]{32})", urlparse(self.path).path)
        if not match:
            raise HTTPError("not found", 404)
        self._discard_body(limit=4096)
        self.server.app.delete_session(match.group(1))
        self._json({"deleted": True})


class AppHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, app: WebApp):
        self.app = app
        super().__init__(address, Handler)


class AppHTTPServerV6(AppHTTPServer):
    address_family = socket.AF_INET6


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="%(message)s", stream=sys.stderr, force=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ashura-web", description="Local ASHURA web interface")
    parser.add_argument("--config", default="config/ashura.toml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the browser after starting")
    parser.add_argument("--token", default=os.environ.get("ASHURA_WEB_TOKEN") or None,
                        help="fixed access token; omitted means the token is loaded or generated")
    parser.add_argument("--token-file", default=None,
                        help="persisted token path (default: [ui].token_file or <data>/web_token)")
    parser.add_argument("--no-persist-token", action="store_true",
                        help="generate an ephemeral token instead of reusing the token file")
    parser.add_argument("--sessions-db", default=None,
                        help="chat-session database (default: [ui].sessions_db or "
                             "<memory db directory>/ui_sessions.db)")
    parser.add_argument("--max-queue", type=int, default=8, help="bounded controller job queue")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    if not is_loopback(args.host):
        print("refusing to bind a non-loopback address: this interface has no TLS and is local-only",
              file=sys.stderr)
        return 2
    configure_logging(args.log_level)
    controller = None
    sessions = None
    app = None
    server = None
    token_info = None
    try:
        controller = build(args.config)
        cfg = load_config(resolve_config(args.config))
        ui = cfg.get("ui", {}) if isinstance(cfg.get("ui", {}), dict) else {}
        memory_section = cfg.get("memory", {}) if isinstance(cfg.get("memory", {}), dict) else {}
        memory_db = str(memory_section.get("db_path", "data/ashura.db"))
        default_sessions = (Path(memory_db).parent / "ui_sessions.db").as_posix()
        session_db = args.sessions_db or ui.get("sessions_db", default_sessions)
        token = args.token
        if token is None:
            persist = bool(ui.get("persist_token", True)) and not args.no_persist_token
            if persist:
                token_path = args.token_file or ui.get("token_file")
                if not token_path:
                    token_path = (Path(memory_db).parent / "web_token").as_posix()
                stored = load_or_create_token(token_path)
                token, token_info = stored.token, stored
            else:
                token = secrets.token_urlsafe(32)
        sessions = SessionStore(session_db)
        app = WebApp(controller, args.config, sessions=sessions, token=token,
                     max_queue=max(1, args.max_queue))
        server_type = AppHTTPServerV6 if ":" in args.host else AppHTTPServer
        server = server_type((args.host, args.port), app)
    except Exception as error:  # noqa: BLE001 - startup failures belong on stderr
        print(f"could not start ASHURA web UI: {error}", file=sys.stderr)
        if app is not None:
            app.close()
        elif sessions is not None:
            sessions.close()
            if controller is not None:
                controller.close()
        elif controller is not None:
            controller.close()
        return 1

    display_host = f"[{args.host}]" if ":" in args.host else args.host
    url = f"http://{display_host}:{server.server_port}/"
    print(f"ASHURA web UI: {url}")
    if args.token:
        print("access token: supplied")
    elif token_info is not None:
        print(f"access token: {app.token}")
        print(f"token file: {token_info.path} ({token_info.status}; {token_info.permissions_note})")
    else:
        print(f"access token: {app.token} (ephemeral; not persisted)")
    print("loopback only · Ctrl-C to stop")
    if args.open:
        webbrowser.open(url + "?token=" + quote(app.token))
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
        app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
