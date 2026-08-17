"""Data models for the OCR pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OCRPageResult:
    """Text extracted from a single page."""

    page_number: int
    text: str
    confidence: float = 0.0
    is_scanned: bool = False
    engine: str = ""


@dataclass
class OCRQualityMetrics:
    """Quality indicators for extracted text."""

    confidence: float = 0.0
    page_count: int = 0
    char_count: int = 0
    word_count: int = 0
    is_scanned: bool = False
    low_confidence: bool = False
    warnings: list[str] = field(default_factory=list)


@dataclass
class OCRResult:
    """Structured OCR outcome — never raises to callers."""

    success: bool
    text: str = ""
    message: str = ""
    engine: str | None = None
    processing_time_ms: int = 0
    quality: OCRQualityMetrics | None = None
    pages: list[OCRPageResult] = field(default_factory=list)
    solution: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict:
        payload: dict = {
            "success": self.success,
            "message": self.message,
        }
        if self.success:
            payload["text"] = self.text
            payload["processing_time_ms"] = self.processing_time_ms
        if self.engine:
            payload["engine"] = self.engine
            payload["ocr_engine"] = self.engine
        if self.quality:
            payload["ocr_quality"] = {
                "confidence": round(self.quality.confidence, 3),
                "page_count": self.quality.page_count,
                "char_count": self.quality.char_count,
                "word_count": self.quality.word_count,
                "is_scanned": self.quality.is_scanned,
                "low_confidence": self.quality.low_confidence,
                "warnings": self.quality.warnings,
            }
        if self.pages:
            payload["pages"] = [
                {
                    "page_number": p.page_number,
                    "confidence": round(p.confidence, 3),
                    "is_scanned": p.is_scanned,
                    "engine": p.engine,
                    "char_count": len(p.text),
                }
                for p in self.pages
            ]
        if self.solution:
            payload["solution"] = self.solution
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload
