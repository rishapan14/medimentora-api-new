"""Multi-region highlight helpers for educational attention / Grad-CAM maps (Phase 11)."""

from __future__ import annotations

from typing import Any


ZONE_BOXES_NORM = {
  # y0, x0, y1, x1 as fractions of height/width
  "upper_left": (0.0, 0.0, 0.5, 0.5),
  "upper_right": (0.0, 0.5, 0.5, 1.0),
  "lower_left": (0.5, 0.0, 1.0, 0.5),
  "lower_right": (0.5, 0.5, 1.0, 1.0),
  "center": (0.25, 0.25, 0.75, 0.75),
  "lower_lung_zones": (0.5, 0.0, 1.0, 1.0),
  "cardiac_silhouette": (0.25, 0.25, 0.75, 0.75),
  "lung": (0.1, 0.05, 0.85, 0.95),
  "global": (0.0, 0.0, 1.0, 1.0),
}


def zone_pixel_box(region: str, h: int, w: int) -> tuple[int, int, int, int] | None:
  """Return (y0, x0, y1, x1) pixel box for a named region, or None."""
  key = (region or "").strip().lower()
  frac = ZONE_BOXES_NORM.get(key)
  if not frac:
    return None
  y0, x0, y1, x1 = frac
  return (
    int(y0 * h),
    int(x0 * w),
    int(y1 * h),
    int(x1 * w),
  )


def highlight_regions_from_findings(
  findings: list[Any] | None,
  *,
  height: int,
  width: int,
) -> list[dict[str, Any]]:
  """
  Build UI-friendly multi-region highlights with normalized boxes + confidence.

  Boxes use percentages (0–100) so the frontend can overlay without knowing
  native image dimensions.
  """
  out: list[dict[str, Any]] = []
  mid_x_pct = 50.0

  for item in findings or []:
    if not isinstance(item, dict):
      continue
    label = str(item.get("label") or "Finding").strip()
    region = str(item.get("region") or "").strip()
    try:
      confidence = float(item.get("probability") or item.get("score") or 0.4)
    except (TypeError, ValueError):
      confidence = 0.4
    confidence = max(0.0, min(1.0, confidence))

    region_l = region.lower()
    label_l = label.lower()

    if region_l == "asymmetric_lung_zone" or "opacity" in label_l or "pneumonia" in label_l:
      # Full hemithorax placeholder — exact side resolved at map-build time
      box = {"x": 0.0, "y": 0.0, "w": mid_x_pct, "h": 100.0, "side": "auto"}
      region_key = region or "asymmetric_lung_zone"
    else:
      pix = zone_pixel_box(region, height, width) if region else None
      if pix is None and "fracture" in label_l:
        box = {"x": 20.0, "y": 20.0, "w": 60.0, "h": 60.0, "side": None}
        region_key = region or "edge_focus"
      elif pix is None:
        continue
      else:
        y0, x0, y1, x1 = pix
        box = {
          "x": round(100.0 * x0 / max(width, 1), 2),
          "y": round(100.0 * y0 / max(height, 1), 2),
          "w": round(100.0 * (x1 - x0) / max(width, 1), 2),
          "h": round(100.0 * (y1 - y0) / max(height, 1), 2),
          "side": None,
        }
        region_key = region

    out.append(
      {
        "id": f"r{len(out) + 1}",
        "label": label,
        "region": region_key,
        "confidence": round(confidence, 4),
        "box_pct": box,
      }
    )
    if len(out) >= 8:
      break

  return out


def region_names_from_findings(findings: list[Any] | None) -> list[str]:
  names: list[str] = []
  for item in findings or []:
    if isinstance(item, dict) and item.get("region"):
      names.append(str(item["region"]))
  return names[:8]
