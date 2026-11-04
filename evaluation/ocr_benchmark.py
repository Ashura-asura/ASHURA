"""Evaluate local OCR against a held-out JSONL manifest.

Manifest rows: {"image": "relative/or/absolute/path", "expected_text": "...",
                "document_type": "document"}. Paths are resolved relative to the manifest.
"""
from __future__ import annotations
import argparse, json, re, statistics
from pathlib import Path
from skills.perception import OCRConfig, OCREngine


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.casefold()).strip()

def edit_distance(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j-1] + (x != y)))
        prev = cur
    return prev[-1]

def error_rate(pred: str, truth: str, unit: str) -> float:
    a = normalize(pred); b = normalize(truth)
    aa = list(a) if unit == "char" else a.split()
    bb = list(b) if unit == "char" else b.split()
    return edit_distance(aa, bb) / max(1, len(bb))

def run(manifest: str | Path, languages: str = "eng", psm: int = 6) -> dict:
    manifest = Path(manifest).resolve()
    rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    engine = OCREngine(OCRConfig(languages=languages, psm=psm))
    records = []
    for row in rows:
        image = Path(row["image"])
        if not image.is_absolute(): image = manifest.parent / image
        result = engine.recognize(image, document_type=row.get("document_type", "document"))
        records.append({"image": str(image), "ok": result.ok, "reason": result.reason,
            "confidence": result.confidence, "elapsed_ms": result.elapsed_ms,
            "cer": error_rate(result.text, row["expected_text"], "char") if result.ok else 1.0,
            "wer": error_rate(result.text, row["expected_text"], "word") if result.ok else 1.0})
    good = [r for r in records if r["ok"]]
    lat = [r["elapsed_ms"] for r in records]
    return {"manifest": str(manifest), "count": len(records), "success_rate": len(good)/max(1,len(records)),
        "mean_confidence": statistics.mean([r["confidence"] for r in good]) if good else 0.0,
        "mean_cer": statistics.mean([r["cer"] for r in records]) if records else 0.0,
        "mean_wer": statistics.mean([r["wer"] for r in records]) if records else 0.0,
        "p50_ms": statistics.median(lat) if lat else 0.0,
        "p95_ms": sorted(lat)[min(len(lat)-1, int(.95*len(lat)))] if lat else 0.0,
        "records": records, "engine": "tesseract", "languages": languages, "psm": psm}

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("manifest"); p.add_argument("--languages",default="eng")
    p.add_argument("--psm",type=int,default=6); p.add_argument("--out")
    a=p.parse_args(); report=run(a.manifest,a.languages,a.psm); text=json.dumps(report,indent=2)
    if a.out: Path(a.out).write_text(text,encoding="utf-8")
    print(text)
if __name__ == "__main__": main()
