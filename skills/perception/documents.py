"""Local document intake for the console.

Images go through the optional Tesseract OCR engine. PDFs use the optional ``pypdf``
text layer (and, when available, PyMuPDF renders scanned pages for OCR). Office and
OpenDocument files are read with the standard library only: they are ZIP containers
with XML parts, so no converter or network service is involved.

Everything here is local, bounded and best-effort. A failed extraction returns an
explicit reason; it never fabricates text. Extracted text is an observation, not a
verified fact.
"""
from __future__ import annotations

import html
import os
import re
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from .ocr import OCRConfig, OCREngine, OCRResult, ocr_file

MAX_EXTRACT_CHARS = 80_000
MAX_PAGES = 200
MAX_ARCHIVE_MEMBER = 24 * 1024 * 1024
MAX_ARCHIVE_TOTAL = 96 * 1024 * 1024

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
TEXT_SUFFIXES = {
    ".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl",
    ".log", ".ini", ".cfg", ".conf", ".toml", ".yaml", ".yml", ".xml", ".html", ".htm",
    ".css", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".py", ".java", ".c", ".h", ".cpp",
    ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".sh", ".ps1", ".sql", ".tex", ".bib",
}
ZIP_SUFFIXES = {".docx", ".pptx", ".odt", ".odp", ".ods"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | TEXT_SUFFIXES | ZIP_SUFFIXES | {".pdf"}

_MIME_FOR_SUFFIX = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".odp": "application/vnd.oasis.opendocument.presentation",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
}
_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".webp": (b"RIFF",),
}


@dataclass(frozen=True)
class DocumentInfo:
    suffix: str
    kind: str
    mime: str | None = None


def document_info(filename: str) -> DocumentInfo:
    suffix = Path(filename or "").suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        kind = "image"
    elif suffix == ".pdf":
        kind = "pdf"
    elif suffix in ZIP_SUFFIXES:
        kind = "office"
    elif suffix in TEXT_SUFFIXES:
        kind = "text"
    else:
        kind = "unsupported"
    return DocumentInfo(suffix, kind, _MIME_FOR_SUFFIX.get(suffix))


def is_supported(filename: str) -> bool:
    return document_info(filename).kind != "unsupported"


def _fail(ref: str, suffix: str, kind: str, reason: str, started: float) -> OCRResult:
    import time
    return OCRResult(False, image_ref=ref, document_type=kind or "document",
                     elapsed_ms=(time.perf_counter() - started) * 1000, reason=reason,
                     meta={"suffix": suffix})


def _finish(ref: str, suffix: str, kind: str, text: str, engine: str, started: float,
            *, pages: int = 0, truncated: bool = False, version: str | None = None,
            confidence: float = 0.0) -> OCRResult:
    import time
    text = text.strip()
    if not text:
        return _fail(ref, suffix, kind, "no extractable text found", started)
    return OCRResult(
        True, text=text, confidence=confidence, engine=engine, engine_version=version,
        image_ref=ref, document_type=kind, elapsed_ms=(time.perf_counter() - started) * 1000,
        verified=False, pages=pages, truncated=truncated,
        meta={"suffix": suffix},
    )


def _read_bounded(path: Path) -> bytes:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("file is empty")
    if size > MAX_ARCHIVE_MEMBER:
        raise ValueError(f"file is larger than {MAX_ARCHIVE_MEMBER // (1024 * 1024)} MB")
    return path.read_bytes()


def _validate_magic(path: Path, info: DocumentInfo) -> None:
    if info.kind == "image":
        prefix = path.read_bytes()[:16]
        allowed = _MAGIC.get(info.suffix, ())
        if allowed and not any(prefix.startswith(magic) for magic in allowed):
            raise ValueError("file content does not match the image extension")
    elif info.kind == "pdf":
        if not path.read_bytes()[:5].startswith(b"%PDF-"):
            raise ValueError("file content does not match the .pdf extension")
    elif info.kind == "office":
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
        expected = {
            ".docx": "word/document.xml",
            ".pptx": "ppt/",
            ".odt": "content.xml",
            ".odp": "content.xml",
            ".ods": "content.xml",
        }[info.suffix]
        if not any(name == expected or name.startswith(expected) for name in names):
            raise ValueError("archive content does not match the file extension")
    elif info.kind == "text":
        data = path.read_bytes()[:4096]
        if b"\x00" in data:
            raise ValueError("file looks binary, not text")


# ---- text -----------------------------------------------------------------------------------

def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


