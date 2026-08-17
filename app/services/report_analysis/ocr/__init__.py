"""Medical report OCR pipeline."""

from app.services.report_analysis.ocr.models import OCRResult
from app.services.report_analysis.ocr.service import OCRService

__all__ = ["OCRService", "OCRResult"]
