"""Educational attention / Grad-CAM heatmap package (Phase 11).

Public API stays import-compatible:

  from app.services.xray.heatmap import HeatmapService
"""

from app.services.xray.heatmap.gradcam import (
  HEATMAP_METHOD_GRADCAM,
  HEATMAP_METHOD_GRADCAM_PROXY,
  HEATMAP_METHOD_HEURISTIC,
  HEATMAP_VERSION,
  generate_gradcam_proxy,
  try_gradcam,
  try_true_gradcam,
)
from app.services.xray.heatmap.regions import (
  highlight_regions_from_findings,
  region_names_from_findings,
  zone_pixel_box,
)
from app.services.xray.heatmap.service import HeatmapResult, HeatmapService

__all__ = [
  "HEATMAP_METHOD_GRADCAM",
  "HEATMAP_METHOD_GRADCAM_PROXY",
  "HEATMAP_METHOD_HEURISTIC",
  "HEATMAP_VERSION",
  "HeatmapResult",
  "HeatmapService",
  "generate_gradcam_proxy",
  "highlight_regions_from_findings",
  "region_names_from_findings",
  "try_gradcam",
  "try_true_gradcam",
  "zone_pixel_box",
]
