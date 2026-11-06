"""Small, bounded local tools for the agentic turn.

The tools are deliberately read-only over the repository plus a single sandboxed note
directory. They never reach the network, never accept an absolute path outside the
workspace and never execute a shell command. Each result is an observation with an
explicit error state; the model is told not to invent one.

The Ollama tool protocol is the native ``/api/chat`` function-call format already used
by ``evaluation.agentic_bench``. Keeping the schema here makes the console and the
benchmark exercise the same tool definitions instead of a second, untested protocol.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from skills.arithmetic import exact
from skills.arithmetic.parser import extract_expression
from skills.perception.documents import TEXT_SUFFIXES

MAX_READ_BYTES = 512 * 1024
MAX_READ_CHARS = 20_000
MAX_MATCHES = 40
MAX_WALK_FILES = 2_000
MAX_LIST_ENTRIES = 200
MAX_NOTE_BYTES = 64 * 1024
SKIP_DIRS = {".git", ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache",
             ".ruff_cache", ".venv", "venv", "env", "node_modules", "data", "results",
             "checkpoints", ".idea", ".vscode"}
PROTECTED_CREATE_DIRS = {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules"}


class ToolError(ValueError):
    """A tool call was valid JSON but not allowed or not executable."""


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _safe_root(root: str | os.PathLike | None = None) -> Path:
    candidate = Path(root or os.environ.get("ASHURA_WORKSPACE") or Path.cwd()).resolve()
    return candidate


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.name


def _resolve(root: Path, raw: Any, *, must_exist: bool = True) -> Path:
    if raw is None or raw == "":
        raw = "."
    if not isinstance(raw, str):
        raise ToolError("path must be a string")
    value = raw.strip().replace("\\", "/")
    if "\x00" in value:
        raise ToolError("path contains a null byte")
    if len(value) > 400:
        raise ToolError("path is too long")
    path = Path(value)
    if path.is_absolute():
        candidate = path.resolve()
    else:
        candidate = (root / path).resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolError("path escapes the ASHURA workspace")
    if must_exist and not candidate.exists():
        raise ToolError(f"path does not exist: {value}")
    return candidate


def _text_suffix(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"README", "LICENSE", "Makefile"}


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    output: str
    args: dict = field(default_factory=dict)
    elapsed_ms: float = 0.0
    error: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[[dict], str]

    def schema(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }}


class ToolRegistry:
    def __init__(self, root: str | os.PathLike | None = None):
        self.root = _safe_root(root)
        self._specs: dict[str, ToolSpec] = {}
        for spec in self._build_specs():
            self._specs[spec.name] = spec

    def names(self) -> list[str]:
        return list(self._specs)

    def schemas(self) -> list[dict]:
        return [spec.schema() for spec in self._specs.values()]

    def execute(self, name: str, args: Any) -> ToolResult:
        started = time.perf_counter()
        spec = self._specs.get(name)
        if spec is None:
            return ToolResult(name, False, _json({"error": f"unknown tool {name!r}",
                                                  "available": self.names()}),
                              args if isinstance(args, dict) else {}, 0.0, "unknown tool")
        if not isinstance(args, dict):
            return ToolResult(name, False, _json({"error": "arguments must be an object"}),
                              {}, 0.0, "invalid arguments")
        try:
            output = spec.handler(args)
            return ToolResult(name, True, output, args,
                              (time.perf_counter() - started) * 1000)
        except ToolError as error:
            return ToolResult(name, False, _json({"error": str(error)}), args,
                              (time.perf_counter() - started) * 1000, str(error))
        except (OSError, ValueError, ArithmeticError, RecursionError, MemoryError) as error:
            message = f"{type(error).__name__}: {str(error)[:200]}"
            return ToolResult(name, False, _json({"error": message}), args,
                              (time.perf_counter() - started) * 1000, message)

    # ---- tool implementations ---------------------------------------------------------------
    def _build_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                "list_files",
                "List files and directories inside the ASHURA workspace. Use a relative path and "
                "an optional glob such as '*.py'.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "relative directory, default '.'"},
                    "pattern": {"type": "string", "description": "optional glob, e.g. '*.py'"},
                }}, self._list_files),
            ToolSpec(
                "read_text_file",
                "Read a UTF-8 or plain-text file inside the workspace. Large files are truncated "
                "and reported as truncated.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "relative file path"},
                }, "required": ["path"]}, self._read_text_file),
            ToolSpec(
                "search_text",
                "Search text files inside the workspace for a literal string. Returns path, line "
                "number and a short snippet.",
                {"type": "object", "properties": {
                    "query": {"type": "string", "description": "literal text to find"},
                    "path": {"type": "string", "description": "relative directory, default '.'"},
                    "glob": {"type": "string", "description": "optional filename glob"},
                }, "required": ["query"]}, self._search_text),
            ToolSpec(
                "file_info",
                "Return size, line count and a SHA-256 prefix for one workspace file.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "relative file path"},
                }, "required": ["path"]}, self._file_info),
            ToolSpec(
                "calculate",
                "Evaluate an exact arithmetic expression with ASHURA's deterministic evaluator.",
                {"type": "object", "properties": {
                    "expression": {"type": "string", "description": "e.g. 37*24+19"},
                }, "required": ["expression"]}, self._calculate),
            ToolSpec(
                "current_time",
                "Return the local date and time of this machine and its timezone.",
                {"type": "object", "properties": {}}, self._current_time),
            ToolSpec(
                "text_stats",
                "Count characters, words and lines in a string.",
                {"type": "object", "properties": {
                    "text": {"type": "string"},
                }, "required": ["text"]}, self._text_stats),
            ToolSpec(
                "system_info",
                "Report the local operating system, Python version and workspace root. No "
                "network information is collected.",
                {"type": "object", "properties": {}}, self._system_info),
            ToolSpec(
                "create_directory",
                "Create the requested directory inside the ASHURA workspace. Use the exact "
                "workspace-relative path the user gave; parent folders are created as needed. "
                "Absolute paths outside the workspace and protected runtime folders are refused.",
                {"type": "object", "properties": {
                    "path": {"type": "string", "description": "workspace-relative folder path"},
                }, "required": ["path"]}, self._create_directory),
            ToolSpec(
                "write_note",
                "Write a short note into the sandboxed data/agent directory. Never overwrites "
                "outside that directory.",
                {"type": "object", "properties": {
                    "name": {"type": "string", "description": "file name, e.g. notes.md"},
                    "content": {"type": "string", "description": "UTF-8 text"},
                }, "required": ["name", "content"]}, self._write_note),
        ]

    def _list_files(self, args: dict) -> str:
        target = _resolve(self.root, args.get("path"))
        if not target.is_dir():
            raise ToolError(f"not a directory: {args.get('path')}")
        pattern = args.get("pattern") or "*"
        if not isinstance(pattern, str) or len(pattern) > 120 or ".." in pattern:
            raise ToolError("invalid glob pattern")
        entries = []
        for path in sorted(target.glob(pattern), key=lambda item: (not item.is_dir(), item.name.lower())):
            if any(part in SKIP_DIRS for part in path.parts) or path.is_symlink():
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append({
                "path": _relative(path, self.root),
                "type": "dir" if path.is_dir() else "file",
                "bytes": None if path.is_dir() else stat.st_size,
            })
            if len(entries) >= MAX_LIST_ENTRIES:
                break
        return _json({"root": str(self.root), "pattern": pattern, "entries": entries,
                      "truncated": len(entries) >= MAX_LIST_ENTRIES})

    def _read_text_file(self, args: dict) -> str:
        target = _resolve(self.root, args.get("path"))
        if not target.is_file():
            raise ToolError("not a file")
        if not _text_suffix(target):
            raise ToolError(f"refusing to read non-text extension {target.suffix or '(none)'}")
        data = target.read_bytes()
        if len(data) > MAX_READ_BYTES:
            data = data[:MAX_READ_BYTES]
            size_truncated = True
        else:
            size_truncated = False
        if b"\x00" in data[:4096]:
            raise ToolError("file looks binary")
        text = data.decode("utf-8", errors="replace")
        truncated = size_truncated or len(text) > MAX_READ_CHARS
        return _json({"path": _relative(target, self.root), "text": text[:MAX_READ_CHARS],
                      "truncated": truncated, "bytes": target.stat().st_size})

    def _search_text(self, args: dict) -> str:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip():
            raise ToolError("query must be a non-empty string")
        if len(query) > 200:
            raise ToolError("query is too long")
        target = _resolve(self.root, args.get("path"))
        if target.is_file():
            files = [target]
        else:
            files = []
            for base, dirs, names in os.walk(target, followlinks=False):
                dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
                for name in names:
                    if name.startswith("."):
                        continue
                    path = Path(base) / name
                    if _text_suffix(path):
                        files.append(path)
                if len(files) >= MAX_WALK_FILES:
                    break
        pattern = args.get("glob")
        if pattern:
            if not isinstance(pattern, str) or ".." in pattern or len(pattern) > 120:
                raise ToolError("invalid glob")
            files = [path for path in files if path.match(pattern)]
        needle = query.casefold()
        matches = []
        for path in files[:MAX_WALK_FILES]:
            try:
                resolved = path.resolve()
                if resolved != self.root and self.root not in resolved.parents:
                    continue
                if not resolved.is_file() or resolved.stat().st_size > MAX_READ_BYTES:
                    continue
                text = resolved.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if b"\x00" in text[:512].encode("utf-8", errors="ignore"):
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if needle in line.casefold():
                    matches.append({"path": _relative(resolved, self.root), "line": number,
                                    "snippet": line.strip()[:240]})
                    if len(matches) >= MAX_MATCHES:
                        break
            if len(matches) >= MAX_MATCHES:
                break
        return _json({"query": query, "matches": matches,
                      "truncated": len(matches) >= MAX_MATCHES})

    def _file_info(self, args: dict) -> str:
        target = _resolve(self.root, args.get("path"))
        if not target.is_file():
            raise ToolError("not a file")
        digest = hashlib.sha256()
        size = 0
        newlines = 0
        last = b""
        with target.open("rb") as handle:
            while True:
                chunk = handle.read(256 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                newlines += chunk.count(b"\n")
                last = chunk[-1:]
                digest.update(chunk)
        lines = newlines + (1 if size and last != b"\n" else 0)
        return _json({
            "path": _relative(target, self.root), "bytes": size,
            "lines": lines, "suffix": target.suffix,
            "sha256_prefix": digest.hexdigest()[:16],
            "modified": datetime.fromtimestamp(target.stat().st_mtime).isoformat(timespec="seconds"),
        })

    def _calculate(self, args: dict) -> str:
        expression = args.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            raise ToolError("expression must be a non-empty string")
        expr = extract_expression(expression) or expression.strip()
        value = exact.evaluate(expr)
        return _json({"expression": expr, "value": exact.format_value(value)})

    def _current_time(self, args: dict) -> str:
        now = datetime.now().astimezone()
        return _json({"iso": now.isoformat(timespec="seconds"),
                      "timezone": getattr(now.tzinfo, "key", None) or now.tzname(),
                      "utc_offset": now.strftime("%z")})

    def _text_stats(self, args: dict) -> str:
        text = args.get("text")
        if not isinstance(text, str):
            raise ToolError("text must be a string")
        return _json({"characters": len(text), "words": len(text.split()),
                      "lines": text.count("\n") + (1 if text else 0)})

    def _system_info(self, args: dict) -> str:
        return _json({"platform": platform.platform(), "python": sys.version.split()[0],
                      "machine": platform.machine(), "workspace": str(self.root),
                      "cwd": str(Path.cwd())})

    def _create_directory(self, args: dict) -> str:
        raw = args.get("path")
        if not isinstance(raw, str) or not raw.strip():
            raise ToolError("path must be a non-empty workspace-relative directory path")
        target = _resolve(self.root, raw, must_exist=False)
        relative = target.relative_to(self.root)
        if not relative.parts:
            raise ToolError("refusing to treat the workspace root as a new directory")
        if any(part.casefold() in PROTECTED_CREATE_DIRS for part in relative.parts):
            raise ToolError("refusing to create directories inside protected runtime folders")
        if target.exists() and not target.is_dir():
            raise ToolError(f"a file already exists at the requested path: {_relative(target, self.root)}")
        created = not target.exists()
        target.mkdir(parents=True, exist_ok=True)
        return _json({"path": _relative(target, self.root), "created": created,
                      "workspace": str(self.root)})

    def _write_note(self, args: dict) -> str:
        name = args.get("name")
        content = args.get("content")
        if not isinstance(name, str) or not name.strip():
            raise ToolError("name must be a non-empty string")
        if not isinstance(content, str):
            raise ToolError("content must be a string")
        safe_name = Path(name).name
        if safe_name != name or safe_name in {"", ".", ".."} or "\x00" in safe_name:
            raise ToolError("name must be a plain file name with no path components")
        if os.name == "nt" and ":" in safe_name:
            raise ToolError("file names with drive or stream separators are not allowed")
        raw = content.encode("utf-8")
        if len(raw) > MAX_NOTE_BYTES:
            raise ToolError(f"note is larger than {MAX_NOTE_BYTES // 1024} KB")
        folder = (self.root / "data" / "agent").resolve()
        folder.mkdir(parents=True, exist_ok=True)
        target = (folder / safe_name).resolve()
        if folder not in target.parents:
            raise ToolError("note path escapes the sandbox")
        target.write_text(content, encoding="utf-8")
        return _json({"path": _relative(target, self.root), "bytes": len(raw)})


# Cues that a request genuinely needs environment access. Ordinary explanations stay on the
# fast single-call path; offering tools for every question would add latency and invented calls.
_TOOL_CUES = re.compile(
    r"(?:\b(?:file|files|folder|folders|directory|directories|repo|repository|workspace|"
    r"codebase|source code|project files|tree)\b)"
    r"|(?:\b(?:list|read|open|inspect|search|find|grep|locate|scan)\b.{0,40}"
    r"\b(?:file|files|folder|directory|repo|repository|workspace|codebase|content|contents)\b)"
    r"|(?:\b(?:what(?:'s| is) (?:in|inside)|show me (?:the )?(?:files|contents)|"
    r"look at|check the|how many (?:files|lines|words))\b)"
    r"|(?:\b(?:current (?:time|date)|what time|today'?s date|time is it|system info|"
    r"operating system|python version)\b)"
    r"|(?:\b(?:use|using|with) (?:the )?tools?\b|\bagentic\b|multi[- ]step)"
    r"|(?:\b(?:calculate|compute|evaluate)\b.{0,80}\b(?:expression|sum|product|result)\b)",
    re.IGNORECASE,
)


def task_needs_tools(text: str) -> bool:
    return bool(_TOOL_CUES.search(text or ""))


def tool_prompt(task: str, history: tuple[tuple[str, str], ...] = ()) -> str:
    """Prompt for the final answer after tool observations have been collected."""
    return task
