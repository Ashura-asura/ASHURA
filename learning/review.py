"""Reviewer CLI for the conflict index (P21/F-039).

Contradictory evidence is kept, never silently overwritten. This tool only lists and explicitly
resolves conflicts; superseding an old record still requires an independently verified experience
(the rule is enforced by `AMA.resolve_conflict`).

    python -m learning.review list --db data/ashura.db
    python -m learning.review list --db data/ashura.db --all
    python -m learning.review resolve 3 --db data/ashura.db --reason "reviewed: typo"
    python -m learning.review resolve 3 --db data/ashura.db --reason "new value checked" \
        --verified-exp <experience-id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from learning.ama import AMA
from memory.database import Database


def list_conflicts(db_path: str | Path, *, open_only: bool = True, limit: int = 100) -> list[dict]:
    db = Database(str(db_path))
    try:
        return AMA(db).conflicts(open_only=open_only, limit=limit)
    finally:
        db.close()


def resolve_conflict(db_path: str | Path, conflict_id: int, reason: str,
                     verified_exp: str | None = None) -> dict:
    db = Database(str(db_path))
    try:
        resolved = AMA(db).resolve_conflict(conflict_id, reason, verified_exp_id=verified_exp)
        return {"id": conflict_id, "resolved": resolved,
                "status": ("superseded" if verified_exp else "dismissed") if resolved else None}
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m learning.review",
                                 description="List or explicitly resolve memory conflicts.")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default="data/ashura.db", help="SQLite database path")
    sub = ap.add_subparsers(dest="command", required=True)

    ls = sub.add_parser("list", parents=[common], help="list conflicts (open by default)")
    ls.add_argument("--all", action="store_true", help="include dismissed/superseded conflicts")
    ls.add_argument("--limit", type=int, default=50)

    rs = sub.add_parser("resolve", parents=[common], help="resolve one conflict")
    rs.add_argument("id", type=int)
    rs.add_argument("--reason", required=True, help="why this resolution is justified")
    rs.add_argument("--verified-exp", default=None,
                    help="verified experience id that supersedes the old record")

    args = ap.parse_args(argv)
    try:
        if args.command == "list":
            print(json.dumps(list_conflicts(args.db, open_only=not args.all, limit=args.limit),
                             indent=2))
        else:
            print(json.dumps(resolve_conflict(args.db, args.id, args.reason, args.verified_exp),
                             indent=2))
    except (ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
