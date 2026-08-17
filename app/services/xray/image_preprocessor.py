"""X-ray image preprocessing pipeline (Phase 3 facade).

Implementation lives in ``app.services.xray.preprocessing.pipeline``.
This module keeps backward-compatible imports for upload/analyze services.
"""

from app.services.xray.preprocessing.pipeline import (
  DEFAULT_TARGET_MAX_DIM,
  DEFAULT_TARGET_MIN_DIM,
  ImagePreprocessor,
  XrayPreprocessResult,
)

__all__ = [
  "DEFAULT_TARGET_MAX_DIM",
  "DEFAULT_TARGET_MIN_DIM",
  "ImagePreprocessor",
  "XrayPreprocessResult",
]
