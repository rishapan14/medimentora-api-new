"""Radiograph image quality assessment (Phase 2).

Detects common upload problems before AI analysis:
  blur, noise, low resolution, under/over exposure, wrong orientation,
  photo-of-monitor, camera photo, low contrast.

Returns a 0–100 quality score plus actionable improvement suggestions.
This is educational decision-support only — never a diagnosis.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Soft threshold: below this, UI should emphasize improvement tips
DEFAULT_POOR_SCORE = 55.0


@dataclass
class ImageQualityIssue:
  """One detected quality problem."""

  code: str
  label: str
  severity: str  # low | medium | high
  score_penalty: float
  detail: str
  suggestion: str

  def to_dict(self) -> dict[str, Any]:
    return {
      "code": self.code,
      "label": self.label,
      "severity": self.severity,
      "score_penalty": round(self.score_penalty, 2),
      "detail": self.detail,
      "suggestion": self.suggestion,
    }


@dataclass
class ImageQualityResult:
  """Full Phase 2 quality assessment outcome."""

  success: bool
  quality_score: float = 0.0
  grade: str = "unknown"  # excellent | good | fair | poor | unknown
  is_poor: bool = False
  issues: list[ImageQualityIssue] = field(default_factory=list)
  suggestions: list[str] = field(default_factory=list)
  metrics: dict[str, Any] = field(default_factory=dict)
  width: int = 0
  height: int = 0
  message: str = ""
  error_code: str | None = None
  version: str = "phase2-v1"

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "quality_score": round(self.quality_score, 1),
      "grade": self.grade,
      "is_poor": self.is_poor,
      "issues": [i.to_dict() for i in self.issues],
      "suggestions": self.suggestions,
      "metrics": self.metrics,
      "width": self.width,
      "height": self.height,
      "message": self.message,
      "error_code": self.error_code,
      "version": self.version,
      "disclaimer": (
        "Image quality assessment supports educational upload review only. "
        "It is not a diagnosis."
      ),
    }


class ImageQualityAssessor:
  """OpenCV-based radiograph quality checker."""

  def __init__(
    self,
    *,
    min_ok_edge: int = 256,
    poor_score_threshold: float = DEFAULT_POOR_SCORE,
  ):
    self.min_ok_edge = min_ok_edge
    self.poor_score_threshold = poor_score_threshold

  def assess(self, image_path: str) -> ImageQualityResult:
    """Assess quality of an image on disk (original upload preferred)."""
    if not image_path or not os.path.isfile(image_path):
      return ImageQualityResult(
        success=False,
        message="Image file not found for quality assessment.",
        error_code="missing_file",
      )

    try:
      import cv2
      import numpy as np
    except ImportError:
      return ImageQualityResult(
        success=False,
        message="OpenCV is required for image quality assessment.",
        error_code="opencv_missing",
      )

    try:
      bgr = cv2.imread(image_path, cv2.IMREAD_COLOR)
      if bgr is None:
        # Try grayscale fallback / unchanged
        gray_only = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if gray_only is None:
          return ImageQualityResult(
            success=False,
            message="Could not read image for quality assessment.",
            error_code="unreadable_image",
          )
        bgr = cv2.cvtColor(gray_only, cv2.COLOR_GRAY2BGR)
      gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    except Exception as exc:
      logger.warning("Quality assessment load failed: %s", exc)
      return ImageQualityResult(
        success=False,
        message="Could not load image for quality assessment.",
        error_code="unreadable_image",
      )

    height, width = gray.shape[:2]
    issues: list[ImageQualityIssue] = []
    metrics: dict[str, Any] = {
      "width": width,
      "height": height,
      "megapixels": round((width * height) / 1_000_000, 3),
    }

    issues.extend(self._check_resolution(width, height, metrics))
    issues.extend(self._check_blur(gray, metrics))
    issues.extend(self._check_noise(gray, metrics))
    issues.extend(self._check_contrast(gray, metrics))
    issues.extend(self._check_exposure(gray, metrics))
    issues.extend(self._check_orientation(gray, metrics))
    issues.extend(self._check_camera_photo(bgr, gray, metrics, image_path))
    issues.extend(self._check_monitor_photo(gray, metrics))

    score = 100.0
    for issue in issues:
      score -= float(issue.score_penalty)
    score = float(max(0.0, min(100.0, score)))

    grade = self._grade(score)
    is_poor = score < self.poor_score_threshold
    suggestions = self._unique_suggestions(issues)

    if is_poor and not suggestions:
      suggestions.append(
        "Re-upload a clearer digital radiograph export (DICOM, PNG, or high-quality JPEG) "
        "rather than a phone photo when possible."
      )

    message = (
      "Image quality is below the recommended threshold for educational AI analysis."
      if is_poor
      else "Image quality is acceptable for educational analysis."
    )

    return ImageQualityResult(
      success=True,
      quality_score=score,
      grade=grade,
      is_poor=is_poor,
      issues=issues,
      suggestions=suggestions,
      metrics=metrics,
      width=width,
      height=height,
      message=message,
    )

  # ------------------------------------------------------------------ checks

  def _check_resolution(self, width: int, height: int, metrics: dict) -> list[ImageQualityIssue]:
    min_edge = min(width, height)
    metrics["min_edge"] = min_edge
    issues: list[ImageQualityIssue] = []
    if min_edge < 128:
      issues.append(
        ImageQualityIssue(
          code="low_resolution",
          label="Extremely low resolution",
          severity="high",
          score_penalty=35,
          detail=f"Shortest edge is {min_edge}px.",
          suggestion="Upload a higher-resolution radiograph (at least 512px on the short side).",
        )
      )
    elif min_edge < self.min_ok_edge:
      issues.append(
        ImageQualityIssue(
          code="low_resolution",
          label="Low resolution",
          severity="medium",
          score_penalty=18,
          detail=f"Shortest edge is {min_edge}px (recommended ≥ {self.min_ok_edge}px).",
          suggestion="Use a larger image or original DICOM/PNG export for clearer educational review.",
        )
      )
    return issues

  def _check_blur(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import cv2

    lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    metrics["laplacian_variance"] = round(lap_var, 2)
    issues: list[ImageQualityIssue] = []
    if lap_var < 25:
      issues.append(
        ImageQualityIssue(
          code="blur",
          label="Severe blur",
          severity="high",
          score_penalty=28,
          detail=f"Sharpness score {lap_var:.1f} is very low.",
          suggestion="Re-acquire or re-export a sharp radiograph; avoid motion blur and out-of-focus camera shots.",
        )
      )
    elif lap_var < 80:
      issues.append(
        ImageQualityIssue(
          code="blur",
          label="Mild blur",
          severity="medium",
          score_penalty=12,
          detail=f"Sharpness score {lap_var:.1f} suggests soft edges.",
          suggestion="Prefer a direct digital export over a zoomed or soft phone photo.",
        )
      )
    return issues

  def _check_noise(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import cv2
    import numpy as np

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    residual = gray.astype(np.float32) - blurred.astype(np.float32)
    noise_std = float(np.std(residual))
    metrics["noise_std"] = round(noise_std, 2)
    issues: list[ImageQualityIssue] = []
    if noise_std > 18:
      issues.append(
        ImageQualityIssue(
          code="noise",
          label="High noise",
          severity="high",
          score_penalty=16,
          detail=f"Noise estimate {noise_std:.1f} is elevated.",
          suggestion="Avoid heavily compressed JPEGs and low-light camera photos of film/monitors.",
        )
      )
    elif noise_std > 12:
      issues.append(
        ImageQualityIssue(
          code="noise",
          label="Moderate noise",
          severity="medium",
          score_penalty=8,
          detail=f"Noise estimate {noise_std:.1f} is moderate.",
          suggestion="Upload a cleaner export; preprocessing can reduce mild noise but not severe grain.",
        )
      )
    return issues

  def _check_contrast(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import numpy as np

    std = float(np.std(gray))
    p5, p95 = np.percentile(gray.astype(np.float64), [5, 95])
    dynamic = float(p95 - p5)
    metrics["intensity_std"] = round(std, 2)
    metrics["dynamic_range_p5_p95"] = round(dynamic, 2)
    issues: list[ImageQualityIssue] = []
    if std < 18 or dynamic < 40:
      issues.append(
        ImageQualityIssue(
          code="low_contrast",
          label="Low contrast",
          severity="high" if std < 12 else "medium",
          score_penalty=20 if std < 12 else 12,
          detail=f"Contrast std={std:.1f}, dynamic range={dynamic:.1f}.",
          suggestion="Increase display/export contrast or use the original DICOM window/level settings.",
        )
      )
    return issues

  def _check_exposure(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import numpy as np

    mean = float(np.mean(gray))
    dark_frac = float(np.mean(gray < 25))
    bright_frac = float(np.mean(gray > 230))
    metrics["mean_intensity"] = round(mean, 2)
    metrics["dark_fraction"] = round(dark_frac, 3)
    metrics["bright_fraction"] = round(bright_frac, 3)
    issues: list[ImageQualityIssue] = []
    if mean < 45 or dark_frac > 0.55:
      issues.append(
        ImageQualityIssue(
          code="under_exposure",
          label="Under-exposed",
          severity="high" if mean < 30 else "medium",
          score_penalty=18 if mean < 30 else 10,
          detail=f"Mean intensity {mean:.1f}; dark pixels {dark_frac:.0%}.",
          suggestion="Brighten the export or adjust window/level before upload.",
        )
      )
    if mean > 200 or bright_frac > 0.45:
      issues.append(
        ImageQualityIssue(
          code="over_exposure",
          label="Over-exposed / washed out",
          severity="high" if mean > 220 else "medium",
          score_penalty=18 if mean > 220 else 10,
          detail=f"Mean intensity {mean:.1f}; bright pixels {bright_frac:.0%}.",
          suggestion="Reduce brightness / avoid clipped highlights when exporting the radiograph.",
        )
      )
    return issues

  def _check_orientation(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import cv2
    import numpy as np

    h, w = gray.shape[:2]
    aspect = w / max(h, 1)
    metrics["aspect_ratio"] = round(aspect, 3)

    # Edge energy: unexpected extreme landscape with strong vertical ribs may be sideways
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    ex = float(np.mean(np.abs(gx)))
    ey = float(np.mean(np.abs(gy)))
    metrics["edge_energy_x"] = round(ex, 2)
    metrics["edge_energy_y"] = round(ey, 2)

    issues: list[ImageQualityIssue] = []
    # Very tall thin or extremely wide with mismatched edge energy → likely rotated
    if aspect > 2.4 and ey > ex * 1.35:
      issues.append(
        ImageQualityIssue(
          code="wrong_orientation",
          label="Possible wrong orientation",
          severity="medium",
          score_penalty=10,
          detail="Wide frame with stronger vertical edge energy — image may be rotated.",
          suggestion="Rotate the radiograph to the standard viewing orientation before analysis.",
        )
      )
    elif aspect < 0.42 and ex > ey * 1.35:
      issues.append(
        ImageQualityIssue(
          code="wrong_orientation",
          label="Possible wrong orientation",
          severity="medium",
          score_penalty=10,
          detail="Tall frame with stronger horizontal edge energy — image may be rotated.",
          suggestion="Rotate the radiograph to the standard viewing orientation before analysis.",
        )
      )
    return issues

  def _check_camera_photo(self, bgr, gray, metrics: dict, image_path: str) -> list[ImageQualityIssue]:
    import cv2
    import numpy as np

    issues: list[ImageQualityIssue] = []
    b, g, r = cv2.split(bgr)
    bf = b.astype(np.float32)
    gf = g.astype(np.float32)
    rf = r.astype(np.float32)
    # Mean absolute channel separation (solid tinted photos have high mean, low std)
    color_delta = float(
      (np.mean(np.abs(bf - gf)) + np.mean(np.abs(rf - gf)) + np.mean(np.abs(rf - bf))) / 3.0
    )
    metrics["color_channel_delta"] = round(color_delta, 2)

    # EXIF hints (phones often embed Make/Model)
    exif_camera = False
    try:
      from PIL import Image, ExifTags

      with Image.open(image_path) as img:
        exif = img.getexif() or {}
        tag_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
        make = str(tag_map.get("Make") or "")
        model = str(tag_map.get("Model") or "")
        metrics["exif_make"] = make or None
        metrics["exif_model"] = model or None
        phone_hints = ("apple", "iphone", "samsung", "xiaomi", "pixel", "huawei", "oppo", "vivo", "oneplus")
        blob = f"{make} {model}".lower()
        exif_camera = any(h in blob for h in phone_hints)
    except Exception:
      metrics["exif_make"] = None
      metrics["exif_model"] = None

    metrics["likely_camera_photo"] = bool(exif_camera or color_delta > 8.0)

    if exif_camera or color_delta > 12.0:
      issues.append(
        ImageQualityIssue(
          code="camera_photo",
          label="Likely camera photo of an X-ray",
          severity="high" if color_delta > 18 else "medium",
          score_penalty=22 if color_delta > 18 else 14,
          detail=(
            f"Color variance={color_delta:.1f}"
            + ("; phone EXIF detected" if exif_camera else "")
            + "."
          ),
          suggestion=(
            "Prefer a direct digital radiograph or DICOM export instead of photographing "
            "a screen or printed film with a phone."
          ),
        )
      )
    elif color_delta > 8.0:
      issues.append(
        ImageQualityIssue(
          code="camera_photo",
          label="Possible camera / color capture",
          severity="low",
          score_penalty=6,
          detail=f"Mild color channel variance ({color_delta:.1f}).",
          suggestion="If this was photographed, re-upload a grayscale digital export when available.",
        )
      )
    return issues

  def _check_monitor_photo(self, gray, metrics: dict) -> list[ImageQualityIssue]:
    import cv2
    import numpy as np

    issues: list[ImageQualityIssue] = []
    # Border brightness: photos of monitors often include bright bezels / room light
    h, w = gray.shape[:2]
    border = max(4, min(h, w) // 40)
    top = gray[:border, :]
    bottom = gray[-border:, :]
    left = gray[:, :border]
    right = gray[:, -border:]
    border_mean = float(np.mean([np.mean(top), np.mean(bottom), np.mean(left), np.mean(right)]))
    center = gray[border : h - border, border : w - border]
    center_mean = float(np.mean(center)) if center.size else float(np.mean(gray))
    metrics["border_mean"] = round(border_mean, 2)
    metrics["center_mean"] = round(center_mean, 2)

    # Moire / screen grid proxy via high-frequency FFT energy ratio
    small = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA)
    f = np.fft.fftshift(np.fft.fft2(small.astype(np.float32)))
    mag = np.abs(f)
    cy, cx = 128, 128
    yy, xx = np.ogrid[:256, :256]
    dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
    high = float(np.mean(mag[dist > 80]))
    mid = float(np.mean(mag[(dist > 20) & (dist <= 80)]))
    hf_ratio = high / (mid + 1e-6)
    metrics["fft_high_mid_ratio"] = round(hf_ratio, 3)

    monitor_like = (border_mean > center_mean + 35 and border_mean > 140) or hf_ratio > 1.35
    metrics["likely_monitor_photo"] = bool(monitor_like)

    if monitor_like:
      issues.append(
        ImageQualityIssue(
          code="monitor_photo",
          label="Possible photo of a monitor",
          severity="high",
          score_penalty=20,
          detail=(
            f"Border vs center brightness and screen-pattern score suggest a photographed display "
            f"(hf_ratio={hf_ratio:.2f})."
          ),
          suggestion=(
            "Do not photograph a PACS/viewer screen. Export or download the radiograph digitally "
            "(DICOM/PNG/JPEG) instead."
          ),
        )
      )
    return issues

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _grade(score: float) -> str:
    if score >= 85:
      return "excellent"
    if score >= 70:
      return "good"
    if score >= 55:
      return "fair"
    return "poor"

  @staticmethod
  def _unique_suggestions(issues: list[ImageQualityIssue]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    # Higher severity first
    order = {"high": 0, "medium": 1, "low": 2}
    for issue in sorted(issues, key=lambda i: order.get(i.severity, 9)):
      tip = (issue.suggestion or "").strip()
      if tip and tip not in seen:
        seen.add(tip)
        out.append(tip)
    return out
