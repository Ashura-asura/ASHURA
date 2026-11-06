"""Local web-research tools and the candidate-fact dataset store.

Network access happens only inside the server process and only when the operator enabled
the ``[web]`` section or the model explicitly calls a web tool. The browser never talks
to a third party (the CSP still restricts ``connect-src`` to ``'self'``).

Search uses a keyless provider chain: DuckDuckGo Lite, then Wikipedia, or a configured
SearXNG instance. Page fetching is bounded, text-only and rejects loopback/private hosts
by default so the agent cannot use the console as a local-network proxy.
"""
from __future__ import annotations

import contextlib
import hashlib
import html
import ipaddress
import json
import re
import socket
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from memory.text import normalize
from skills.perception.documents import MAX_EXTRACT_CHARS, html_to_text

USER_AGENT = "ASHURA-local-console/0.2 (+loopback research tool)"
DDG_LITE = "https://lite.duckduckgo.com/lite/"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
MAX_PAGE_BYTES = 1_500_000
MAX_SEARCH_BYTES = 1_000_000
MAX_PAGE_TEXT = 20_000


class WebError(RuntimeError):
    """A search or fetch failed; the caller must treat this as no evidence."""


@dataclass(frozen=True)
class WebConfig:
    enabled: bool = False
    provider: str = "duckduckgo"      # duckduckgo | wikipedia | searxng
    searx_url: str = ""
    timeout_s: float = 15.0
    max_results: int = 5
    max_fetch_pages: int = 2
    max_page_chars: int = 3500
    auto_on_uncertainty: bool = True
    allow_private_hosts: bool = False  # tests/dev only; never enable on a shared network
    facts_db: str = "data/web_facts.db"
    dataset_dir: str = "data/web_training"

    def __post_init__(self) -> None:
        if self.provider not in {"duckduckgo", "wikipedia", "searxng"}:
            raise ValueError("web.provider must be duckduckgo, wikipedia or searxng")
        if self.provider == "searxng" and not self.searx_url.strip():
            raise ValueError("web.searx_url is required when provider = 'searxng'")
        if not 1 <= self.max_results <= 10:
            raise ValueError("web.max_results must be between 1 and 10")
        if not 0 <= self.max_fetch_pages <= 5:
            raise ValueError("web.max_fetch_pages must be between 0 and 5")
        if not 500 <= self.max_page_chars <= 20_000:
            raise ValueError("web.max_page_chars must be between 500 and 20000")
        if self.timeout_s <= 0:
            raise ValueError("web.timeout_s must be positive")

    @classmethod
    def from_dict(cls, values: dict) -> "WebConfig":
        names = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = sorted(set(values) - names)
        if unknown:
            raise ValueError(f"web: unknown key(s) {unknown}; valid keys: {sorted(names)}")
        return cls(**values)


@dataclass(frozen=True)
class WebResult:
    title: str
    url: str
    snippet: str
    provider: str

    def as_dict(self) -> dict:
        return {"title": self.title, "url": self.url, "snippet": self.snippet,
                "provider": self.provider}


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str | None
    text: str
    content_type: str
    truncated: bool
    fetched_at: str = field(default_factory=lambda: datetime.now().astimezone().isoformat(timespec="seconds"))


