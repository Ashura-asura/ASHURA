"""Local OCR adapter with validation, preprocessing, confidence and correction storage.

Tesseract is an optional system dependency (the Python package is ``pytesseract``).
This module never sends images to a network service. OCR text is explicitly marked as
unverified until a user or downstream verifier confirms it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import shutil
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OCRConfig:
    languages: str = "eng"
    psm: int = 6
    preprocess: bool = True
    max_bytes: int = 25 * 1024 * 1024
    min_confidence: float = 0.0
    tesseract_cmd: str | None = None

    def __post_init__(self) -> None:
        if not self.languages.strip():
            raise ValueError("languages must be non-empty")
        if not 0 <= self.psm <= 13:
            raise ValueError("psm must be between 0 and 13")
        if self.max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        if not 0 <= self.min_confidence <= 1:
            raise ValueError("min_confidence must be in [0, 1]")


@dataclass(frozen=True)
class OCRResult:
    ok: bool
    text: str = ""
    confidence: float = 0.0
    engine: str = "tesseract"
    engine_version: str | None = None
    image_ref: str | None = None
    image_sha256: str | None = None
    document_type: str = "document"
    elapsed_ms: float = 0.0
    reason: str | None = None
    verified: bool = False


class OCREngine:
    """Thin, optional local Tesseract wrapper."""

    def __init__(self, config: OCRConfig | None = None):
        self.config = config or OCRConfig()
        self._pytesseract = None
        self._pil = None
        try:
            import pytesseract
            from PIL import Image, ImageOps, ImageFilter
            self._pytesseract = pytesseract
            self._pil = (Image, ImageOps, ImageFilter)
            if self.config.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.config.tesseract_cmd
        except Exception:
            pass

    @property
    def available(self) -> bool:
        if self._pytesseract is None:
            return False
        configured = self.config.tesseract_cmd
        cmd = (shutil.which(configured) or configured) if configured else shutil.which("tesseract")
        return bool(cmd and os.path.isfile(cmd))

    def recognize(self, image_path: str | os.PathLike, *, image_ref: str | None = None,
                  document_type: str = "document") -> OCRResult:
        started = time.perf_counter()
        path = Path(image_path)
        ref = image_ref or str(path)
        try:
            if not path.is_file():
                return self._fail(ref, document_type, started, f"image not found: {path}")
            size = path.stat().st_size
            if size <= 0 or size > self.config.max_bytes:
                return self._fail(ref, document_type, started,
                                  f"image size must be 1..{self.config.max_bytes} bytes")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if not self.available:
                return self._fail(ref, document_type, started,
                                  "local OCR unavailable; install Tesseract and pytesseract",
                                  image_sha256=digest)
            Image, ImageOps, ImageFilter = self._pil
            with Image.open(path) as raw:
                raw.verify()
            with Image.open(path) as raw:
                image = ImageOps.exif_transpose(raw).convert("RGB")
                # Upscale small screenshots/scans before thresholding; cap growth to avoid
                # pathological RAM use on tiny images.
                if max(image.size) < 1400:
                    scale = min(3, max(1, int(1400 / max(image.size))))
                    if scale > 1:
                        image = image.resize((image.width * scale, image.height * scale), Image.Resampling.LANCZOS)
                if self.config.preprocess:
                    image = ImageOps.grayscale(image)
                    image = ImageOps.autocontrast(image)
                    image = image.filter(ImageFilter.MedianFilter(size=3))
                data = self._pytesseract.image_to_data(
                    image, lang=self.config.languages,
                    config=f"--psm {self.config.psm}",
                    output_type=self._pytesseract.Output.DICT)
                words, confidences = [], []
                for word, raw_conf in zip(data.get("text", []), data.get("conf", [])):
                    word = str(word).strip()
                    try:
                        conf = float(raw_conf)
                    except (TypeError, ValueError):
                        continue
                    if word and conf >= 0:
                        words.append(word)
                        confidences.append(conf / 100.0)
                text = " ".join(words).strip()
                confidence = sum(confidences) / len(confidences) if confidences else 0.0
                version = str(self._pytesseract.get_tesseract_version()).splitlines()[0]
            if not text:
                return self._fail(ref, document_type, started, "OCR returned no text",
                                 image_sha256=digest, engine_version=version)
            if confidence < self.config.min_confidence:
                return self._fail(ref, document_type, started,
                                  f"confidence {confidence:.3f} below configured minimum",
                                  image_sha256=digest, engine_version=version, text=text,
                                  confidence=confidence)
            return OCRResult(True, text, confidence, "tesseract", version, ref, digest,
                             document_type, (time.perf_counter() - started) * 1000,
                             verified=False)
        except Exception as exc:
            return self._fail(ref, document_type, started, f"OCR failed: {exc}")

    def _fail(self, ref: str, document_type: str, started: float, reason: str,
              **kwargs: Any) -> OCRResult:
        return OCRResult(False, elapsed_ms=(time.perf_counter() - started) * 1000,
                         image_ref=ref, document_type=document_type, reason=reason, **kwargs)


def ocr_file(image_path: str | os.PathLike, *, image_ref: str | None = None,
             document_type: str = "document", config: OCRConfig | None = None) -> OCRResult:
    """Convenience function used by the ASHURA controller."""
    return OCREngine(config).recognize(image_path, image_ref=image_ref,
                                       document_type=document_type)


class OCRCorrectionStore:
    """Persist OCR observations and user corrections in a local SQLite file.

    Stored output remains an OCR observation, not an automatic training label.
    A correction is marked verified only when explicitly supplied by a user.
    """
    def __init__(self, db_path: str | os.PathLike | sqlite3.Connection):
        self._shared_connection = db_path if isinstance(db_path, sqlite3.Connection) else None
        self.db_path = str(db_path) if self._shared_connection is None else ":shared-connection:"
        if self._shared_connection is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS ocr_records (
                id INTEGER PRIMARY KEY, image_ref TEXT, image_sha256 TEXT,
                extracted_text TEXT NOT NULL, confidence REAL NOT NULL,
                engine TEXT NOT NULL, engine_version TEXT, document_type TEXT,
                correction TEXT, correction_verified INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS idx_ocr_hash ON ocr_records(image_sha256)")

    def _connect(self):
        return self._shared_connection if self._shared_connection is not None else sqlite3.connect(self.db_path)

    def add(self, result: OCRResult) -> int:
        with self._connect() as db:
            cur = db.execute("""INSERT INTO ocr_records
                (image_ref,image_sha256,extracted_text,confidence,engine,engine_version,
                 document_type,created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (result.image_ref, result.image_sha256, result.text, result.confidence,
                 result.engine, result.engine_version, result.document_type, time.time()))
            return int(cur.lastrowid)

    def correct(self, record_id: int, corrected_text: str, *, user_verified: bool = True) -> None:
        corrected_text = corrected_text.strip()
        if not corrected_text:
            raise ValueError("corrected_text must be non-empty")
        with self._connect() as db:
            cur = db.execute("UPDATE ocr_records SET correction=?, correction_verified=? WHERE id=?",
                             (corrected_text, int(user_verified), int(record_id)))
            if cur.rowcount != 1:
                raise KeyError(f"OCR record {record_id} not found")

    def get(self, record_id: int) -> dict | None:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM ocr_records WHERE id=?", (int(record_id),)).fetchone()
            return dict(row) if row else None

    def verified_corrections(self, limit: int = 1000) -> list[dict]:
        with self._connect() as db:
            db.row_factory = sqlite3.Row
            rows = db.execute("SELECT * FROM ocr_records WHERE correction_verified=1 "
                              "ORDER BY id DESC LIMIT ?", (max(0, int(limit)),)).fetchall()
            return [dict(r) for r in rows]
