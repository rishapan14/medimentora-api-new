"""Grad-CAM and educational Grad-CAM-proxy generation (Phase 11).

True Grad-CAM needs a differentiable CNN (Torch / Grad-enabled ONNX). Until that
backend exists, ``try_gradcam`` returns a **localized activation proxy** that
mimics class-activation maps: Gaussian peaks at finding regions, weighted by
confidence. Heuristic full-field attention remains the fallback in ``service.py``.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any

from flask import current_app, has_app_context

from app.services.xray.heatmap.regions import (
  highlight_regions_from_findings,
  zone_pixel_box,
)

logger = logging.getLogger(__name__)

HEATMAP_VERSION = "1.1.0"
HEATMAP_METHOD_HEURISTIC = "heuristic_attention"
HEATMAP_METHOD_GRADCAM = "gradcam"
HEATMAP_METHOD_GRADCAM_PROXY = "gradcam_proxy"


def try_true_gradcam(image_path: str) -> Any | None:
  """
  Reserved hook for real CNN Grad-CAM.

  Returns a HeatmapResult when a Torch/ONNX Grad-CAM backend is wired; else None.
  """
  _ = image_path
  # No Torch chest Grad-CAM backend yet.
  return None


def generate_gradcam_proxy(
  image_path: str,
  *,
  xray_id: int | None = None,
  findings: list[Any] | None = None,
  features: dict[str, Any] | None = None,
  body_part: str | None = None,
  heatmap_folder: str | None = None,
) -> Any:
  """
  Build an educational Grad-CAM-style activation map (localized peaks).

  Returns HeatmapResult (imported lazily to avoid circular imports at module load).
  """
  from app.services.xray.heatmap.service import HeatmapResult

  started = time.perf_counter()
  try:
    import cv2
    import numpy as np
  except ImportError:
    return HeatmapResult(
      success=False,
      message="OpenCV/NumPy required for Grad-CAM proxy.",
      error_code="opencv_missing",
      processing_time_ms=_ms(started),
    )

  gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
  if gray is None:
    return HeatmapResult(
      success=False,
      message="Could not read image for Grad-CAM proxy.",
      error_code="unreadable_image",
      processing_time_ms=_ms(started),
    )

  h, w = gray.shape[:2]
  att = np.zeros((h, w), dtype="float32")

  # Mild base from intensity deviation so empty findings still show structure
  norm = gray.astype("float32") / 255.0
  mean = float(np.mean(norm))
  att += np.abs(norm - mean) * 0.12

  mid_x = w // 2
  left_m = float(np.mean(norm[:, :mid_x])) if mid_x > 0 else 0.0
  right_m = float(np.mean(norm[:, mid_x:])) if mid_x < w else 0.0

  yy, xx = np.mgrid[0:h, 0:w].astype("float32")

  peaks_added = 0
  for item in findings or []:
    if not isinstance(item, dict):
      continue
    region = (item.get("region") or "").strip().lower()
    label = (item.get("label") or "").lower()
    try:
      prob = float(item.get("probability") or item.get("score") or 0.4)
    except (TypeError, ValueError):
      prob = 0.4
    prob = max(0.15, min(1.0, prob))

    cx, cy, sigma_x, sigma_y = _peak_params(
      region,
      label,
      h,
      w,
      mid_x,
      left_m,
      right_m,
    )
    # Confidence-weighted Gaussian activation (Grad-CAM-like)
    gauss = np.exp(
      -(((xx - cx) ** 2) / (2 * sigma_x**2) + ((yy - cy) ** 2) / (2 * sigma_y**2))
    ).astype("float32")
    att += gauss * (0.55 + 0.9 * prob)
    peaks_added += 1

  # Feature zones: top intensity zones get secondary peaks
  zone_means = (features or {}).get("zone_means") or {}
  if zone_means and peaks_added < 2:
    ranked = sorted(zone_means.items(), key=lambda kv: kv[1], reverse=True)
    for zone, _ in ranked[:2]:
      box = zone_pixel_box(zone, h, w)
      if not box:
        continue
      y0, x0, y1, x1 = box
      cx = (x0 + x1) / 2.0
      cy = (y0 + y1) / 2.0
      sigma_x = max((x1 - x0) / 3.0, w * 0.08)
      sigma_y = max((y1 - y0) / 3.0, h * 0.08)
      gauss = np.exp(
        -(((xx - cx) ** 2) / (2 * sigma_x**2) + ((yy - cy) ** 2) / (2 * sigma_y**2))
      ).astype("float32")
      att += gauss * 0.45
      peaks_added += 1

  if peaks_added == 0:
    # Centered soft activation when no findings
    cx, cy = w / 2.0, h / 2.0
    sigma_x, sigma_y = w * 0.28, h * 0.28
    att += np.exp(
      -(((xx - cx) ** 2) / (2 * sigma_x**2) + ((yy - cy) ** 2) / (2 * sigma_y**2))
    ).astype("float32") * 0.5

  # Normalize
  att -= float(att.min())
  denom = float(att.max()) - float(att.min())
  if denom < 1e-6:
    att = np.zeros_like(att)
  else:
    att /= denom

  att_u8 = (att * 255.0).astype("uint8")
  att_u8 = cv2.GaussianBlur(att_u8, (21, 21), 0)
  heat_bgr = cv2.applyColorMap(att_u8, cv2.COLORMAP_JET)
  heat_rgba = cv2.cvtColor(heat_bgr, cv2.COLOR_BGR2BGRA)
  heat_rgba[:, :, 3] = att_u8

  base_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
  overlay_bgr = cv2.addWeighted(base_bgr, 0.55, heat_bgr, 0.45, 0)

  out_dir = heatmap_folder or _default_folder()
  os.makedirs(out_dir, exist_ok=True)
  stem = f"xray_{xray_id}" if xray_id is not None else f"xray_{uuid.uuid4().hex[:12]}"
  heatmap_path = os.path.join(out_dir, f"{stem}_heatmap.png")
  overlay_path = os.path.join(out_dir, f"{stem}_overlay.png")

  if not cv2.imwrite(heatmap_path, heat_rgba):
    return HeatmapResult(
      success=False,
      message="Failed to write Grad-CAM proxy heatmap.",
      error_code="write_failed",
      processing_time_ms=_ms(started),
    )
  cv2.imwrite(overlay_path, overlay_bgr)

  regions = highlight_regions_from_findings(findings, height=h, width=w)
  # Resolve auto-side boxes for asymmetric findings
  for r in regions:
    box = r.get("box_pct") or {}
    if box.get("side") == "auto":
      use_left = left_m >= right_m
      box["x"] = 0.0 if use_left else 50.0
      box["w"] = 50.0
      box["side"] = "left" if use_left else "right"
      r["box_pct"] = box

  return HeatmapResult(
    success=True,
    heatmap_path=heatmap_path,
    overlay_path=overlay_path,
    method=HEATMAP_METHOD_GRADCAM_PROXY,
    width=w,
    height=h,
    processing_time_ms=_ms(started),
    message=(
      "Educational Grad-CAM-style activation map generated "
      "(localized confidence-weighted peaks; not true CNN Grad-CAM)."
    ),
    meta={
      "body_part": body_part,
      "highlighted_regions": regions,
      "gradcam_available": False,
      "gradcam_backend": None,
      "proxy": True,
      "peaks": peaks_added,
      "colormap": "JET",
      "alpha_channel": True,
      "version": HEATMAP_VERSION,
    },
  )


def try_gradcam(
  image_path: str,
  *,
  xray_id: int | None = None,
  findings: list[Any] | None = None,
  features: dict[str, Any] | None = None,
  body_part: str | None = None,
  heatmap_folder: str | None = None,
) -> Any | None:
  """Attempt true Grad-CAM, then educational proxy. Returns HeatmapResult or None."""
  true_cam = try_true_gradcam(image_path)
  if true_cam is not None:
    return true_cam

  proxy = generate_gradcam_proxy(
    image_path,
    xray_id=xray_id,
    findings=findings,
    features=features,
    body_part=body_part,
    heatmap_folder=heatmap_folder,
  )
  if getattr(proxy, "success", False):
    return proxy
  logger.warning("Grad-CAM proxy failed: %s", getattr(proxy, "message", ""))
  return None


def _peak_params(
  region: str,
  label: str,
  h: int,
  w: int,
  mid_x: int,
  left_m: float,
  right_m: float,
) -> tuple[float, float, float, float]:
  """Return (cx, cy, sigma_x, sigma_y) for a finding peak."""
  if region == "asymmetric_lung_zone" or "opacity" in label or "pneumonia" in label:
    if left_m >= right_m:
      cx = mid_x * 0.5
    else:
      cx = mid_x + (w - mid_x) * 0.5
    cy = h * 0.45
    return cx, cy, max(w * 0.18, 8.0), max(h * 0.22, 8.0)

  box = zone_pixel_box(region, h, w) if region else None
  if box:
    y0, x0, y1, x1 = box
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    return cx, cy, max((x1 - x0) / 3.5, w * 0.08), max((y1 - y0) / 3.5, h * 0.08)

  if "fracture" in label:
    return w * 0.5, h * 0.5, w * 0.2, h * 0.2

  return w * 0.5, h * 0.45, w * 0.25, h * 0.25


def _default_folder() -> str:
  if has_app_context():
    return current_app.config.get("XRAY_HEATMAP_FOLDER") or os.path.join(
      "uploads", "xrays", "heatmaps"
    )
  return os.path.join("uploads", "xrays", "heatmaps")


def _ms(started: float) -> int:
  return int((time.perf_counter() - started) * 1000)
