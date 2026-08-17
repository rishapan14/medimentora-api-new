"""Atomic OpenCV preprocessing steps for educational X-ray images (Phase 3).

Each function is fail-safe: on error it returns the input unchanged plus a warning.
Never invents clinical content — only improves pixel readability.
"""

from __future__ import annotations

from typing import Any


def to_grayscale(image, cv2) -> tuple[Any, str | None, str | None]:
  if image is None:
    return image, None, "empty_image"
  if len(image.shape) == 3:
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), "grayscale", None
  return image, "grayscale_skip", None


def remove_borders(gray, cv2, np, *, max_trim_frac: float = 0.18) -> tuple[Any, str | None, str | None]:
  """Crop uniform dark/bright borders often left by scanners or photos."""
  try:
    h, w = gray.shape[:2]
    if h < 64 or w < 64:
      return gray, "border_removal_skipped", None

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    content = cv2.bitwise_or(mask, cv2.inRange(blurred, 25, 230))
    coords = cv2.findNonZero(content)
    if coords is None:
      return gray, "border_removal_skipped", None

    x, y, bw, bh = cv2.boundingRect(coords)
    # Keep most of the anatomy — reject aggressive crops
    if bw < int(w * 0.70) or bh < int(h * 0.70):
      return gray, "border_removal_skipped", None

    max_x_trim = int(w * max_trim_frac)
    max_y_trim = int(h * max_trim_frac)
    left, top = x, y
    right, bottom = w - (x + bw), h - (y + bh)
    if left > max_x_trim or right > max_x_trim or top > max_y_trim or bottom > max_y_trim:
      return gray, "border_removal_skipped", None

    if max(left, right, top, bottom) < 3:
      return gray, "border_removal_none", None

    pad = max(2, min(h, w) // 100)
    x0 = max(0, x - pad)
    y0 = max(0, y - pad)
    x1 = min(w, x + bw + pad)
    y1 = min(h, y + bh + pad)
    if (x1 - x0) < 32 or (y1 - y0) < 32:
      return gray, "border_removal_skipped", None
    return gray[y0:y1, x0:x1], "border_removal", None
  except Exception:
    return gray, None, "Border removal failed; skipped."


def deskew_small_angle(gray, cv2, np, *, max_degrees: float = 8.0) -> tuple[Any, float, str | None, str | None]:
  """Correct small in-plane rotation using edge projection (EXIF handled separately)."""
  try:
    h, w = gray.shape[:2]
    if min(h, w) < 128:
      return gray, 0.0, "deskew_skipped", None

    edges = cv2.Canny(gray, 50, 150)
    coords = np.column_stack(np.where(edges > 0))
    if coords.shape[0] < 200:
      return gray, 0.0, "deskew_skipped", None

    # OpenCV minAreaRect expects (x, y) = (col, row)
    pts = coords[:, ::-1].astype(np.float32)
    angle = float(cv2.minAreaRect(pts)[-1])
    # minAreaRect angle is in [-90, 0); normalize to small correction
    if angle < -45:
      angle = 90.0 + angle
    if abs(angle) < 0.4 or abs(angle) > max_degrees:
      return gray, 0.0, "deskew_none", None

    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
      gray,
      matrix,
      (w, h),
      flags=cv2.INTER_LINEAR,
      borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated, angle, f"deskew_{angle:.1f}", None
  except Exception:
    return gray, 0.0, None, "Deskew failed; skipped."


def denoise(gray, cv2) -> tuple[Any, str | None, str | None]:
  try:
    return cv2.bilateralFilter(gray, d=5, sigmaColor=40, sigmaSpace=40), "bilateral_denoise", None
  except Exception:
    try:
      return cv2.GaussianBlur(gray, (3, 3), 0), "gaussian_denoise", "Bilateral filter failed; used Gaussian blur."
    except Exception:
      return gray, None, "Noise removal failed; skipped."


def apply_clahe(gray, cv2, *, clip_limit: float = 2.0, tile_size: int = 8) -> tuple[Any, str | None, str | None]:
  try:
    clahe = cv2.createCLAHE(
      clipLimit=float(clip_limit),
      tileGridSize=(int(tile_size), int(tile_size)),
    )
    return clahe.apply(gray), "clahe", None
  except Exception:
    return gray, None, "CLAHE failed; skipped."


def histogram_equalization_blend(gray, cv2, *, clahe_weight: float = 0.7) -> tuple[Any, str | None, str | None]:
  try:
    equalized = cv2.equalizeHist(gray)
    blended = cv2.addWeighted(gray, float(clahe_weight), equalized, 1.0 - float(clahe_weight), 0)
    return blended, "histogram_equalization_blend", None
  except Exception:
    return gray, None, "Histogram equalization failed; skipped."


def normalize_brightness(gray, np, *, target_mean: float = 128.0) -> tuple[Any, str | None, str | None]:
  """Shift intensities toward a stable mid-gray mean without hard clipping extremes."""
  try:
    mean = float(np.mean(gray))
    if mean < 1e-3:
      return gray, "brightness_normalization_skipped", None
    shift = float(target_mean) - mean
    if abs(shift) < 2.0:
      return gray, "brightness_normalization_none", None
    # Soft shift: only apply a fraction to avoid washing anatomy
    adjusted = np.clip(gray.astype(np.float32) + shift * 0.65, 0, 255).astype(np.uint8)
    return adjusted, "brightness_normalization", None
  except Exception:
    return gray, None, "Brightness normalization failed; skipped."


def enhance_sharpness(gray, cv2, *, amount: float = 0.45) -> tuple[Any, str | None, str | None]:
  """Mild unsharp mask — keeps edges readable without inventing texture."""
  try:
    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.2)
    sharp = cv2.addWeighted(gray, 1.0 + float(amount), blurred, -float(amount), 0)
    return sharp, "sharpness_enhancement", None
  except Exception:
    return gray, None, "Sharpness enhancement failed; skipped."


