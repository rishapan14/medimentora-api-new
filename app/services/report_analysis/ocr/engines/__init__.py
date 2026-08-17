"""OCR engines for medical report extraction."""

from app.services.report_analysis.ocr.engines.paddle_engine import PaddleOCREngine
from app.services.report_analysis.ocr.engines.tesseract_engine import TesseractEngine

__all__ = ["PaddleOCREngine", "TesseractEngine"]
