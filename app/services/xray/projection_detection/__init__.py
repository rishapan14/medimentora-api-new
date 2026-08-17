"""Automatic radiographic projection detection (Phase 5).

Educational routing only — never a diagnosis.
"""

from app.services.xray.projection_detection.detector import (
  PROJECTION_LABELS,
  HeuristicProjectionDetector,
  ProjectionDetectionResult,
  ProjectionDetector,
  get_projection_detector,
)

__all__ = [
  "PROJECTION_LABELS",
  "HeuristicProjectionDetector",
  "ProjectionDetectionResult",
  "ProjectionDetector",
  "get_projection_detector",
]