def contrast_boost(gray, cv2, *, alpha: float = 1.08, beta: float = 4.0) -> tuple[Any, str | None, str | None]:
  try:
    return cv2.convertScaleAbs(gray, alpha=float(alpha), beta=float(beta)), "contrast_enhancement", None
  except Exception:
    return gray, None, "Contrast enhancement failed; skipped."


def resize_for_model(
  gray,
  cv2,
  *,
  target_max_dim: int,
  target_min_dim: int,
) -> tuple[Any, bool, str | None, str | None]:
  try:
    h, w = gray.shape[:2]
    max_side = max(h, w)
    min_side = min(h, w)
    changed = False

    if max_side > target_max_dim:
      scale = target_max_dim / float(max_side)
      new_w = max(1, int(round(w * scale)))
      new_h = max(1, int(round(h * scale)))
      gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_AREA)
      changed = True
      h, w = gray.shape[:2]
      min_side = min(h, w)

    if min_side < target_min_dim:
      scale = target_min_dim / float(min_side)
      new_w = min(target_max_dim, max(1, int(round(w * scale))))
      new_h = min(target_max_dim, max(1, int(round(h * scale))))
      gray = cv2.resize(gray, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
      changed = True

    return gray, changed, ("resize" if changed else "resize_skipped"), None
  except Exception:
    return gray, False, None, "Resize failed; skipped."


def intensity_normalization_metadata(gray, np) -> dict[str, float]:
  """Return mean/std and 0–1 scale hints for downstream vision models."""
  arr = gray.astype(np.float32)
  mean = float(np.mean(arr))
  std = float(np.std(arr))
  return {
    "mean": round(mean, 3),
    "std": round(std, 3),
    "min": round(float(np.min(arr)), 3),
    "max": round(float(np.max(arr)), 3),
    "normalized_mean": round(mean / 255.0, 5),
    "normalized_std": round(std / 255.0, 5),
  }
