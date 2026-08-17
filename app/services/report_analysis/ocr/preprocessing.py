"""Image preprocessing for medical document OCR.

Backward-compatible shim — the real pipeline now lives in
`app.services.image_preprocessor` (OpenCV: shadow removal, denoise,
CLAHE contrast, deskew, sharpen, optional adaptive threshold).
"""

from __future__ import annotations

import logging

from app.services.image_preprocessor import PreprocessResult, enhance_image

logger = logging.getLogger(__name__)


def preprocess_image(image_path: str, enabled: bool = True) -> str:
    """Enhance an image for OCR and return the path to the processed file."""
    return preprocess_image_detailed(image_path, enabled=enabled).path


def preprocess_image_detailed(image_path: str, enabled: bool = True) -> PreprocessResult:
    """Enhance an image for OCR and return full pipeline metadata."""
    result = enhance_image(image_path, enabled=enabled)
    if result.warnings:
        logger.warning("Image enhancement warnings: %s", "; ".join(result.warnings))
    return result
