from skills.perception import OCRConfig, OCRCorrectionStore, OCREngine, OCRResult, ocr_file


def test_ocr_config_validation():
    try:
        OCRConfig(psm=99)
        assert False, "expected invalid psm"
    except ValueError:
        pass


def test_ocr_missing_image_is_reported(tmp_path):
    result = ocr_file(tmp_path / "missing.png")
    assert not result.ok
    assert "not found" in result.reason


def test_ocr_correction_store_requires_explicit_correction(tmp_path):
    store = OCRCorrectionStore(tmp_path / "ocr.db")
    result = OCRResult(True, text="wrong OCR", confidence=0.5, image_ref="sample.png",
                       image_sha256="abc", engine_version="test")
    rid = store.add(result)
    assert store.verified_corrections() == []
    store.correct(rid, "corrected text", user_verified=True)
    rows = store.verified_corrections()
    assert len(rows) == 1 and rows[0]["correction"] == "corrected text"


def test_ocr_unknown_record_raises(tmp_path):
    store = OCRCorrectionStore(tmp_path / "ocr.db")
    try:
        store.correct(99, "x")
        assert False, "expected missing record"
    except KeyError:
        pass

def test_controller_persists_successful_ocr_observation(monkeypatch):
    from brain.controller import Controller, default_registry
    from brain.need_field import NeedField, Task
    from foundation.language_model import EchoModel
    from learning.ama import AMA
    from memory.database import Database
    import brain.controller as controller_module

    db = Database()
    reg = default_registry(); reg.get("ocr").available = True
    ctl = Controller(EchoModel(), ama=AMA(db), nfd=NeedField(reg))
    fake = OCRResult(True, text="hello from image", confidence=.91, image_ref="image.png",
                     image_sha256="hash", engine_version="tesseract-test")
    monkeypatch.setattr(controller_module, "ocr_file", lambda *a, **k: fake)
    result = ctl.handle(Task("read this image", has_image=True, image_path="image.png"))
    row = db.conn.execute("SELECT extracted_text,confidence,image_sha256 FROM ocr_records").fetchone()
    assert row[0] == "hello from image" and row[1] == .91 and row[2] == "hash"
    db.close()
