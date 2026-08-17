"""X-ray preprocessing package (Phases 1–3).

Phase 1: ``format_sniff`` — magic-byte detection for upload validation.
Phase 2: quality assessment lives in ``app.services.xray.quality``.
Phase 3: ``pipeline`` + ``steps`` — OpenCV enhancement for educational AI.
"""

from app.services.xray.preprocessing.format_sniff import (
  DetectedImageFormat,
  sniff_image_format,
)
from app.services.xray.preprocessing.pipeline import (
  ImagePreprocessor,
  XrayPreprocessResult,
)

__all__ = [
  "DetectedImageFormat",
  "sniff_image_format",
  "ImagePreprocessor",
  "XrayPreprocessResult",
]
