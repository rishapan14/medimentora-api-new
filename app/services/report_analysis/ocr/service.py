"""Production OCR service orchestrating engines, preprocessing, and PDF handling."""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError

from flask import current_app

from app.services.report_analysis.ocr.engines.azure_document_intelligence import AzureDocumentIntelligenceEngine
from app.services.report_analysis.ocr.engines.base import BaseOCREngine
from app.services.report_analysis.ocr.engines.google_document_ai import GoogleDocumentAIEngine
from app.services.report_analysis.ocr.engines.paddle_engine import PaddleOCREngine
from app.services.report_analysis.ocr.engines.tesseract_engine import TesseractEngine
from app.services.report_analysis.ocr.models import OCRPageResult, OCRQualityMetrics, OCRResult
from app.services.report_analysis.ocr.pdf_extractor import extract_pdf_pages
from app.services.report_analysis.ocr.preprocessing import preprocess_image_detailed
from app.services.report_analysis.ocr.reading_order import merge_reading_order
from app.services.report_analysis.ocr.text_cleaner import clean_extracted_text, estimate_text_quality

logger = logging.getLogger(__name__)


class OCRService:
    """High-quality OCR pipeline for medical report documents."""

    @classmethod
    def extract_text(cls, file_path: str, file_type: str) -> OCRResult:
        """Extract and clean text from image or PDF medical reports."""
        started = time.perf_counter()
        normalized = (file_type or "").strip().lower()

        try:
            if normalized == "pdf":
                result = cls._extract_pdf(file_path)
            elif normalized == "image":
                result = cls._extract_image(file_path)
            else:
                return OCRResult(
                    success=False,
                    message=f"Unsupported file type: {file_type or 'unknown'}.",
                    error_code="unsupported_file",
                    processing_time_ms=cls._elapsed_ms(started),
                )
        except Exception:
            logger.exception("OCR pipeline failed for %s", file_path)
            return OCRResult(
                success=False,
                message="OCR processing failed for this document.",
                error_code="ocr_failed",
                processing_time_ms=cls._elapsed_ms(started),
            )

        result.processing_time_ms = cls._elapsed_ms(started)
        return result

    @classmethod
    def _extract_image(cls, file_path: str) -> OCRResult:
        if not os.path.isfile(file_path):
            return OCRResult(success=False, message="Image file not found.", error_code="missing_image")

        preprocess = cls._config("OCR_PREPROCESS", True)
        enhance_result = preprocess_image_detailed(file_path, enabled=preprocess)
        processed_path = enhance_result.path

        logger.info(
            "OCR started for image: %s (enhanced=%s, steps=%s)",
            file_path,
            enhance_result.success,
            ",".join(enhance_result.applied_steps) or "none",
        )
        try:
            text, engine, confidence = cls._run_engine_chain(processed_path)
        except FuturesTimeoutError:
            return OCRResult(success=False, message="OCR timed out.", error_code="ocr_timeout")
        except RuntimeError as exc:
            return cls._runtime_error_result(str(exc))

        cleaned = clean_extracted_text(text)
        if not cleaned:
            return OCRResult(
                success=False,
                message=(
                    "No readable text found in this image. "
                    "Upload a lab report PDF or a clear photo of a printed report with text values — "
                    "X-rays and scans without text cannot be analyzed by OCR."
                ),
                error_code="empty_ocr",
                engine=engine,
            )

        quality = cls._build_quality(cleaned, confidence, page_count=1, is_scanned=True, engine=engine)
        logger.info("OCR completed (%s) — %d chars, confidence=%.2f", engine, len(cleaned), quality.confidence)

        return OCRResult(
            success=True,
            text=cleaned,
            message="Text extracted successfully.",
            engine=engine,
            quality=quality,
            pages=[OCRPageResult(page_number=1, text=cleaned, confidence=confidence, is_scanned=True, engine=engine)],
        )

    @classmethod
    def _extract_pdf(cls, file_path: str) -> OCRResult:
        if not os.path.isfile(file_path):
            return OCRResult(success=False, message="PDF file not found.", error_code="missing_pdf")

        logger.info("PDF extraction started: %s", file_path)
        preprocess = cls._config("OCR_PREPROCESS", True)

        def ocr_page(image_path: str) -> tuple[str, float, str]:
            enhanced = preprocess_image_detailed(image_path, enabled=preprocess)
            try:
                text, engine, confidence = cls._run_engine_chain(enhanced.path)
                return clean_extracted_text(text), confidence, engine
            except RuntimeError as exc:
                msg = str(exc)
                if msg.startswith("OCR_EMPTY"):
                    return "", 0.0, "none"
                raise

        try:
            raw_text, pages, any_scanned = extract_pdf_pages(file_path, ocr_page_callback=ocr_page)
        except FileNotFoundError:
            return OCRResult(success=False, message="PDF file not found.", error_code="missing_pdf")
        except RuntimeError as exc:
            return cls._runtime_error_result(str(exc))

        cleaned = clean_extracted_text(raw_text)
        if not cleaned:
            return OCRResult(
                success=False,
                message=(
                    "Could not extract readable text from this PDF. "
                    "It may be scanned poorly, encrypted, or contain no printed text."
                ),
                error_code="empty_pdf",
                solution="Upload a text-based lab report PDF, or a clearer scan of a printed report.",
            )

        avg_conf = sum(p.confidence for p in pages) / max(len(pages), 1)
        engine = pages[0].engine if pages else "pypdf"
        if any_scanned:
            engine = cls._preferred_engine_name()

        quality = cls._build_quality(cleaned, avg_conf, len(pages), any_scanned, engine)
        logger.info(
            "PDF extraction completed — pages=%d scanned=%s chars=%d confidence=%.2f",
            len(pages),
            any_scanned,
            len(cleaned),
            quality.confidence,
        )

        return OCRResult(
            success=True,
            text=cleaned,
            message="Text extracted successfully.",
            engine=engine,
            quality=quality,
            pages=pages,
        )

    @classmethod
    def _run_engine_chain(cls, image_path: str) -> tuple[str, str, float]:
        timeout = int(cls._config("OCR_TIMEOUT_SECONDS", 120))
        engines = cls._engine_chain()

        available = [engine for engine in engines if engine.is_available()]
        if not available:
            raise RuntimeError(
                "OCR_NOT_INSTALLED: No OCR engine is installed in this Python environment."
            )

        last_error = "OCR produced no text."
        saw_empty = False
        for engine in available:
            logger.info("Running OCR engine: %s", engine.name)
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    output = pool.submit(engine.extract, image_path).result(timeout=timeout)
                text = merge_reading_order(output.lines) if output.lines else ""
                if not text and output.lines:
                    text = "\n".join(line.text for line in output.lines if line.text.strip())
                if text.strip():
                    confidence = (
                        sum(line.confidence for line in output.lines) / len(output.lines)
                        if output.lines
                        else estimate_text_quality(text)
                    )
                    return text, output.engine_name, confidence
                saw_empty = True
                last_error = f"{engine.name} found no readable text in this file."
                logger.warning("%s", last_error)
            except FuturesTimeoutError:
                raise
            except Exception:
                logger.exception("OCR engine failed: %s", engine.name)
                last_error = f"{engine.name} failed while reading this file."

        if saw_empty:
            raise RuntimeError(f"OCR_EMPTY: {last_error}")
        raise RuntimeError(f"OCR_FAILED: {last_error}")

    @classmethod
    def _engine_chain(cls) -> list[BaseOCREngine]:
        pref = str(cls._config("OCR_ENGINE", "auto")).lower()
        # Local engines first — cloud stubs only when explicitly configured
        local_engines: list[BaseOCREngine] = [
            PaddleOCREngine(),
            TesseractEngine(),
        ]
        cloud_engines: list[BaseOCREngine] = [
            GoogleDocumentAIEngine(),
            AzureDocumentIntelligenceEngine(),
        ]

        if pref == "google_document_ai":
            return [GoogleDocumentAIEngine()]
        if pref in ("azure", "azure_document_intelligence"):
            return [AzureDocumentIntelligenceEngine()]
        if pref in ("paddleocr", "paddle", "rapidocr"):
            return [PaddleOCREngine()]
        if pref == "tesseract":
            return [TesseractEngine()]

        # auto — RapidOCR/PaddleOCR first (installed locally), then Tesseract, then cloud
        return local_engines + cloud_engines

    @classmethod
    def _preferred_engine_name(cls) -> str:
        for engine in cls._engine_chain():
            if engine.is_available():
                return engine.name
        return "paddleocr"

    @staticmethod
    def _build_quality(
        text: str,
        engine_confidence: float,
        page_count: int,
        is_scanned: bool,
        engine: str,
    ) -> OCRQualityMetrics:
        heuristic = estimate_text_quality(text)
        confidence = min(1.0, engine_confidence * 0.6 + heuristic * 0.4)
        warnings: list[str] = []
        if confidence < 0.45:
            warnings.append("Low OCR confidence — results may be incomplete.")
        if len(text) < 80:
            warnings.append("Very little text extracted — upload a clearer document if possible.")

        return OCRQualityMetrics(
            confidence=confidence,
            page_count=page_count,
            char_count=len(text),
            word_count=len(text.split()),
            is_scanned=is_scanned,
            low_confidence=confidence < 0.45,
            warnings=warnings,
        )

    @staticmethod
    def _config(key: str, default):
        try:
            return current_app.config.get(key, os.getenv(key, default))
        except RuntimeError:
            return os.getenv(key, default)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)

    @staticmethod
    def _runtime_error_result(message: str) -> OCRResult:
        """Map internal OCR RuntimeError codes to user-facing results."""
        if message.startswith("OCR_NOT_INSTALLED"):
            logger.error("OCR engine unavailable: %s", message)
            return OCRResult(
                success=False,
                message="OCR engine is not installed.",
                error_code="ocr_not_available",
                solution=(
                    "Install RapidOCR in the Flask virtual environment, then start the API with "
                    ".venv\\Scripts\\python.exe run.py (or .\\start-api.ps1)."
                ),
            )
        if message.startswith("OCR_EMPTY"):
            detail = message.split(":", 1)[-1].strip()
            logger.warning("OCR found no text: %s", detail)
            return OCRResult(
                success=False,
                message=(
                    "No readable text was found in this file. "
                    "Upload a lab report (PDF/JPG/PNG) that contains printed text, values, and units. "
                    "X-rays and image-only scans without text cannot be analyzed by OCR."
                ),
                error_code="empty_ocr",
                solution="Use a CBC, lipid profile, or other text-based lab report.",
            )
        logger.exception("OCR failed: %s", message)
        return OCRResult(
            success=False,
            message="OCR failed while reading this file. Try a clearer PDF or image.",
            error_code="ocr_failed",
            solution=message,
        )

    @staticmethod
    def _engine_setup_hint() -> str:
        return (
            "Install OCR into the same Python env that runs Flask:\n"
            "  .venv\\Scripts\\python.exe -m pip install rapidocr-onnxruntime pymupdf opencv-python numpy\n"
            "Then restart the API server. Optional: OCR_ENGINE=paddleocr"
        )
