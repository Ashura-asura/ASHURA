"""DPF slow plasticity / versioned checkpoints (spec 8.2, 11.1). EXPERIMENTAL training, mandatory gate.

Stable artifacts are only replaced by a candidate that passed NGR. The previous stable artifact is
kept on disk so rollback is a pointer change, not a retrain. This class stores *files*; it does not
know how to train them.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from evaluation.ngr import NGRResult

KINDS = ("stable", "candidates", "experimental")


@dataclass(frozen=True)
class Version:
    name: str
    artifact: str
    promoted_at: str
    reasons: tuple[str, ...] = ()
    parent: str | None = None


class CheckpointStore:
    def __init__(self, root: str | os.PathLike = "checkpoints"):
        self.root = Path(root)
        for kind in KINDS:
            (self.root / kind).mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "manifest.json"
        if not self.manifest.exists():
            self._write({"stable": None, "history": []})

    # ---- manifest ---------------------------------------------------------------------------
    def _write(self, data: dict) -> None:
        tmp = self.manifest.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(self.manifest)

    def _read(self) -> dict:
        return json.loads(self.manifest.read_text())

    def current(self) -> Version | None:
        s = self._read()["stable"]
        return Version(**{**s, "reasons": tuple(s.get("reasons", []))}) if s else None

    def history(self) -> list[Version]:
        return [Version(**{**h, "reasons": tuple(h.get("reasons", []))}) for h in self._read()["history"]]

    # ---- staging / promotion ----------------------------------------------------------------
    def stage(self, artifact: str | os.PathLike, name: str, kind: str = "candidates") -> Path:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        dest = self.root / kind / name
        if dest.exists():
            raise FileExistsError(f"{dest} already exists; refusing to overwrite")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(artifact, dest)
        return dest

    def promote(self, name: str, ngr: NGRResult) -> Path:
        """Copy candidates/name to stable/name only if NGR passed. Never mutates the base model."""
        if not ngr.promote:
            raise PermissionError(f"NGR rejected the candidate: {ngr.reasons}")
        src = self.root / "candidates" / name
        if not src.exists():
            raise FileNotFoundError(src)
        dest = self.root / "stable" / name
        shutil.copy2(src, dest)
        data = self._read()
        prev = data["stable"]
        record = Version(name=name, artifact=f"stable/{name}", promoted_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                         reasons=tuple(ngr.reasons), parent=prev["name"] if prev else None)
        data["history"].append(asdict(record))
        data["stable"] = asdict(record)
        self._write(data)
        return dest

    def rollback(self) -> Version | None:
        """Return the stable pointer to the parent of the current version (artifact kept)."""
        data = self._read()
        current = data["stable"]
        if not current:
            raise RuntimeError("no stable version to roll back")
        parent = current.get("parent")
        if not parent:
            raise RuntimeError("current stable version has no parent")
        parent_record = next((h for h in data["history"] if h["name"] == parent), None)
        if parent_record is None:
            raise RuntimeError(f"parent record {parent!r} missing from manifest")
        data["stable"] = parent_record
        self._write(data)
        return self.current()

    def load(self, version: Version | None = None):
        """Return the artifact path for a version (default: current stable)."""
        v = version or self.current()
        if v is None:
            raise RuntimeError("no stable version")
        path = self.root / v.artifact
        if not path.exists():
            raise FileNotFoundError(path)
        return path
