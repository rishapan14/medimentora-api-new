"""Backward-compatible OCR entry point — delegates to OCRService."""

from app.services.report_analysis.ocr.models import OCRResult
from app.services.report_analysis.ocr.service import OCRService

extract_text = OCRService.extract_text

__all__ = ["OCRResult", "OCRService", "extract_text"]
