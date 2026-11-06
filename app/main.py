"""Minimal CLI:  python -m app.main  [--config config/ashura.toml] [--trace]

Commands at the prompt:  /ocr <image path>   /help   /quit   (Ctrl-D also exits)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from brain.controller import Controller, default_registry
from brain.need_field import NFDConfig, NeedField, Task
from brain.tools import ToolRegistry
from brain.working_memory import WorkingMemory
from foundation.language_model import build_model
from foundation.model_config import load_config, load_model_config
from learning.ama import AMA, AMAConfig
from learning.runtime import build_learning_worker
from memory.database import Database
from skills.perception import document_info, is_supported
from skills.web import WebConfig, WebFactStore, WebSearch

REPO_ROOT = Path(__file__).resolve().parents[1]
HELP = ("Type a question. Commands: /ocr <image or document path>, /help, /quit")


def resolve_config(path: str) -> Path:
    """A relative config path is tried against the working directory first, then the repository root,
    so `python -m app.main` works from any directory."""
    p = Path(path)
    if p.is_file():
        return p
    alt = REPO_ROOT / path
    if not p.is_absolute() and alt.is_file():
        return alt
    raise FileNotFoundError(f"config file not found: {path} (also tried {alt})")


def build(config_path: str) -> Controller:
    cfg_file = resolve_config(config_path)
    cfg = load_config(cfg_file)
    model_cfg = load_model_config(cfg_file)
    mem = cfg.get("memory", {})
    agent = cfg.get("agent", {}) if isinstance(cfg.get("agent", {}), dict) else {}
    web_section = cfg.get("web", {}) if isinstance(cfg.get("web", {}), dict) else {}
    db = Database(mem.get("db_path", "data/ashura.db"))
    worker = None
    fact_store = None
    try:
        ama = AMA(db, AMAConfig.from_dict(cfg.get("ama", {})))
        model = build_model(model_cfg)
        tools = ToolRegistry(REPO_ROOT) if agent.get("enabled", True) else None
        web = None
        if web_section.get("enabled", False):
            web_config = WebConfig.from_dict(web_section)
            web = WebSearch(web_config)
            fact_store = WebFactStore(web_config.facts_db)
        nfd = NeedField(default_registry(), NFDConfig.from_dict(cfg.get("nfd", {})))
        wm = WorkingMemory(slots=int(mem.get("working_memory_slots", 8)),      # these two keys were ignored before
                           ttl_s=float(mem.get("working_memory_ttl_s", 600)))
        controller = Controller(
            model, ama=ama, nfd=nfd, wm=wm, tools=tools, web=web, fact_store=fact_store,
            max_answer_tokens=agent.get("max_answer_tokens"),
            long_answer_tokens=agent.get("long_answer_tokens"),
            max_continuations=int(agent.get("max_continuations", 2)),
            max_tool_rounds=int(agent.get("max_tool_rounds", 3)),
        )
        worker = build_learning_worker(cfg.get("learning", {}))
        if worker is not None:
            controller.correction_loop = worker
            controller.learning_worker = worker
        return controller
    except Exception:
        if worker is not None:
            worker.close(timeout=1)
        if fact_store is not None:
            fact_store.close()
        db.close()                                                              # don't leak the connection on failure
        raise


def parse_command(line: str) -> Task | str | None:
    """Turn one input line into a Task/str to handle, or None for 'nothing to do'. Raises SystemExit on /quit."""
    if line in {"/quit", "/exit"}:
        raise SystemExit(0)
    if line == "/help":
        print(HELP)
        return None
    if line.startswith("/ocr"):
        path = line[4:].strip().strip('"').strip("'")
        if not path:
            print("usage: /ocr <image or document path>")
            return None
        if not is_supported(path):
            print(f"unsupported file type: {path} "
                  "(images, PDF, DOCX/PPTX, ODT/ODP/ODS, HTML and text/code files are supported)")
            return None
        info = document_info(path)
        if info.kind == "image":
            # The user asked for OCR explicitly, so it must not be deferred because the machine is busy.
            return Task("Read the text in this image.", has_image=True, image_path=path,
                        document_name=Path(path).name, force=("ocr",))
        return Task("Read this document and summarize its key content.",
                    has_document=True, document_path=path,
                    document_name=Path(path).name, force=("documents",))
    return line


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ashura")
    ap.add_argument("--config", default="config/ashura.toml")
    ap.add_argument("--trace", action="store_true", help="print routing decision for each request")
    args = ap.parse_args(argv)
    try:
        c = build(args.config)
    except Exception as e:      # e.g. Ollama not running, model not installed, digest mismatch, bad config
        print(f"could not start ASHURA: {e}", file=sys.stderr)
        return 1
    with c:
        if c.model.name == "echo-stub":
            print("note: the echo stub is configured, so answers only repeat your question. "
                  "Use --config config/ashura.ollama.toml for a real model.", file=sys.stderr)
        print("ASHURA (/help for commands, Ctrl-D to exit)")
        try:
            while True:
                try:
                    q = input("> ").strip()
                except KeyboardInterrupt:
                    print()
                    continue
                if not q:
                    continue
                try:
                    item = parse_command(q)
                    if item is None:
                        continue
                    r = c.handle(item)
                except SystemExit:
                    break
                except Exception as e:  # noqa: BLE001 - one bad request must not kill the session
                    print(f"error: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
                print(r.text)
                if args.trace:
                    print(f"  [route={r.trace.routing['selected']} routing={r.trace.routing_ms:.2f}ms "
                          f"total={r.trace.total_ms:.1f}ms verified={r.verified} ama={r.admission}]")
        except EOFError:
            pass
        finally:
            worker = getattr(c, "learning_worker", None)
            if worker is not None and not worker.close(timeout=5):
                print("warning: a learning job is still running; it will be marked interrupted "
                      "on the next start", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
