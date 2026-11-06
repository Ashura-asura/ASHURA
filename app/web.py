"""Local web UI for ASHURA.

Stdlib-only HTTP server, bound to localhost. It serves a small static single-page app and a JSON
API over the same Controller used by the CLI. One request is handled at a time, matching the
single-model/single-SQLite-connection runtime used by the rest of the project.

    python -m app.web --config config/ashura.ollama.toml
    python -m app.web --open
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import mimetypes
import os
import sys
import tempfile
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.main import build
from brain.need_field import Task

STATIC = Path(__file__).with_name("static")
MAX_BODY = 12 * 1024 * 1024
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def serialize_response(response) -> dict:
    trace = response.trace
    return {
        "text": response.text,
        "verified": response.verified,
        "admission": response.admission,
        "attribution": response.attribution,
        "correction": response.correction,
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
    if not path.startswith("/static/"):
        return None
    root = STATIC.resolve()
    candidate = (root / path[len("/static/"):]).resolve()
    if root not in candidate.parents or not candidate.is_file():
        return None
    return candidate


class WebApp:
    def __init__(self, controller, config_path: str):
        self.controller = controller
        self.config_path = config_path
        self.started = time.time()

    def _count(self, sql: str) -> int | None:
        try:
            return int(self.controller.ama.db.conn.execute(sql).fetchone()[0])
        except Exception:
            return None

    def status(self) -> dict:
        return {
            "model": self.controller.model.name,
            "config": str(self.config_path),
            "database": getattr(getattr(self.controller.ama, "db", None), "path", None),
            "uptime_s": round(time.time() - self.started, 1),
            "counts": {
                "experiences": self._count("SELECT COUNT(*) FROM experiences"),
                "facts": self._count("SELECT COUNT(*) FROM facts"),
                "conflicts_open": self._count("SELECT COUNT(*) FROM conflicts WHERE status = 'open'"),
                "fts_rows": self._count("SELECT COUNT(*) FROM fts_index"),
            },
        }

    def chat(self, message: str) -> dict:
        message = (message or "").strip()
        if not message:
            raise ValueError("message must not be empty")
        return serialize_response(self.controller.handle(Task(message)))

    def ocr(self, filename: str, encoded: str) -> dict:
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("invalid base64 image data") from error
        if not raw or len(raw) > MAX_BODY:
            raise ValueError("image is empty or too large")
        suffix = Path(filename or "upload.png").suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".png"
        fd, path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            task = Task("Read the text in this image.", has_image=True, image_path=path,
                        force=("ocr",))
            return serialize_response(self.controller.handle(task))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def memory(self, query: str = "", limit: int = 20) -> dict:
        limit = max(1, min(int(limit), 50))
        ama = self.controller.ama
        if ama is None:
            return {"query": query, "items": []}
        if query.strip():
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
                row["conflict"] = bool(json.loads(row.pop("related_ids") or "[]"))
                row["label"] = row["status"]
        return {"query": query, "items": rows}


class Handler(BaseHTTPRequestHandler):
    server_version = "ASHURAWeb/0.1"

    def log_message(self, fmt, *args):  # keep the console readable; errors still reach stderr
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ValueError("invalid Content-Length") from None
        if length <= 0:
            raise ValueError("request body is required")
        if length > MAX_BODY:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON: {error.msg}") from None
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _file(self, path: Path) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            return self._error("static file not found", 404)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript",
                                                                "application/json"}:
            content_type += "; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            return self._file(STATIC / "index.html")
        if parsed.path.startswith("/static/"):
            path = static_file(parsed.path)
            return self._file(path) if path else self._error("static file not found", 404)
        if parsed.path == "/api/status":
            return self._json(self.server.app.status())
        if parsed.path == "/api/memory":
            query = parse_qs(parsed.query)
            try:
                return self._json(self.server.app.memory(
                    query.get("q", [""])[0], int(query.get("limit", ["20"])[0])))
            except (TypeError, ValueError) as error:
                return self._error(str(error))
        if parsed.path == "/api/health":
            return self._json({"ok": True})
        return self._error("not found", 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            payload = self._body()
        except ValueError as error:
            return self._error(str(error), 413 if "too large" in str(error) else 400)
        try:
            if parsed.path == "/api/chat":
                return self._json(self.server.app.chat(str(payload.get("message", ""))))
            if parsed.path == "/api/ocr":
                return self._json(self.server.app.ocr(
                    str(payload.get("filename", "upload.png")),
                    str(payload.get("data", ""))))
        except ValueError as error:
            return self._error(str(error))
        except Exception as error:  # noqa: BLE001 - one bad request must not kill the server
            return self._error(f"{type(error).__name__}: {error}", 500)
        return self._error("not found", 404)


class AppHTTPServer(HTTPServer):
    def __init__(self, address, app: WebApp):
        self.app = app
        super().__init__(address, Handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ashura-web", description="Local ASHURA web UI")
    parser.add_argument("--config", default="config/ashura.toml")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", help="open the browser after starting")
    args = parser.parse_args(argv)

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        print("refusing to bind a non-loopback address: this UI has no authentication",
              file=sys.stderr)
        return 2
    try:
        controller = build(args.config)
    except Exception as error:  # noqa: BLE001 - config/model/DB startup errors belong on stderr
        print(f"could not start ASHURA: {error}", file=sys.stderr)
        return 1
    app = WebApp(controller, args.config)
    try:
        server = AppHTTPServer((args.host, args.port), app)
    except OSError as error:
        controller.close()
        print(f"could not bind {args.host}:{args.port}: {error}", file=sys.stderr)
        return 1
    url = f"http://{args.host}:{server.server_port}/"
    print(f"ASHURA web UI: {url}  (Ctrl-C to stop)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        server.server_close()
        worker = getattr(controller, "learning_worker", None)
        if worker is not None:
            worker.close(timeout=5)
        controller.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
