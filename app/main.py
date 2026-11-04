"""Minimal CLI:  python -m app.main  [--config config/ashura.toml]"""
from __future__ import annotations

import argparse

from brain.controller import Controller
from brain.need_field import NFDConfig, NeedField, Task
from foundation.language_model import build_model
from foundation.model_config import load_config, load_model_config
from learning.ama import AMA, AMAConfig
from memory.database import Database


def build(config_path: str) -> Controller:
    cfg = load_config(config_path)
    db = Database(cfg["memory"]["db_path"])
    ama = AMA(db, AMAConfig.from_dict(cfg.get("ama", {})))
    model = build_model(load_model_config(config_path))
    from brain.controller import default_registry
    nfd = NeedField(default_registry(), NFDConfig.from_dict(cfg.get("nfd", {})))
    return Controller(model, ama=ama, nfd=nfd)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/ashura.toml")
    ap.add_argument("--trace", action="store_true", help="print routing decision for each request")
    args = ap.parse_args()
    try:
        c = build(args.config)
    except Exception as e:      # e.g. Ollama not running, model not installed, digest mismatch
        raise SystemExit(f"could not start ASHURA: {e}")
    print("ASHURA (Ctrl-D to exit)")
    try:
        while True:
            q = input("> ").strip()
            if not q:
                continue
            if q.startswith("/ocr "):
                path = q[5:].strip().strip('"')
                r = c.handle(Task("Read the text in this image.", has_image=True,
                                  image_path=path))
            else:
                r = c.handle(q)
            print(r.text)
            if args.trace:
                print(f"  [route={r.trace.routing['selected']} routing={r.trace.routing_ms:.2f}ms "
                      f"total={r.trace.total_ms:.1f}ms verified={r.verified} ama={r.admission}]")
    except EOFError:
        pass


if __name__ == "__main__":
    main()
