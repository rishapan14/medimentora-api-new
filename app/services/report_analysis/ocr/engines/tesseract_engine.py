"""Tesseract OCR engine."""

from __future__ import annotations

import logging
import os
import platform
import shutil
from pathlib import Path

from app.services.report_analysis.ocr.engines.base import BaseOCREngine, EngineLine, EngineOutput

logger = logging.getLogger(__name__)

WINDOWS_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

_tesseract_cmd: str | None = None


class TesseractEngine(BaseOCREngine):
    """System Tesseract OCR engine."""

    name = "tesseract"

    def is_available(self) -> bool:
        return resolve_tesseract_executable() is not None

    def extract(self, image_path: str) -> EngineOutput:
        import pytesseract
        from PIL import Image

        cmd = resolve_tesseract_executable()
        if not cmd:
            raise RuntimeError("Tesseract is not installed.")

        global _tesseract_cmd
        _tesseract_cmd = cmd
        pytesseract.pytesseract.tesseract_cmd = cmd

        with Image.open(image_path) as img:
            text = pytesseract.image_to_string(img).strip()
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

        confidences: list[float] = []
        lines: list[EngineLine] = []
        for i, raw in enumerate(data.get("text", [])):
            token = (raw or "").strip()
            if not token:
                continue
            try:
                confidences.append(max(0.0, float(data["conf"][i]) / 100.0))
            except (TypeError, ValueError):
                confidences.append(0.5)

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.6
        if text:
            for line in text.splitlines():
                line = line.strip()
                if line:
                    lines.append(EngineLine(text=line, confidence=avg_conf))

        return EngineOutput(lines=lines, engine_name="tesseract")


def resolve_tesseract_executable() -> str | None:
    """Resolve tesseract binary from env, PATH, or common install locations."""
    configured = os.getenv("TESSERACT_CMD", "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return str(path)
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        return None

    found = shutil.which("tesseract")
    if found:
        return found

    if platform.system() == "Windows":
        for candidate in WINDOWS_TESSERACT_PATHS:
            if Path(candidate).is_file():
                return candidate
    return None