class _TextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.skip = 0
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "template"}:
            self.skip += 1
        elif tag == "title":
            self.in_title = True
        elif tag in {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "template"} and self.skip:
            self.skip -= 1
        elif tag == "title":
            self.in_title = False
        elif tag in {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        elif not self.skip:
            self.parts.append(data)


def html_to_text(source: str) -> tuple[str, str | None]:
    """Return readable text and the document title from a local HTML string."""
    parser = _TextHTMLParser()
    parser.feed(source)
    text = html.unescape("".join(parser.parts))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    title = html.unescape("".join(parser.title_parts)).strip() or None
    return text.strip(), title


# ---- archive/XML helpers --------------------------------------------------------------------

def _safe_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in archive.infolist():
        if info.is_dir():
            continue
        total += info.file_size
        if info.file_size > MAX_ARCHIVE_MEMBER or total > MAX_ARCHIVE_TOTAL:
            raise ValueError("archive expands beyond the local extraction limit")
        members[info.filename] = info
    return members


def _xml_text(data: bytes, *, word: bool = False) -> str:
    root = ElementTree.fromstring(data)
    parts: list[str] = []
    for node in root.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag in {"tab"}:
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append("\n")
        elif tag == "p":
            parts.append("\n")
            # OpenDocument puts text directly inside text:p (and text:span), unlike
            # DOCX where it lives in w:t. Collect it without duplicating w:t content.
            if node.text:
                parts.append(node.text)
        elif tag in {"span", "h", "a"} and node.text:
            parts.append(node.text)
        elif tag == "tr":
            parts.append("\n")
    text = "".join(parts)
    if word:
        text = text.replace("\n\n", "\n")
    return text


def _extract_docx(path: Path, ref: str, started: float) -> OCRResult:
    with zipfile.ZipFile(path) as archive:
        members = _safe_members(archive)
        parts = ["word/document.xml"]
        parts += sorted(name for name in members
                        if name.startswith("word/header") or name.startswith("word/footer"))
        text = []
        for name in parts:
            info = members.get(name)
            if info is None:
                continue
            text.append(_xml_text(archive.read(info), word=True))
        try:
            import docx  # type: ignore
            version = getattr(docx, "__version__", None)
        except Exception:  # noqa: BLE001 - optional
            version = "stdlib-xml"
    return _finish(ref, ".docx", "document", "\n".join(text), "python-docx/stdlib-xml",
                   started, version=version)


def _extract_pptx(path: Path, ref: str, started: float) -> OCRResult:
    with zipfile.ZipFile(path) as archive:
        members = _safe_members(archive)
        slides = sorted(
            (name for name in members if name.startswith("ppt/slides/slide") and name.endswith(".xml")),
            key=lambda name: int("".join(ch for ch in Path(name).stem if ch.isdigit()) or 0),
        )
        pages = []
        for index, name in enumerate(slides[:MAX_PAGES], 1):
            body = _xml_text(archive.read(members[name]))
            if body.strip():
                pages.append(f"--- slide {index} ---\n{body}")
    return _finish(ref, ".pptx", "document", "\n\n".join(pages), "stdlib-pptx-xml",
                   started, pages=len(pages))


def _extract_odf(path: Path, ref: str, started: float) -> OCRResult:
    suffix = path.suffix.lower()
    with zipfile.ZipFile(path) as archive:
        members = _safe_members(archive)
        info = members.get("content.xml")
        if info is None:
            raise ValueError("OpenDocument archive has no content.xml")
        text = _xml_text(archive.read(info))
    return _finish(ref, suffix, "document", text, "stdlib-odf-xml", started)


# ---- PDF ------------------------------------------------------------------------------------

def _extract_pdf(path: Path, ref: str, started: float, config: OCRConfig | None) -> OCRResult:
    try:
        from pypdf import PdfReader
    except Exception as error:  # noqa: BLE001 - optional dependency
        return _fail(ref, ".pdf", "pdf",
                     f"PDF text extraction needs the optional pypdf package ({error})", started)
    try:
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                return _fail(ref, ".pdf", "pdf",
                             "PDF is encrypted; provide an unencrypted local copy", started)
        pages = min(len(reader.pages), MAX_PAGES)
        chunks: list[str] = []
        empty_pages: list[int] = []
        for index in range(pages):
            try:
                text = reader.pages[index].extract_text() or ""
            except Exception:  # noqa: BLE001 - a damaged page must not discard the readable ones
                text = ""
            if text.strip():
                chunks.append(f"--- page {index + 1} ---\n{text.strip()}")
            else:
                empty_pages.append(index)
        version = getattr(__import__("pypdf"), "__version__", None)
        if chunks:
            joined = "\n\n".join(chunks)
            truncated = len(joined) > MAX_EXTRACT_CHARS or len(reader.pages) > pages
            if truncated:
                joined = joined[:MAX_EXTRACT_CHARS]
            return _finish(ref, ".pdf", "pdf", joined, "pypdf", started,
                           pages=len(chunks), truncated=truncated, version=version)
        # No text layer: try rendering scanned pages when OCR is available.
        ocr_text = _ocr_pdf_pages(path, empty_pages[:20], config)
        if ocr_text:
            return _finish(ref, ".pdf", "pdf", ocr_text, "tesseract (scanned pdf)", started,
                           pages=len(empty_pages), truncated=len(empty_pages) > 20 or len(reader.pages) > pages,
                           version=version)
        return _fail(ref, ".pdf", "pdf",
                     "PDF has no text layer and scanned-page OCR is unavailable", started)
    except (OSError, ValueError) as error:
        return _fail(ref, ".pdf", "pdf", f"PDF extraction failed: {error}", started)


def _ocr_pdf_pages(path: Path, pages: list[int], config: OCRConfig | None) -> str:
    try:
        import fitz  # type: ignore - optional PyMuPDF renderer
        engine = OCREngine(config)
        if not engine.available:
            return ""
        parts: list[str] = []
        with fitz.open(str(path)) as document:
            for index in pages:
                if index >= document.page_count:
                    continue
                page = document.load_page(index)
                pixmap = page.get_pixmap(dpi=150)
                image = _pixmap_to_pil(pixmap)
                if image is None:
                    continue
                result = engine.recognize_pil(image, image_ref=f"{path}#page={index + 1}",
                                              document_type="pdf")
                if result.ok:
                    parts.append(f"--- page {index + 1} (OCR) ---\n{result.text}")
        return "\n\n".join(parts)
    except Exception:  # noqa: BLE001 - OCR fallback is best-effort
        return ""


def _pixmap_to_pil(pixmap: Any):
    try:
        from PIL import Image
        mode = "RGBA" if pixmap.alpha else "RGB"
        return Image.frombytes(mode, (pixmap.width, pixmap.height), pixmap.samples)
    except Exception:  # noqa: BLE001
        return None


# ---- public API -----------------------------------------------------------------------------

def extract_file(path: str | os.PathLike, *, filename: str | None = None,
                 config: OCRConfig | None = None) -> OCRResult:
    """Extract text from a supported upload. Never raises for bad input."""
    import time
    started = time.perf_counter()
    target = Path(path)
    ref = filename or target.name
    info = document_info(filename or target.name)
    if info.kind == "unsupported":
        supported = ", ".join(sorted(SUPPORTED_SUFFIXES))
        return _fail(ref, info.suffix, "document",
                     f"unsupported file type {info.suffix or '(none)'}; supported: {supported}",
                     started)
    try:
        if not target.is_file():
            return _fail(ref, info.suffix, info.kind, f"file not found: {target}", started)
        size = target.stat().st_size
        if size <= 0:
            return _fail(ref, info.suffix, info.kind, "file is empty", started)
        if size > MAX_ARCHIVE_MEMBER:
            return _fail(ref, info.suffix, info.kind,
                         f"file is larger than {MAX_ARCHIVE_MEMBER // (1024 * 1024)} MB", started)
        _validate_magic(target, info)
        if info.kind == "image":
            result = ocr_file(target, image_ref=ref, document_type="image", config=config)
            return _with_suffix(result, info.suffix)
        if info.kind == "pdf":
            return _extract_pdf(target, ref, started, config)
        if info.suffix == ".docx":
            return _extract_docx(target, ref, started)
        if info.suffix == ".pptx":
            return _extract_pptx(target, ref, started)
        if info.suffix in {".odt", ".odp", ".ods"}:
            return _extract_odf(target, ref, started)
        data = _read_bounded(target)
        text = _decode_text(data)
        if info.suffix in {".html", ".htm"}:
            text, _title = html_to_text(text)
        truncated = len(text) > MAX_EXTRACT_CHARS
        if truncated:
            text = text[:MAX_EXTRACT_CHARS]
        return _finish(ref, info.suffix, "text", text, "local text", started,
                       truncated=truncated)
    except (OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as error:
        return _fail(ref, info.suffix, info.kind, f"document extraction failed: {error}", started)
    except Exception as error:  # noqa: BLE001 - one bad upload must not take down the worker
        return _fail(ref, info.suffix, info.kind,
                     f"document extraction failed: {type(error).__name__}: {error}", started)


def _with_suffix(result: OCRResult, suffix: str) -> OCRResult:
    meta = dict(result.meta or {})
    meta["suffix"] = suffix
    return OCRResult(
        result.ok, result.text, result.confidence, result.engine, result.engine_version,
        result.image_ref, result.image_sha256, "image" if result.ok else result.document_type,
        result.elapsed_ms, result.reason, result.verified, result.pages, result.truncated, meta,
    )
