"""DPF slow plasticity / versioned checkpoints (spec 8.2, 11.1). EXPERIMENTAL training, mandatory gate.

Stable artifacts are only replaced by a candidate that passed NGR. The previous stable artifact is
kept on disk so rollback is a pointer change, not a retrain. This class stores *files*; it does not
know how to train them.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
import tempfile
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


def _check_name(name: str) -> str:
    """Artifact names are plain file names: no directories, no traversal."""
    if not name or name in {".", ".."} or Path(name).name != name or "\\" in name or "/" in name:
        raise ValueError(f"invalid checkpoint name {name!r}: must be a plain file name")
    return name


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
        fd, tmp_name = tempfile.mkstemp(prefix=f".{self.manifest.name}.", suffix=".tmp",
                                       dir=self.manifest.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(data, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp_name, self.manifest)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    @staticmethod
    def _atomic_copy(source: Path, destination: Path) -> None:
        """Copy an artifact to a unique same-directory temp file, then atomically publish it."""
        fd, tmp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp",
                                       dir=destination.parent)
        os.close(fd)
        try:
            shutil.copy2(source, tmp_name)
            os.replace(tmp_name, destination)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _read(self) -> dict:
        try:
            return json.loads(self.manifest.read_text())
        except (OSError, ValueError) as e:
            raise RuntimeError(f"checkpoint manifest {self.manifest} is unreadable or corrupt: {e}") from e

    def current(self) -> Version | None:
        s = self._read()["stable"]
        return Version(**{**s, "reasons": tuple(s.get("reasons", []))}) if s else None

    def history(self) -> list[Version]:
        return [Version(**{**h, "reasons": tuple(h.get("reasons", []))}) for h in self._read()["history"]]

    # ---- staging / promotion ----------------------------------------------------------------
    def stage(self, artifact: str | os.PathLike, name: str, kind: str = "candidates") -> Path:
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        dest = self.root / kind / _check_name(name)
        if dest.exists():
            raise FileExistsError(f"{dest} already exists; refusing to overwrite")
        dest.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_copy(Path(artifact), dest)
        return dest

    def promote(self, name: str, ngr: NGRResult) -> Path:
        """Copy candidates/name to stable/name only if NGR passed. Never mutates the base model."""
        if not ngr.promote:
            raise PermissionError(f"NGR rejected the candidate: {ngr.reasons}")
        src = self.root / "candidates" / _check_name(name)
        if not src.exists():
            raise FileNotFoundError(src)
        dest = self.root / "stable" / name
        if dest.exists() and not filecmp.cmp(src, dest, shallow=False):
            raise FileExistsError(f"{dest} already exists with different content; refusing to overwrite a stable artifact")
        self._atomic_copy(src, dest)                    # a crash can never leave a half-copied stable file
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