class _DDGLiteParser(HTMLParser):
    """Parse DuckDuckGo Lite's result table without executing anything."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_link = False
        self._in_snippet = False
        self._link_href = ""
        self._link_text: list[str] = []
        self._snippet_text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        if tag in {"script", "style"}:
            self._skip += 1
        if tag == "a" and "result-link" in classes:
            self._flush()
            self._in_link = True
            self._link_href = attrs.get("href") or ""
            self._link_text = []
        elif tag == "td" and "result-snippet" in classes:
            self._in_snippet = True
            self._snippet_text = []
        elif self._in_snippet and tag == "span" and "link-text" in classes:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self._skip:
            self._skip -= 1
        elif tag == "a" and self._in_link:
            self._in_link = False
        elif tag == "td" and self._in_snippet:
            self._in_snippet = False
        elif self._in_snippet and tag == "span" and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_link:
            self._link_text.append(data)
        elif self._in_snippet:
            self._snippet_text.append(data)

    def _flush(self):
        if not self._link_href:
            return
        if self.results and self.results[-1].get("snippet") == "":
            self.results[-1]["snippet"] = _clean(" ".join(self._snippet_text))
        self.results.append({
            "url": _decode_ddg_url(self._link_href),
            "title": _clean(" ".join(self._link_text)) or "Untitled result",
            "snippet": "",
        })

    def close(self):
        super().close()
        self._flush()
        if self.results and not self.results[-1].get("snippet"):
            self.results[-1]["snippet"] = _clean(" ".join(self._snippet_text))


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _decode_ddg_url(href: str) -> str:
    value = html.unescape(href or "")
    if value.startswith("//"):
        value = "https:" + value
    parsed = urllib.parse.urlsplit(value)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path == "/l/":
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return target
    return value


def _is_private_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return True
    for info in infos:
        address = info[4][0].split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            return True
        if not ip.is_global:
            return True
    return False


def _validate_url(raw: str, *, allow_private: bool) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise WebError("URL is empty")
    value = raw.strip()
    if len(value) > 2048:
        raise WebError("URL is too long")
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"}:
        raise WebError("only http and https URLs are allowed")
    if not parsed.hostname:
        raise WebError("URL has no host")
    if parsed.username or parsed.password:
        raise WebError("credentials in URLs are not allowed")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise WebError(f"invalid URL port: {error}") from None
    if not 1 <= port <= 65535:
        raise WebError("invalid URL port")
    if not allow_private and _is_private_host(parsed.hostname):
        raise WebError("refusing to fetch a loopback, private or link-local host")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/",
                                    parsed.query, ""))


def _read_limited(response, limit: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    total = 0
    while True:
        block = response.read(min(64 * 1024, limit - total + 1))
        if not block:
            break
        total += len(block)
        if total > limit:
            chunks.append(block[:limit - (total - len(block))])
            return b"".join(chunks), True
        chunks.append(block)
    return b"".join(chunks), False


def _decode_body(raw: bytes, encoding: str, limit: int) -> bytes:
    """Decompress a response without allowing a compression bomb to bypass the byte limit."""
    encoding = (encoding or "").lower().strip()
    if encoding not in {"gzip", "deflate"}:
        return raw
    attempts = [zlib.MAX_WBITS + 16] if encoding == "gzip" else [zlib.MAX_WBITS, -zlib.MAX_WBITS]
    for wbits in attempts:
        try:
            inflater = zlib.decompressobj(wbits)
            out = inflater.decompress(raw, limit + 1)
            if len(out) > limit:
                raise WebError(f"compressed response expands beyond {limit} bytes")
            return out
        except zlib.error:
            continue
    raise WebError("could not decompress the response")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable automatic redirects so every hop can be validated against the SSRF guard."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebSearch:
    def __init__(self, config: WebConfig | None = None):
        self.config = config or WebConfig()
        self._lock = threading.Lock()
        self._last_call = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.config.enabled)

    def _throttle(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = 0.5 - (now - self._last_call)
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()

    def _request(self, url: str, *, accept: str, limit: int, allow_private: bool = False,
                 headers: dict | None = None) -> tuple[bytes, str, str | None]:
        safe_url = _validate_url(url, allow_private=allow_private or self.config.allow_private_hosts)
        request = urllib.request.Request(safe_url, headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Encoding": "identity",
            **(headers or {}),
        })
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_s) as response:
                content_type = response.headers.get("Content-Type", "")
                raw = _read_limited(response, limit)[0]
                encoding = response.headers.get("Content-Encoding", "")
                return _decode_body(raw, encoding, limit), content_type, response.geturl()
        except urllib.error.HTTPError as error:
            raise WebError(f"provider returned HTTP {error.code}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
            raise WebError(f"network request failed: {error}") from None

    def search(self, query: str, limit: int | None = None) -> list[WebResult]:
        if not self.enabled:
            raise WebError("web search is disabled in this configuration")
        query = _clean(query)
        if not query or len(query) > 500:
            raise WebError("query must be 1..500 characters")
        count = max(1, min(int(limit or self.config.max_results), 10))
        self._throttle()
        errors: list[str] = []
        providers = {
            "duckduckgo": [self._search_ddg, self._search_wikipedia],
            "wikipedia": [self._search_wikipedia],
            "searxng": [self._search_searx, self._search_wikipedia],
        }[self.config.provider]
        for provider in providers:
            try:
                results = provider(query, count)
            except WebError as error:
                errors.append(str(error))
                continue
            if results:
                return results[:count]
        raise WebError("; ".join(errors) if errors else "no results returned")

    def _search_ddg(self, query: str, count: int) -> list[WebResult]:
        url = DDG_LITE + "?" + urllib.parse.urlencode({"q": query})
        raw, _content_type, _final = self._request(
            url, accept="text/html", limit=MAX_SEARCH_BYTES,
            headers={"Referer": "https://lite.duckduckgo.com/"},
        )
        parser = _DDGLiteParser()
        parser.feed(raw.decode("utf-8", errors="replace"))
        parser.close()
        results = []
        for item in parser.results:
            if not item.get("url", "").startswith(("http://", "https://")):
                continue
            results.append(WebResult(item["title"], item["url"], item.get("snippet", ""),
                                     "duckduckgo"))
            if len(results) >= count:
                break
        return results

    def _search_wikipedia(self, query: str, count: int) -> list[WebResult]:
        params = urllib.parse.urlencode({
            "action": "query", "list": "search", "srsearch": query,
            "format": "json", "utf8": "1", "srlimit": str(count),
        })
        raw, _content_type, _final = self._request(
            WIKIPEDIA_API + "?" + params, accept="application/json",
            limit=MAX_SEARCH_BYTES)
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as error:
            raise WebError(f"Wikipedia returned invalid JSON: {error}") from None
        if not isinstance(payload, dict):
            raise WebError("Wikipedia returned an unexpected response")
        results = []
        for item in (payload.get("query") or {}).get("search") or []:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            snippet = _clean(re.sub(r"<[^>]+>", " ", html.unescape(str(item.get("snippet") or ""))))
            title = str(item["title"])
            results.append(WebResult(
                title, "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                snippet, "wikipedia"))
        return results

    def _search_searx(self, query: str, count: int) -> list[WebResult]:
        base = self.config.searx_url.rstrip("/")
        url = base + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
        raw, _content_type, _final = self._request(
            url, accept="application/json", limit=MAX_SEARCH_BYTES, allow_private=True)
        try:
            payload = json.loads(raw.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as error:
            raise WebError(f"SearXNG returned invalid JSON: {error}") from None
        results = []
        for item in payload.get("results") or [] if isinstance(payload, dict) else []:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            results.append(WebResult(str(item.get("title") or "Untitled result"),
                                     str(item["url"]), str(item.get("content") or ""),
                                     "searxng"))
            if len(results) >= count:
                break
        return results

    def fetch(self, url: str, *, max_chars: int = MAX_PAGE_TEXT) -> WebPage:
        if not self.enabled:
            raise WebError("web access is disabled in this configuration")
        safe_url = _validate_url(url, allow_private=self.config.allow_private_hosts)
        self._throttle()
        opener = urllib.request.build_opener(_NoRedirect)
        current = safe_url
        response = None
        try:
            for _redirect in range(4):
                request = urllib.request.Request(current, headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html, text/plain, application/json;q=0.8",
                    "Accept-Encoding": "identity",
                })
                try:
                    response = opener.open(request, timeout=self.config.timeout_s)
                    break
                except urllib.error.HTTPError as error:
                    location = error.headers.get("Location") if error.headers else None
                    if error.code in {301, 302, 303, 307, 308} and location:
                        # Revalidate every redirect target: urllib's default handler would follow
                        # a public URL into loopback/private space.
                        current = _validate_url(
                            urllib.parse.urljoin(current, location),
                            allow_private=self.config.allow_private_hosts)
                        continue
                    raise WebError(f"page returned HTTP {error.code}") from None
            else:
                raise WebError("too many redirects")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            raw, limited = _read_limited(response, MAX_PAGE_BYTES)
            encoding = response.headers.get("Content-Encoding", "")
            raw = _decode_body(raw, encoding, MAX_PAGE_BYTES)
            final_url = response.geturl()
            charset = response.headers.get_content_charset() or "utf-8"
        except urllib.error.HTTPError as error:
            raise WebError(f"page returned HTTP {error.code}") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as error:
            raise WebError(f"page request failed: {error}") from None
        finally:
            if response is not None:
                try:
                    response.close()
                except OSError:
                    pass
        if content_type and not (content_type.startswith("text/") or
                                 content_type in {"application/json", "application/xhtml+xml"}):
            raise WebError(f"refusing non-text content type {content_type}")
        try:
            source = raw.decode(charset, errors="replace")
        except LookupError:
            source = raw.decode("utf-8", errors="replace")
        if content_type in {"application/json", "application/ld+json"}:
            title, text = None, source
        else:
            text, title = html_to_text(source)
        text = text[:max_chars]
        return WebPage(final_url, title, text, content_type or "text/plain",
                       limited or len(text) >= max_chars,
                       datetime.now().astimezone().isoformat(timespec="seconds"))


# ---- candidate facts and training dataset -----------------------------------------------------

_GAP_CUES = re.compile(
    r"\b(?:i (?:do not|don't) know|i(?:'m| am) not sure|i cannot (?:find|browse|access|confirm)|"
    r"i can't (?:find|browse|access|confirm)|unable to (?:find|verify|access)|"
    r"no (?:reliable |available )?(?:information|data|results)|"
    r"as of my (?:knowledge )?(?:cutoff|training)|beyond my (?:knowledge|training)|"
    r"not in my (?:knowledge|training)|my knowledge (?:cutoff|does not))\b",
    re.IGNORECASE,
)

_WEB_CUES = re.compile(
    r"\b(?:latest|current|today|tonight|this week|this month|news|recently|right now|"
    r"as of \d{4}|who won|released|release date|price|population|weather|"
    r"search (?:the )?(?:web|internet|online)|look (?:it |this )?up online)\b",
    re.IGNORECASE,
)


def looks_uncertain(text: str) -> bool:
    return bool(_GAP_CUES.search(text or ""))


def needs_web(text: str) -> bool:
    return bool(_WEB_CUES.search(text or ""))


_FACTS_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS web_gaps (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    question     TEXT NOT NULL,
    question_key TEXT NOT NULL,
    model_answer TEXT NOT NULL DEFAULT '',
    session_id   TEXT,
    model        TEXT,
    reason       TEXT NOT NULL DEFAULT '',
    resolved     INTEGER NOT NULL DEFAULT 0,
    fact_id      INTEGER,
    UNIQUE(question_key)
);
CREATE TABLE IF NOT EXISTS web_facts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           REAL NOT NULL,
    question     TEXT NOT NULL,
    answer       TEXT NOT NULL,
    sources      TEXT NOT NULL DEFAULT '[]',
    session_id   TEXT,
    model        TEXT,
    provider     TEXT NOT NULL DEFAULT '',
    status       TEXT NOT NULL DEFAULT 'candidate',
    review_note  TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_web_facts_status ON web_facts(status, ts);
CREATE INDEX IF NOT EXISTS idx_web_gaps_resolved ON web_gaps(resolved, ts);
"""


class WebFactStore:
    """SQLite store for model knowledge gaps and web-sourced candidate facts.

    Candidate facts are observations with provenance, not verified training labels. The
    dataset export marks every row ``training_ready: false`` until a human reviews it.
    """

    def __init__(self, path: str = "data/web_facts.db"):
        self.path = str(path)
        self._memory = self.path == ":memory:"
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        if self._memory:
            self._conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_FACTS_SCHEMA)
            if not self._memory:
                conn.execute("PRAGMA journal_mode = WAL")

    @contextlib.contextmanager
    def _connect(self):
        if self._memory:
            with self._lock:
                if self._conn is None:
                    raise RuntimeError("web fact store is closed")
                try:
                    yield self._conn
                    self._conn.commit()
                except BaseException:
                    self._conn.rollback()
                    raise
            return
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @staticmethod
    def _key(question: str) -> str:
        return hashlib.sha256(normalize(question).encode("utf-8")).hexdigest()

    def record_gap(self, question: str, model_answer: str = "", *, session_id: str | None = None,
                   model: str | None = None, reason: str = "model reported uncertainty") -> int:
        question = (question or "").strip()
        if not question:
            raise ValueError("question must be non-empty")
        key = self._key(question)
        now = time.time()
        with self._connect() as conn:
            row = conn.execute("SELECT id FROM web_gaps WHERE question_key = ?", (key,)).fetchone()
            if row is not None:
                conn.execute("""UPDATE web_gaps SET ts=?, model_answer=?, session_id=?, model=?,
                                reason=?, resolved=0 WHERE id=?""",
                             (now, (model_answer or "")[:8000], session_id, model, reason, row["id"]))
                return int(row["id"])
            cursor = conn.execute("""INSERT INTO web_gaps
                (ts, question, question_key, model_answer, session_id, model, reason)
                VALUES (?,?,?,?,?,?,?)""",
                (now, question[:4000], key, (model_answer or "")[:8000], session_id, model, reason))
            return int(cursor.lastrowid)

    def record_fact(self, question: str, answer: str, sources: list[dict], *,
                    session_id: str | None = None, model: str | None = None,
                    provider: str = "", status: str = "candidate") -> int:
        question = (question or "").strip()
        answer = (answer or "").strip()
        if not question or not answer:
            raise ValueError("question and answer must be non-empty")
        if status not in {"candidate", "verified", "rejected"}:
            raise ValueError("status must be candidate, verified or rejected")
        clean_sources = []
        for item in sources or []:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            clean_sources.append({"title": str(item.get("title") or url)[:300], "url": url[:2048],
                                  "snippet": str(item.get("snippet") or "")[:1000]})
        digest = hashlib.sha256(
            f"{self._key(question)}\x1f{normalize(answer)}\x1f"
            f"{json.dumps(clean_sources, sort_keys=True)}".encode("utf-8")).hexdigest()
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute("""INSERT OR IGNORE INTO web_facts
                (ts, question, answer, sources, session_id, model, provider, status, content_hash)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (now, question[:4000], answer[:20000], json.dumps(clean_sources), session_id,
                 model, provider, status, digest))
            row = conn.execute("SELECT id FROM web_facts WHERE content_hash = ?", (digest,)).fetchone()
            fact_id = int(row["id"])
            conn.execute("""UPDATE web_gaps SET resolved=1, fact_id=?
                            WHERE question_key=? AND resolved=0""",
                         (fact_id, self._key(question)))
            return fact_id

    def set_status(self, fact_id: int, status: str, note: str = "") -> None:
        if status not in {"candidate", "verified", "rejected"}:
            raise ValueError("status must be candidate, verified or rejected")
        with self._connect() as conn:
            cursor = conn.execute("UPDATE web_facts SET status=?, review_note=? WHERE id=?",
                                  (status, note[:1000], int(fact_id)))
            if cursor.rowcount != 1:
                raise KeyError(f"web fact {fact_id} not found")

    def stats(self) -> dict:
        with self._connect() as conn:
            facts = conn.execute("SELECT COUNT(*) FROM web_facts").fetchone()[0]
            candidates = conn.execute("SELECT COUNT(*) FROM web_facts WHERE status='candidate'").fetchone()[0]
            verified = conn.execute("SELECT COUNT(*) FROM web_facts WHERE status='verified'").fetchone()[0]
            gaps = conn.execute("SELECT COUNT(*) FROM web_gaps").fetchone()[0]
            open_gaps = conn.execute("SELECT COUNT(*) FROM web_gaps WHERE resolved=0").fetchone()[0]
        return {"facts": int(facts), "candidates": int(candidates), "verified": int(verified),
                "gaps": int(gaps), "open_gaps": int(open_gaps)}

    def list_facts(self, limit: int = 50, status: str | None = None) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            if status:
                rows = conn.execute("SELECT * FROM web_facts WHERE status=? ORDER BY ts DESC LIMIT ?",
                                    (status, limit)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM web_facts ORDER BY ts DESC LIMIT ?",
                                    (limit,)).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["sources"] = json.loads(item.get("sources") or "[]")
            except json.JSONDecodeError:
                item["sources"] = []
            out.append(item)
        return out

    def list_gaps(self, limit: int = 50, unresolved_only: bool = False) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            if unresolved_only:
                rows = conn.execute("SELECT * FROM web_gaps WHERE resolved=0 ORDER BY ts DESC LIMIT ?",
                                    (limit,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM web_gaps ORDER BY ts DESC LIMIT ?",
                                    (limit,)).fetchall()
        return [dict(row) for row in rows]

    def export_dataset(self, out_dir: str | None = None, *,
                       include_rejected: bool = False) -> dict:
        """Write a reviewable JSONL dataset plus a manifest. Returns their paths and counts."""
        folder = Path(out_dir or "data/web_training")
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jsonl = folder / "web_training.jsonl"
        manifest_path = folder / "web_training_manifest.json"
        rows = self.list_facts(limit=10_000)
        exported = []
        for row in rows:
            if row["status"] == "rejected" and not include_rejected:
                continue
            exported.append({
                "id": row["id"],
                "created_at": datetime.fromtimestamp(row["ts"]).astimezone().isoformat(timespec="seconds"),
                "question": row["question"],
                "answer": row["answer"],
                "sources": row["sources"],
                "provider": row["provider"],
                "model": row["model"],
                "session_id": row["session_id"],
                "verification_status": "unverified_web_source",
                "review_status": row["status"],
                "training_ready": False,
                "review_required": True,
            })
        tmp = jsonl.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8", newline="\n") as handle:
            for row in exported:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        tmp.replace(jsonl)
        manifest = {
            "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "format": "ashura-web-candidate-v1",
            "records": len(exported),
            "stats": self.stats(),
            "training_ready": False,
            "review_required": True,
            "warning": ("Web-sourced answers are observations, not verified labels. Review every row "
                        "and add independent verification before any training run."),
            "dataset": jsonl.name,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return {"path": str(jsonl), "manifest": str(manifest_path), "records": len(exported),
                "stamp": stamp, "training_ready": False}
