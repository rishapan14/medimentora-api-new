"""PaddleOCR-based engine (RapidOCR ONNX + optional full PaddleOCR)."""

from __future__ import annotations

import logging

from app.services.report_analysis.ocr.engines.base import BaseOCREngine, EngineLine, EngineOutput
from app.services.report_analysis.ocr.reading_order import merge_reading_order

logger = logging.getLogger(__name__)

_rapidocr_instance = None
_paddleocr_instance = None


class PaddleOCREngine(BaseOCREngine):
    """
    Primary OCR engine using PaddleOCR technology.

    Uses RapidOCR (PaddleOCR ONNX) by default; falls back to full PaddleOCR when installed.
    """

    name = "paddleocr"

    def is_available(self) -> bool:
        return self._get_rapidocr() is not None or self._get_paddleocr() is not None

    def extract(self, image_path: str) -> EngineOutput:
        paddle = self._get_paddleocr()
        if paddle is not None:
            return self._extract_paddleocr(paddle, image_path)
        rapid = self._get_rapidocr()
        if rapid is None:
            raise RuntimeError("PaddleOCR/RapidOCR is not installed.")
        return self._extract_rapidocr(rapid, image_path)

    @staticmethod
    def _get_rapidocr():
        global _rapidocr_instance
        if _rapidocr_instance is not None:
            return _rapidocr_instance
        try:
            from rapidocr_onnxruntime import RapidOCR

            _rapidocr_instance = RapidOCR()
            logger.info("RapidOCR (PaddleOCR ONNX) initialized successfully")
            return _rapidocr_instance
        except ImportError:
            logger.warning(
                "rapidocr-onnxruntime is not installed in this Python environment. "
                "Install with: .venv\\Scripts\\python.exe -m pip install rapidocr-onnxruntime"
            )
            return None
        except Exception:
            logger.exception("RapidOCR failed to initialize")
            return None

    @staticmethod
    def _get_paddleocr():
        global _paddleocr_instance
        if _paddleocr_instance is not None:
            return _paddleocr_instance
        try:
            from paddleocr import PaddleOCR

            _paddleocr_instance = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
            return _paddleocr_instance
        except ImportError:
            return None
        except Exception:
            logger.warning("Full PaddleOCR installed but failed to initialize — using RapidOCR")
            return None

    @staticmethod
    def _extract_rapidocr(engine, image_path: str) -> EngineOutput:
        result, _ = engine(image_path)
        lines: list[EngineLine] = []
        if result:
            for item in result:
                box, text, score = item[0], item[1], float(item[2] if len(item) > 2 else 0.8)
                lines.append(EngineLine(text=str(text), confidence=score, box=box))
        text = merge_reading_order(lines) if lines else ""
        if not text and result:
            text = "\n".join(str(item[1]) for item in result)
        return EngineOutput(lines=lines, engine_name="rapidocr")

    @staticmethod
    def _extract_paddleocr(engine, image_path: str) -> EngineOutput:
        raw = engine.ocr(image_path, cls=True)
        lines: list[EngineLine] = []
        if raw:
            for block in raw[0] or []:
                box, payload = block[0], block[1]
                text, score = payload[0], float(payload[1])
                lines.append(EngineLine(text=text, confidence=score, box=box))
        text = merge_reading_order(lines)
        return EngineOutput(lines=lines, engine_name="paddleocr")
