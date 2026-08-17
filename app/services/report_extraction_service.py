"""Text extraction from PDF and images — delegates to app.utils.ocr."""

from app.utils.ocr import OCRResult, extract_text

__all__ = ["ReportExtractionService", "OCRResult", "extract_text"]


class ReportExtractionService:
    """Extract text from uploaded medical reports."""

    @staticmethod
    def extract_from_pdf(file_path: str) -> OCRResult:
        from app.utils.ocr import extract_text_from_pdf
        return extract_text_from_pdf(file_path)

    @staticmethod
    def extract_from_image(file_path: str) -> OCRResult:
        from app.utils.ocr import extract_text_from_image
        return extract_text_from_image(file_path)

    @classmethod
    def extract_text(cls, file_path: str, file_type: str) -> OCRResult:
        return extract_text(file_path, file_type)
