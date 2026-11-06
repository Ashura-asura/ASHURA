"""Playwright smoke for the ASHURA workbench.

Runs the real HTTP server against an in-memory controller and drives Chromium.
No external network access, no real model weights.

Usage:
    python tests/browser/smoke.py            # behavior + screenshot comparison
    python tests/browser/smoke.py --update   # regenerate baselines

Screenshot baselines are Windows Chromium renders. CI runs with --no-snapshots
because font rasterization differs between operating systems.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time as real_time
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from playwright.sync_api import expect, sync_playwright  # noqa: E402

import app.sessions as sessions_module  # noqa: E402
import app.web as web_module  # noqa: E402
import app.worker as worker_module  # noqa: E402
import brain.controller as controller_module  # noqa: E402
import learning.ama as ama_module  # noqa: E402
import memory.episodic as episodic_module  # noqa: E402
import memory.semantic as semantic_module  # noqa: E402
from app.sessions import SessionStore  # noqa: E402
from app.web import AppHTTPServer, WebApp  # noqa: E402
from brain.controller import Controller  # noqa: E402
from foundation.language_model import EchoModel  # noqa: E402
from learning.ama import AMA  # noqa: E402
from memory.database import Database  # noqa: E402

TOKEN = "browser-token"
WIDTHS = (320, 375, 430, 768, 1024, 1440, 1920)
BASELINES = ROOT / "design" / "ui-baselines"
# Screenshot runs must not embed the wall clock, durations, or "just now" labels.
FIXED_EPOCH = 1_767_268_800.0  # 2026-01-01T12:00:00Z
FIXED_MS = int(FIXED_EPOCH * 1000)


class FrozenTime:
    """Stand-in for the stdlib time module that returns fixed readings."""

    def time(self) -> float:
        return FIXED_EPOCH

    def monotonic(self) -> float:
        return 1_000.0

    def perf_counter(self) -> float:
        return 1_000.0

    def __getattr__(self, name: str):
        return getattr(real_time, name)


class DeterministicUUID:
    """Stable, unique IDs so record IDs do not churn between screenshot runs."""

    def __init__(self) -> None:
        self._counter = 0

    def uuid4(self):
        self._counter += 1
        return types.SimpleNamespace(hex=f"{self._counter:08x}" + "0" * 24)


def freeze_server_time() -> None:
    """Patch only the modules that stamp sessions, traces and memory records."""
    frozen = FrozenTime()
    for module in (
        sessions_module,
        web_module,
        controller_module,
        ama_module,
        episodic_module,
        semantic_module,
    ):
        module.time = frozen
    ids = DeterministicUUID()
    for module in (sessions_module, worker_module, episodic_module, semantic_module):
        module.uuid = ids


def build_server() -> tuple[AppHTTPServer, WebApp, threading.Thread]:
    freeze_server_time()
    app = WebApp(
        Controller(EchoModel(), ama=AMA(Database(":memory:"))),
        "config/ashura.toml",
        sessions=SessionStore(":memory:"),
        token=TOKEN,
        csrf="browser-csrf",
    )
    httpd = AppHTTPServer(("127.0.0.1", 0), app)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, app, thread


def chromium_path() -> str | None:
    base = Path.home() / "AppData" / "Local" / "ms-playwright"
    candidates = sorted(base.glob("chromium-*/chrome-win64/chrome.exe"))
    return str(candidates[-1]) if candidates else None


class Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.console_errors: list[str] = []

    def check(self, condition: bool, message: str) -> None:
        if condition:
            print(f"  ok  {message}")
        else:
            self.failures.append(message)
            print(f"  FAIL {message}")

    def watch(self, page) -> None:
        def on_console(message):
            if message.type != "error":
                return
            text = message.text
            # The pre-auth status probe is expected to log a 401 in Chromium.
            if "Failed to load resource" in text and "401" in text:
                return
            self.console_errors.append(text)

        page.on("console", on_console)
        page.on("pageerror", lambda error: self.console_errors.append(str(error)))

        def on_failed(request):
            failure = request.failure or ""
            # The reader is deliberately cancelled once the SSE "done" frame arrives.
            if "/api/chat/stream" in request.url and "ERR_ABORTED" in failure:
                return
            self.console_errors.append(f"request failed: {request.url} {failure}")

        page.on("requestfailed", on_failed)


def wait_authenticated(page) -> None:
    expect(page.locator("#unlock-dialog")).not_to_be_visible()
    expect(page.locator("#status-health")).to_contain_text("reachable", timeout=10_000)


def login(page) -> None:
    expect(page.locator("#unlock-dialog")).to_be_visible(timeout=10_000)
    page.fill("#unlock-token", TOKEN)
    page.click("#unlock-submit")
    wait_authenticated(page)


def overflow(page) -> int:
    return page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )


def set_theme(page, value: str) -> None:
    page.locator(f'label.radio-card:has(input[name="theme"][value="{value}"])').click()


def screenshot(page, name: str, update: bool) -> None:
    BASELINES.mkdir(parents=True, exist_ok=True)
    target = BASELINES / f"{name}.png"
    # Transient toasts are not part of the layout under test.
    page.evaluate("() => { const t = document.getElementById('toast'); if (t) t.hidden = true; }")
    # The test server binds an ephemeral port; mask it without changing text width.
    page.evaluate(
        """() => {
            const host = window.location.host;
            if (!host) return;
            const mask = host.replace(/\\d+$/, (digits) => "0".repeat(digits.length));
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const node = walker.currentNode;
                if (node.nodeValue && node.nodeValue.includes(host)) {
                    node.nodeValue = node.nodeValue.split(host).join(mask);
                }
            }
        }"""
    )
    if update:
        page.screenshot(path=str(target))
        return
    if target.exists():
        page.screenshot(path=str(target.with_suffix(".actual.png")))
        try:
            from PIL import Image, ImageChops
        except ImportError:
            print("  skip screenshot (Pillow unavailable)")
            return
        actual = Image.open(target.with_suffix(".actual.png")).convert("RGB")
        baseline = Image.open(target).convert("RGB")
        if actual.size != baseline.size:
            print(f"  FAIL screenshot size changed: {name}")
            return
        diff = ImageChops.difference(actual, baseline)
        changed = sum(1 for pixel in diff.getdata() if max(pixel) > 12)
        ratio = changed / max(1, actual.size[0] * actual.size[1])
        print(f"  {'ok' if ratio < 0.002 else 'FAIL'} screenshot {name} ({ratio:.4%})")
        if ratio >= 0.002:
            raise SystemExit(f"screenshot mismatch: {name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--no-snapshots", action="store_true")
    args = parser.parse_args()

    checker = Checker()
    httpd, app, thread = build_server()
    base = f"http://127.0.0.1:{httpd.server_port}/"
    try:
        with sync_playwright() as playwright:
            launch = {"headless": True}
            executable = chromium_path()
            if executable:
                launch["executable_path"] = executable
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(viewport={"width": 1440, "height": 900},
                                           reduced_motion="reduce")
            page = context.new_page()
            # Freeze client-side "now" so status timestamps and relative ages are stable.
            page.add_init_script(f"Date.now = () => {FIXED_MS};")
            checker.watch(page)
            page.goto(base)
            login(page)
            checker.check("echo-stub" in page.inner_text("#status-model"), "model name is reported")
            checker.check("Server: reachable" in page.inner_text("#status-health"), "health is reachable")
            checker.check("readiness" in page.get_attribute("#runtime-model", "title").lower(),
                          "model readiness caveat is present")

            print("command center")
            expect(page.locator("#empty-state")).to_be_visible()
            page.fill("#message", "hello browser")
            page.click("#send")
            expect(page.locator(".msg.assistant .bubble").last).to_contain_text(
                "[echo] hello browser", timeout=20_000
            )
            expect(page.locator("#send")).to_be_enabled(timeout=20_000)
            expect(page.locator(".session-row").first).to_be_visible(timeout=10_000)
            checker.check(page.locator(".msg.user").count() == 1, "user turn rendered")
            checker.check(page.locator(".msg-trace button").count() >= 1, "trace action rendered")
            answer_size = page.locator(".msg.assistant .bubble").last.evaluate(
                "element => getComputedStyle(element).fontSize")
            checker.check(answer_size == "16px", "assistant answer text is readable at 16px")

            print("desktop command center controls")
            sessions_toggle = page.locator("#sessions-toggle")
            checker.check(sessions_toggle.is_visible(), "desktop sessions toggle is visible")
            sessions_toggle.click()
            expect(page.locator("#session-pane")).to_be_hidden()
            checker.check(sessions_toggle.get_attribute("aria-expanded") == "false",
                          "hidden sessions state is announced accessibly")
            page.reload()
            wait_authenticated(page)
            expect(page.locator("#session-pane")).to_be_hidden()
            checker.check(sessions_toggle.get_attribute("aria-label") == "Show sessions",
                          "hidden sessions preference survives reload")
            sessions_toggle.click()
            expect(page.locator("#session-pane")).to_be_visible()
            checker.check(sessions_toggle.get_attribute("aria-expanded") == "true",
                          "sessions pane can be restored")

            print("rich rendering")
            rendered = page.evaluate(r"""async () => {
                const { renderMarkdown } = await import('/static/js/components.js');
                const source = [
                    String.raw`Inline $E=mc^2$ math.`,
                    '',
                    String.raw`$$\frac{a}{b}$$`,
                    '',
                    '| Name | Value |',
                    '| --- | ---: |',
                    '| alpha | 1 |',
                    '',
                    String.raw`$\undefinedmacro{x}$`,
                ].join(String.fromCharCode(10));
                return renderMarkdown(source);
            }""")
            checker.check("<math" in rendered and "<msup>" in rendered,
                          "inline LaTeX renders as MathML")
            checker.check('<div class="math-display">' in rendered and "<mfrac>" in rendered,
                          "display LaTeX renders as block MathML")
            checker.check("<table>" in rendered and '<th class="align-right">Value</th>' in rendered,
                          "markdown tables render with alignment")
            checker.check("math-unrendered" in rendered,
                          "unsupported LaTeX falls back to visible source")
            checker.check("<img" not in rendered, "math source cannot inject HTML")

            print("documents, tools and source evidence")
            fixture = app.sessions.create("Evidence fixture")
            app.sessions.append(fixture["id"], "user", "Inspect this workspace file")
            app.sessions.append(fixture["id"], "assistant", "Evidence answer", meta={
                "kind": "chat",
                "model": "echo-stub",
                "verified": False,
                "verification": {"status": "unavailable", "reason": "no independent check"},
                "admission": None,
                "attribution": None,
                "correction": None,
                "trace": None,
                "sources": [{"title": "Example source", "url": "https://example.com/source",
                             "snippet": "External snippet", "provider": "duckduckgo"}],
                "tool_calls": [{"name": "list_files", "ok": True, "elapsed_ms": 2.5,
                                "args": {"path": "."}, "error": None}],
                "document": {"name": "notes.txt", "kind": "text", "ok": True,
                             "pages": 1, "engine": "local text", "truncated": False},
                "web": {"enabled": True, "queried": True, "sources": [], "errors": []},
                "truncated": True,
            })
            page.reload()
            wait_authenticated(page)
            page.locator(".session-row", has_text="Evidence fixture").first.click()
            expect(page.locator(".document-card")).to_contain_text("notes.txt")
            expect(page.locator(".tool-details")).to_contain_text("Tool observations · 1")
            expect(page.locator(".source-details")).to_contain_text("Web sources · 1")
            expect(page.locator(".evidence-warning")).to_contain_text("token limit")
            expect(page.locator(".msg-meta").last).to_contain_text("Truncated")
            expect(page.locator(".msg-meta").last).to_contain_text("1 web source")
            checker.check("External pages are untrusted evidence"
                          in page.locator(".source-details").last.evaluate("el => el.textContent"),
                          "web sources are labelled untrusted evidence")

            existing_document_cards = page.locator(".document-card").count()
            page.set_input_files("#ocr-file", {
                "name": "smoke-notes.txt",
                "mimeType": "text/plain",
                "buffer": b"Local smoke document content.",
            })
            expect(page.locator("#attachment-preview")).to_contain_text("smoke-notes.txt")
            expect(page.locator(".document-card")).to_have_count(existing_document_cards)
            page.locator("#message").fill("Extract the note text exactly.")
            page.locator("#send").click()
            expect(page.locator(".document-card").last).to_contain_text("smoke-notes.txt")
            expect(page.locator(".msg.assistant .bubble").last).to_contain_text(
                "[echo]", timeout=20_000)
            expect(page.locator("#send")).to_be_enabled(timeout=20_000)
            checker.check("Local extraction; content is not independently verified."
                          in page.inner_text(".document-card").lower()
                          or "not independently verified" in page.inner_text(".document-card").lower(),
                          "document extraction is labelled unverified")
            checker.check("Document turn" in page.locator(".msg-meta").last.inner_text(),
                          "document turn badge rendered")
            app.sessions.delete(fixture["id"])
            page.reload()
            wait_authenticated(page)
            page.locator(".session-row", has_text="hello browser").first.click()
            expect(page.locator(".msg.assistant .bubble").last).to_contain_text("[echo] hello browser")

            page.locator('[data-message-action="inspect"]').last.click()
            expect(page.locator("#panel-summary")).to_contain_text("Turn facts")
            expect(page.locator("#panel-summary")).to_contain_text("Not verified")
            page.click("#tab-trace")
            expect(page.locator("#panel-trace")).to_contain_text("Steps")
            checker.check(page.locator("#tab-trace").get_attribute("aria-selected") == "true",
                          "trace tab is selected")

            print("execution studio")
            page.click('.rail-link[data-route="execution"]')
            expect(page.locator(".execution-view")).to_be_visible()
            expect(page.locator(".operation-row").first).to_be_visible(timeout=10_000)
            page.locator(".operation-row").first.click()
            expect(page.locator("#timeline")).to_contain_text("Selected")
            checker.check("completed" in page.inner_text(".timeline-note").lower(),
                          "completed-turn provenance note is shown")

            print("knowledge studio")
            page.click('.rail-link[data-route="knowledge"]')
            expect(page.locator(".knowledge-view")).to_be_visible()
            expect(page.locator(".memory-row").first).to_be_visible(timeout=10_000)
            page.locator(".memory-row").first.click()
            expect(page.locator("#memory-detail")).to_contain_text("Provenance")
            checker.check("not exposed" in page.inner_text("#memory-detail").lower(),
                          "unavailable conflict detail is labelled")

            print("system monitor")
            page.click('.rail-link[data-route="system"]')
            expect(page.locator(".system-view")).to_be_visible()
            checker.check("Not measured by this build" in page.inner_text("#system-body"),
                          "absent metrics are explicit")
            checker.check("Not available" in page.inner_text("#system-body"),
                          "unavailable values are not zeros")
            expect(page.locator("#system-refresh")).to_be_visible()

            print("settings and security")
            page.click('.rail-link[data-route="settings"]')
            expect(page.locator(".settings-view")).to_be_visible()
            expect(page.locator("#settings-session-status")).to_contain_text("Unlocked")
            expect(page.locator("#settings-model-body")).to_contain_text("Model switching is unavailable")
            checker.check("ollama" in page.inner_text("#settings-model-body").lower(),
                          "non-Ollama model switch is labelled unavailable")
            expect(page.locator("#settings-web-body")).to_contain_text("Web research is disabled")
            checker.check("connect-src 'self'" in page.inner_text("#settings-web-body"),
                          "web panel states the browser stays on this origin")
            checker.check("No encryption at rest" in page.inner_text(".settings-view"),
                          "plaintext storage limit is stated")
            checker.check("not rotated" in page.inner_text(".settings-view"),
                          "token rotation limit is stated")

            print("themes")
            page.click("#theme-toggle")
            first = page.get_attribute("html", "data-theme")
            page.click("#theme-toggle")
            second = page.get_attribute("html", "data-theme")
            checker.check(first != second and second in {"dark", "light"}, "theme toggle changes theme")
            set_theme(page, "light")
            checker.check(page.get_attribute("html", "data-theme") == "light", "light preference applies")
            set_theme(page, "dark")
            checker.check(page.get_attribute("html", "data-theme") == "dark", "dark preference applies")

            print("logout and persistence")
            page.click("#logout-button")
            expect(page.locator("#unlock-dialog")).to_be_visible()
            page.keyboard.press("Escape")
            checker.check(page.locator("#unlock-dialog").is_visible(),
                          "locked gate cannot be dismissed with Escape")
            login(page)
            page.click('.rail-link[data-route="command"]')
            expect(page.locator(".session-row").first).to_be_visible(timeout=10_000)
            expect(page.locator("#transcript")).to_contain_text("[echo] hello browser")
            checker.check(page.locator("#session-list").inner_text().count("hello") >= 1,
                          "session persisted across logout")

            print("responsive widths")
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(120)
                page.click('.rail-link[data-route="command"]') if width >= 861 else page.evaluate(
                    "() => { window.location.hash = '#/command'; }"
                )
                page.wait_for_timeout(80)
                spills = overflow(page)
                checker.check(spills <= 1, f"no horizontal overflow at {width}px ({spills}px)")
                checker.check(page.locator("#composer").is_visible(), f"composer visible at {width}px")
                if not args.no_snapshots:
                    screenshot(page, f"layout-{width}", args.update)
            page.set_viewport_size({"width": 1440, "height": 900})

            print("mobile drawers")
            page.set_viewport_size({"width": 375, "height": 812})
            page.wait_for_timeout(100)
            page.click("#sessions-toggle")
            checker.check(page.locator("body").evaluate("el => el.classList.contains('sessions-open')"),
                          "session drawer opens at 375px")
            page.click("#sessions-close")
            page.click("#inspector-toggle")
            checker.check(page.locator("body").evaluate("el => el.classList.contains('inspector-open')"),
                          "inspector drawer opens at 375px")
            page.click("#inspector-close")

            page.evaluate("() => { window.location.hash = '#/execution'; }")
            expect(page.locator(".execution-view")).to_be_visible()
            page.click("#operations-toggle")
            checker.check(page.locator("body").evaluate("el => el.classList.contains('operations-open')"),
                          "operations drawer opens at 375px")
            page.click("#operations-close")
            page.click("#evidence-toggle")
            checker.check(page.locator("body").evaluate("el => el.classList.contains('evidence-open')"),
                          "evidence drawer opens at 375px")
            page.click("#evidence-close")

            page.evaluate("() => { window.location.hash = '#/knowledge'; }")
            expect(page.locator(".knowledge-view")).to_be_visible()
            page.click("#memory-toggle")
            checker.check(page.locator("body").evaluate("el => el.classList.contains('memory-open')"),
                          "memory drawer opens at 375px")
            page.click("#memory-close")
            page.evaluate("() => { window.location.hash = '#/command'; }")
            expect(page.locator(".command-view")).to_be_visible()

            print("keyboard and palette")
            page.set_viewport_size({"width": 1440, "height": 900})
            palette = page.locator("#palette-dialog")
            page.click("#palette-trigger")
            expect(palette).to_be_visible()
            expect(palette.locator("#palette-close")).to_be_visible()
            box = palette.bounding_box()
            checker.check(box is not None and box["y"] < 160,
                          "command palette is anchored near the top")
            checker.check(box is not None and box["width"] > 500,
                          "command palette uses the wide command-bar layout")
            page.click("#palette-close")
            checker.check(not palette.is_visible(), "palette close control dismisses the palette")
            page.keyboard.press("Control+k")
            expect(palette).to_be_visible()
            page.mouse.click(8, 300)
            checker.check(not palette.is_visible(), "palette backdrop click dismisses the palette")
            page.keyboard.press("Control+k")
            expect(palette).to_be_visible()
            page.fill("#palette-input", "system")
            expect(page.locator(".palette-item").first).to_contain_text("System Monitor")
            page.keyboard.press("Enter")
            expect(page.locator(".system-view")).to_be_visible()
            page.keyboard.press("Alt+1")
            expect(page.locator(".command-view")).to_be_visible()
            checker.check(page.locator("#unlock-token").count() == 1, "unlock field is programmatically labelled")

            print("workspace screenshots")
            if not args.no_snapshots:
                for route, selector in (
                    ("command", ".command-view"),
                    ("execution", ".execution-view"),
                    ("knowledge", ".knowledge-view"),
                    ("system", ".system-view"),
                    ("settings", ".settings-view"),
                ):
                    page.evaluate(f"() => {{ window.location.hash = '#/{route}'; }}")
                    expect(page.locator(selector)).to_be_visible()
                    if route == "execution":
                        expect(page.locator(".operation-row").first).to_be_visible(timeout=10_000)
                    if route == "knowledge":
                        expect(page.locator(".memory-row").first).to_be_visible(timeout=10_000)
                        page.locator(".memory-row").first.click()
                    page.wait_for_timeout(150)
                    screenshot(page, f"{route}-1440", args.update)
                    page.set_viewport_size({"width": 375, "height": 812})
                    page.wait_for_timeout(100)
                    screenshot(page, f"{route}-mobile-375", args.update)
                    page.set_viewport_size({"width": 1440, "height": 900})

                page.evaluate("() => { window.location.hash = '#/settings'; }")
                expect(page.locator(".settings-view")).to_be_visible()
                set_theme(page, "light")
                page.wait_for_timeout(100)
                screenshot(page, "settings-light-1440", args.update)
                page.evaluate("() => { window.location.hash = '#/command'; }")
                expect(page.locator(".command-view")).to_be_visible()
                screenshot(page, "command-light-1440", args.update)
                page.evaluate("() => { window.location.hash = '#/settings'; }")
                set_theme(page, "dark")

            browser.close()
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)
        app.close()

    if checker.console_errors:
        print("\nconsole/page errors:")
        for error in checker.console_errors:
            print(f"  - {error}")
    checker.check(not checker.console_errors, "no console, page or request errors")
    if checker.failures:
        print(f"\n{len(checker.failures)} browser checks failed")
        return 1
    print("\nall browser checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
