"""Phase 3 OpenCV preprocessing pipeline for educational X-ray images.

Composable steps live in ``steps.py``. ``ImagePreprocessor`` remains the
public facade used by upload/analyze services.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from app.services.xray.preprocessing import steps as prep_steps

logger = logging.getLogger(__name__)

DEFAULT_TARGET_MAX_DIM = 2048
DEFAULT_TARGET_MIN_DIM = 512


@dataclass
class XrayPreprocessResult:
  """Outcome of the X-ray enhancement pipeline."""

  success: bool
  path: str | None = None
  applied_steps: list[str] = field(default_factory=list)
  original_size: tuple[int, int] = (0, 0)  # (width, height)
  final_size: tuple[int, int] = (0, 0)
  rotation_degrees: float = 0.0
  processing_time_ms: int = 0
  mean_intensity: float | None = None
  std_intensity: float | None = None
  normalization: dict | None = None
  message: str = ""
  error_code: str | None = None
  warnings: list[str] = field(default_factory=list)
  quality: dict | None = None

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "path": self.path,
      "applied_steps": self.applied_steps,
      "original_size": list(self.original_size),
      "final_size": list(self.final_size),
      "rotation_degrees": round(self.rotation_degrees, 2),
      "processing_time_ms": self.processing_time_ms,
      "mean_intensity": self.mean_intensity,
      "std_intensity": self.std_intensity,
      "normalization": self.normalization,
      "message": self.message,
      "error_code": self.error_code,
      "warnings": self.warnings,
      "quality": self.quality,
    }


class ImagePreprocessor:
  """Enhance radiographic images for AI-assisted X-ray analysis (Phase 3)."""

  def __init__(
    self,
    target_max_dim: int = DEFAULT_TARGET_MAX_DIM,
    target_min_dim: int = DEFAULT_TARGET_MIN_DIM,
    clahe_clip_limit: float = 2.0,
    clahe_tile_size: int = 8,
    enable_border_removal: bool = True,
    enable_deskew: bool = True,
    enable_sharpen: bool = True,
  ):
    self.target_max_dim = target_max_dim
    self.target_min_dim = target_min_dim
    self.clahe_clip_limit = clahe_clip_limit
    self.clahe_tile_size = clahe_tile_size
    self.enable_border_removal = enable_border_removal
    self.enable_deskew = enable_deskew
    self.enable_sharpen = enable_sharpen

  def enhance(self, input_path: str, output_path: str | None = None) -> XrayPreprocessResult:
    """
    Run the full Phase 3 pipeline:

    load (+ EXIF rotate) → grayscale → border removal → small-angle deskew →
    denoise → CLAHE → histogram equalization blend → brightness normalization →
    sharpness → contrast → resize → normalization metadata → PNG save
    """
    started = time.perf_counter()
    if not input_path or not os.path.isfile(input_path):
      return XrayPreprocessResult(
        success=False,
        message="X-ray file not found for preprocessing.",
        error_code="missing_file",
        processing_time_ms=self._elapsed_ms(started),
      )

    try:
      import cv2
      import numpy as np
    except ImportError:
      return XrayPreprocessResult(
        success=False,
        message="OpenCV is required for X-ray preprocessing. Install opencv-python.",
        error_code="opencv_missing",
        processing_time_ms=self._elapsed_ms(started),
      )

    applied: list[str] = []
    warnings: list[str] = []
    rotation = 0.0

    try:
      image, exif_rotation = self._load_with_autorotate(input_path, cv2)
      if image is None:
        return XrayPreprocessResult(
          success=False,
          message="Could not read X-ray image (corrupted or unsupported).",
          error_code="unreadable_image",
          processing_time_ms=self._elapsed_ms(started),
        )
      rotation = float(exif_rotation or 0.0)
      if rotation:
        applied.append(f"auto_rotate_{int(rotation)}")
      else:
        applied.append("load")

      original_h, original_w = image.shape[:2]
      original_size = (original_w, original_h)

      gray, step, warn = prep_steps.to_grayscale(image, cv2)
      self._record(applied, warnings, step, warn)

      if self.enable_border_removal:
        gray, step, warn = prep_steps.remove_borders(gray, cv2, np)
        self._record(applied, warnings, step, warn)

      if self.enable_deskew:
        gray, deskew_deg, step, warn = prep_steps.deskew_small_angle(gray, cv2, np)
        self._record(applied, warnings, step, warn)
        rotation = float(rotation) + float(deskew_deg or 0.0)

      gray, step, warn = prep_steps.denoise(gray, cv2)
      self._record(applied, warnings, step, warn)

      gray, step, warn = prep_steps.apply_clahe(
        gray, cv2, clip_limit=self.clahe_clip_limit, tile_size=self.clahe_tile_size
      )
      self._record(applied, warnings, step, warn)

      gray, step, warn = prep_steps.histogram_equalization_blend(gray, cv2)
      self._record(applied, warnings, step, warn)

      gray, step, warn = prep_steps.normalize_brightness(gray, np)
      self._record(applied, warnings, step, warn)

      if self.enable_sharpen:
        gray, step, warn = prep_steps.enhance_sharpness(gray, cv2)
        self._record(applied, warnings, step, warn)

      gray, step, warn = prep_steps.contrast_boost(gray, cv2)
      self._record(applied, warnings, step, warn)

      gray, _changed, step, warn = prep_steps.resize_for_model(
        gray,
        cv2,
        target_max_dim=self.target_max_dim,
        target_min_dim=self.target_min_dim,
      )
      self._record(applied, warnings, step, warn)

      normalization = prep_steps.intensity_normalization_metadata(gray, np)
      applied.append("normalization")

      dest = output_path or self._default_output_path(input_path)
      os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
      ok = cv2.imwrite(dest, gray)
      if not ok:
        return XrayPreprocessResult(
          success=False,
          message="Failed to write preprocessed X-ray image.",
          error_code="write_failed",
          applied_steps=applied,
          original_size=original_size,
          processing_time_ms=self._elapsed_ms(started),
          warnings=warnings,
        )
      applied.append("save_png")

      final_h, final_w = gray.shape[:2]
      return XrayPreprocessResult(
        success=True,
        path=dest,
        applied_steps=applied,
        original_size=original_size,
        final_size=(final_w, final_h),
        rotation_degrees=rotation,
        processing_time_ms=self._elapsed_ms(started),
        mean_intensity=normalization.get("mean"),
        std_intensity=normalization.get("std"),
        normalization=normalization,
        message="X-ray preprocessing completed.",
        warnings=warnings,
      )
    except Exception:
      logger.exception("X-ray preprocessing failed for %s", input_path)
      return XrayPreprocessResult(
        success=False,
        message="X-ray preprocessing failed unexpectedly.",
        error_code="preprocess_failed",
        applied_steps=applied,
        processing_time_ms=self._elapsed_ms(started),
        warnings=warnings,
      )

  @staticmethod
  def _record(applied: list[str], warnings: list[str], step: str | None, warn: str | None) -> None:
    if step:
      applied.append(step)
    if warn:
      warnings.append(warn)

  def _load_with_autorotate(self, path: str, cv2_mod):
    """Load image and apply EXIF orientation when present."""
    rotation = 0.0
    try:
      from PIL import Image, ImageOps
      import numpy as np

      with Image.open(path) as pil_img:
        exif_orientation = None
        try:
          exif = pil_img.getexif()
          if exif:
            exif_orientation = exif.get(274)
        except Exception:
          exif_orientation = None

        oriented = ImageOps.exif_transpose(pil_img) or pil_img
        if exif_orientation and int(exif_orientation) not in (0, 1):
          rotation_map = {3: 180.0, 6: 90.0, 8: 270.0}
          rotation = rotation_map.get(int(exif_orientation), 90.0)

        arr = np.array(oriented.convert("RGB"))
        bgr = cv2_mod.cvtColor(arr, cv2_mod.COLOR_RGB2BGR)
        return bgr, rotation
    except Exception:
      image = cv2_mod.imread(path, cv2_mod.IMREAD_UNCHANGED)
      return image, 0.0

  @staticmethod
  def _default_output_path(input_path: str) -> str:
    base, _ = os.path.splitext(input_path)
    return f"{base}_preprocessed_{uuid.uuid4().hex[:8]}.png"

  @staticmethod
  def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
