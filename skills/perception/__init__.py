"""Local perception skills."""
from .documents import (IMAGE_SUFFIXES, SUPPORTED_SUFFIXES, TEXT_SUFFIXES,
                        document_info, extract_file, is_supported)
from .ocr import OCRConfig, OCRCorrectionStore, OCREngine, OCRResult, ocr_file

__all__ = [
    "IMAGE_SUFFIXES", "SUPPORTED_SUFFIXES", "TEXT_SUFFIXES",
    "OCRConfig", "OCREngine", "OCRResult", "OCRCorrectionStore", "ocr_file",
    "document_info", "extract_file", "is_supported",
]
