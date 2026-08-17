"""Hybrid PDF text extraction: digital text + OCR for scanned pages."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from app.services.report_analysis.ocr.models import OCRPageResult

logger = logging.getLogger(__name__)

MIN_DIGITAL_CHARS_PER_PAGE = 40


def extract_pdf_pages(file_path: str, ocr_page_callback) -> tuple[str, list[OCRPageResult], bool]:
    """
    Extract PDF text using digital layer first, OCR for scanned/low-text pages.

    ocr_page_callback(image_path) -> tuple[str, float, str]
    Returns merged text, per-page metadata, and whether any page was scanned.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError("PDF file not found.")

    try:
        import fitz  # PyMuPDF
    except ImportError:
        return _extract_pdf_pypdf_only(file_path)

    doc = fitz.open(str(path))
    pages: list[OCRPageResult] = []
    merged: list[str] = []
    any_scanned = False

    try:
        for idx in range(len(doc)):
            page_num = idx + 1
            page = doc.load_page(idx)
            digital = (page.get_text("text") or "").strip()

            if len(digital) >= MIN_DIGITAL_CHARS_PER_PAGE:
                pages.append(
                    OCRPageResult(
                        page_number=page_num,
                        text=digital,
                        confidence=0.95,
                        is_scanned=False,
                        engine="pymupdf",
                    )
                )
                merged.append(digital)
                continue

            any_scanned = True
            logger.info("PDF page %d appears scanned — running OCR", page_num)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            pix.save(tmp.name)

            ocr_text, confidence, engine = ocr_page_callback(tmp.name)
            pages.append(
                OCRPageResult(
                    page_number=page_num,
                    text=ocr_text,
                    confidence=confidence,
                    is_scanned=True,
                    engine=engine,
                )
            )
            merged.append(ocr_text)
    finally:
        doc.close()

    return "\n\n".join(part for part in merged if part), pages, any_scanned


def _extract_pdf_pypdf_only(file_path: str) -> tuple[str, list[OCRPageResult], bool]:
    from pypdf import PdfReader

    reader = PdfReader(file_path)
    if reader.is_encrypted:
        reader.decrypt("")

    pages: list[OCRPageResult] = []
    merged: list[str] = []
    for idx, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        pages.append(
            OCRPageResult(page_number=idx, text=text, confidence=0.8 if text else 0.2, is_scanned=False, engine="pypdf")
        )
        merged.append(text)

    return "\n\n".join(part for part in merged if part), pages, False
