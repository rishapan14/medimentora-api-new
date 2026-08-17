"""Educational attention / Grad-CAM heatmap service (Phase 11).

True Grad-CAM requires differentiable CNN gradients. Until an ONNX/Torch chest
model is wired, ``prefer_gradcam=True`` uses a localized Grad-CAM **proxy**,
with heuristic full-field attention as fallback.

Safety: heatmaps are visualization aids for learning — not proof of pathology.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from flask import current_app, has_app_context

from app.extensions import db
from app.models.xray_analysis_model import XrayAnalysis
from app.services.xray.heatmap.gradcam import (
  HEATMAP_METHOD_GRADCAM,
  HEATMAP_METHOD_GRADCAM_PROXY,
  HEATMAP_METHOD_HEURISTIC,
  HEATMAP_VERSION,
  try_gradcam,
)
from app.services.xray.heatmap.regions import (
  highlight_regions_from_findings,
  region_names_from_findings,
  zone_pixel_box,
)
from app.utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class HeatmapResult:
  """Result of generating an educational attention / Grad-CAM heatmap."""

  success: bool
  heatmap_path: str | None = None
  overlay_path: str | None = None
  method: str = HEATMAP_METHOD_HEURISTIC
  width: int = 0
  height: int = 0
  processing_time_ms: int = 0
  message: str = ""
  error_code: str | None = None
  meta: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict:
    is_gradcam_family = self.method in (
      HEATMAP_METHOD_GRADCAM,
      HEATMAP_METHOD_GRADCAM_PROXY,
    )
    return {
      "success": self.success,
      "heatmap_path": self.heatmap_path,
      "overlay_path": self.overlay_path,
      "method": self.method,
      "width": self.width,
      "height": self.height,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "error_code": self.error_code,
      "heatmap_version": HEATMAP_VERSION,
      "meta": self.meta,
      "ui_hints": {
        "supports_opacity_slider": True,
        "supports_toggle": True,
        "supports_download": True,
        "supports_region_labels": True,
        "default_opacity": 0.45,
        "blend_mode": "screen_or_multiply",
        "note": (
          "Serve original + heatmap separately so the client can opacity-blend "
          "and toggle the overlay."
        ),
      },
      "safety": {
        "is_gradcam": self.method == HEATMAP_METHOD_GRADCAM,
        "is_gradcam_proxy": self.method == HEATMAP_METHOD_GRADCAM_PROXY,
        "gradcam_family": is_gradcam_family,
        "educational_only": True,
        "note": (
          "Attention maps highlight regions of algorithmic focus, not confirmed disease."
        ),
      },
    }

  def meta_for_storage(self) -> dict[str, Any]:
    """Compact JSON persisted on xray_analysis.heatmap_meta."""
    return {
      "method": self.method,
      "version": HEATMAP_VERSION,
      "width": self.width,
      "height": self.height,
      "processing_time_ms": self.processing_time_ms,
      "highlighted_regions": (self.meta or {}).get("highlighted_regions") or [],
      "colormap": (self.meta or {}).get("colormap") or "JET",
      "proxy": bool((self.meta or {}).get("proxy")),
      "gradcam_available": bool((self.meta or {}).get("gradcam_available")),
      "message": self.message,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
      },
    }


class HeatmapService:
  """Generate and persist educational X-ray attention / Grad-CAM heatmaps."""

  @classmethod
  def generate_for_user(
    cls,
    xray_id: int,
    user_id: int,
    *,
    force: bool = False,
    features: dict[str, Any] | None = None,
    prefer_gradcam: bool = True,
  ) -> tuple[XrayAnalysis | None, HeatmapResult]:
    """Generate heatmap for an owned X-ray and persist heatmap_path + heatmap_meta."""
    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, HeatmapResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
      )

    if (
      not force
      and row.heatmap_path
      and os.path.isfile(row.heatmap_path)
    ):
      cached_meta = getattr(row, "heatmap_meta", None) or {}
      return row, HeatmapResult(
        success=True,
        heatmap_path=row.heatmap_path,
        method=str(cached_meta.get("method") or HEATMAP_METHOD_HEURISTIC),
        message="Using existing heatmap.",
        meta={"cached": True, **(cached_meta if isinstance(cached_meta, dict) else {})},
      )

    image_path = None
    if row.preprocessed_path and os.path.isfile(row.preprocessed_path):
      image_path = row.preprocessed_path
    elif row.file_path and os.path.isfile(row.file_path):
      image_path = row.file_path

    if not image_path:
      return row, HeatmapResult(
        success=False,
        message="No image available for heatmap generation.",
        error_code="missing_image",
      )

    result = cls.generate(
      image_path,
      xray_id=row.id,
      findings=row.possible_findings,
      features=features,
      body_part=row.body_part,
      prefer_gradcam=prefer_gradcam,
    )
    if not result.success:
      return row, result

    if row.heatmap_path and row.heatmap_path != result.heatmap_path:
      cls._safe_unlink(row.heatmap_path)
      overlay_old = row.heatmap_path.replace("_heatmap.png", "_overlay.png")
      if overlay_old != row.heatmap_path:
        cls._safe_unlink(overlay_old)

    row.heatmap_path = result.heatmap_path
    row.heatmap_meta = result.meta_for_storage()
    row.updated_at = utc_now()
    db.session.commit()

    logger.info(
      "Heatmap OK id=%s method=%s path=%s ms=%s",
      xray_id,
      result.method,
      result.heatmap_path,
      result.processing_time_ms,
    )
    return row, result

  @classmethod
  def generate(
    cls,
    image_path: str,
    *,
    xray_id: int | None = None,
    findings: list[Any] | None = None,
    features: dict[str, Any] | None = None,
    body_part: str | None = None,
    prefer_gradcam: bool = True,
  ) -> HeatmapResult:
    """
    Build an attention / Grad-CAM heatmap for the given radiograph.

    When prefer_gradcam=True, tries true Grad-CAM then educational proxy;
    otherwise (or on failure) uses heuristic attention.
    """
    started = time.perf_counter()

    if prefer_gradcam:
      gradcam = try_gradcam(
        image_path,
        xray_id=xray_id,
        findings=findings,
        features=features,
        body_part=body_part,
        heatmap_folder=cls._heatmap_folder(),
      )
      if gradcam is not None:
        return gradcam

    try:
      import cv2
      import numpy as np
    except ImportError:
      return HeatmapResult(
        success=False,
        message="OpenCV/NumPy required for heatmap generation.",
        error_code="opencv_missing",
        processing_time_ms=cls._ms(started),
      )

    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
      return HeatmapResult(
        success=False,
        message="Could not read image for heatmap generation.",
        error_code="unreadable_image",
        processing_time_ms=cls._ms(started),
      )

    h, w = gray.shape[:2]
    attention = cls._build_heuristic_attention(gray, np, findings=findings, features=features)

    att = attention.astype("float32")
    att -= float(att.min())
    denom = float(att.max()) - float(att.min())
    if denom < 1e-6:
      att = np.zeros_like(att)
    else:
      att /= denom

    att_u8 = (att * 255.0).astype("uint8")
    att_u8 = cv2.GaussianBlur(att_u8, (31, 31), 0)

    heat_bgr = cv2.applyColorMap(att_u8, cv2.COLORMAP_JET)
    heat_rgba = cv2.cvtColor(heat_bgr, cv2.COLOR_BGR2BGRA)
    heat_rgba[:, :, 3] = att_u8

    base_bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    overlay_bgr = cv2.addWeighted(base_bgr, 0.55, heat_bgr, 0.45, 0)

    out_dir = cls._heatmap_folder()
    os.makedirs(out_dir, exist_ok=True)
    stem = f"xray_{xray_id}" if xray_id is not None else f"xray_{uuid.uuid4().hex[:12]}"
    heatmap_path = os.path.join(out_dir, f"{stem}_heatmap.png")
    overlay_path = os.path.join(out_dir, f"{stem}_overlay.png")

    if not cv2.imwrite(heatmap_path, heat_rgba):
      return HeatmapResult(
        success=False,
        message="Failed to write heatmap image.",
        error_code="write_failed",
        processing_time_ms=cls._ms(started),
      )
    cv2.imwrite(overlay_path, overlay_bgr)

    regions = highlight_regions_from_findings(findings, height=h, width=w)
    return HeatmapResult(
      success=True,
      heatmap_path=heatmap_path,
      overlay_path=overlay_path,
      method=HEATMAP_METHOD_HEURISTIC,
      width=w,
      height=h,
      processing_time_ms=cls._ms(started),
      message="Educational heuristic attention heatmap generated.",
      meta={
        "body_part": body_part,
        "highlighted_regions": regions,
        "region_names": region_names_from_findings(findings),
        "gradcam_available": False,
        "colormap": "JET",
        "alpha_channel": True,
        "version": HEATMAP_VERSION,
      },
    )

  @classmethod
  def _build_heuristic_attention(
    cls,
    gray,
    np,
    *,
    findings: list[Any] | None,
    features: dict[str, Any] | None,
  ):
    """Zone-weighted attention map guided by findings / features."""
    h, w = gray.shape
    att = np.zeros((h, w), dtype="float32")
    mid_y, mid_x = h // 2, w // 2

    norm = gray.astype("float32") / 255.0
    mean = float(np.mean(norm))
    deviation = np.abs(norm - mean)
    att += deviation * 0.35

    edges_f = None
    try:
      import cv2

      edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 140)
      edges_f = edges.astype("float32") / 255.0
      att += edges_f * 0.2
    except Exception:
      edges_f = None

    left = norm[:, :mid_x]
    right = norm[:, mid_x:]
    left_m = float(np.mean(left)) if left.size else 0.0
    right_m = float(np.mean(right)) if right.size else 0.0
    asymmetry = abs(left_m - right_m)
    if asymmetry > 0.05:
      if left_m > right_m:
        att[:, :mid_x] += 0.25 + asymmetry
      else:
        att[:, mid_x:] += 0.25 + asymmetry

    zone_means = (features or {}).get("zone_means") or {}
    if zone_means:
      ranked = sorted(zone_means.items(), key=lambda kv: kv[1], reverse=True)
      for i, (zone, _) in enumerate(ranked[:2]):
        box = zone_pixel_box(zone, h, w)
        if box:
          y0, x0, y1, x1 = box
          att[y0:y1, x0:x1] += 0.35 - i * 0.1

    for item in findings or []:
      if not isinstance(item, dict):
        continue
      region = (item.get("region") or "").strip().lower()
      prob = float(item.get("probability") or item.get("score") or 0.4)
      label = (item.get("label") or "").lower()

      box = zone_pixel_box(region, h, w) if region else None
      if region == "asymmetric_lung_zone" or "opacity" in label or "pneumonia" in label:
        if left_m >= right_m:
          att[:, :mid_x] += 0.3 * prob
        else:
          att[:, mid_x:] += 0.3 * prob
      elif box:
        y0, x0, y1, x1 = box
        att[y0:y1, x0:x1] += 0.4 * max(prob, 0.2)
      elif "fracture" in label and edges_f is not None:
        att += edges_f * (0.5 * prob)

    yy, xx = np.mgrid[0:h, 0:w]
    cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
    ry, rx = max(h / 2.0, 1.0), max(w / 2.0, 1.0)
    radial = 1.0 - (((yy - cy) / ry) ** 2 + ((xx - cx) / rx) ** 2)
    radial = np.clip(radial, 0.15, 1.0).astype("float32")
    att *= radial

    return att

  @classmethod
  def _try_gradcam(cls, image_path: str) -> HeatmapResult | None:
    """Back-compat hook — prefer ``try_gradcam`` with findings when possible."""
    return try_gradcam(image_path, heatmap_folder=cls._heatmap_folder())

  @classmethod
  def _heatmap_folder(cls) -> str:
    if has_app_context():
      return current_app.config.get("XRAY_HEATMAP_FOLDER") or os.path.join(
        "uploads", "xrays", "heatmaps"
      )
    return os.path.join("uploads", "xrays", "heatmaps")

  @staticmethod
  def _safe_unlink(path: str | None) -> None:
    if not path:
      return
    try:
      if os.path.isfile(path):
        os.remove(path)
    except OSError:
      logger.warning("Could not remove old heatmap: %s", path)

  @staticmethod
  def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
