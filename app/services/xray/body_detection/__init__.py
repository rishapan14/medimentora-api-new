"""Automatic body-part detection for educational X-ray analysis (Phase 4).

Architecture allows swapping heuristic → ONNX/Torch models later.
Never claims a diagnosis — only suggests anatomic region for learning workflows.
"""

from app.services.xray.body_detection.detector import (
  BODY_PART_LABELS,
  BodyPartDetectionResult,
  BodyPartDetector,
  HeuristicBodyPartDetector,
  get_detector,
)

__all__ = [
  "BODY_PART_LABELS",
  "BodyPartDetectionResult",
  "BodyPartDetector",
  "HeuristicBodyPartDetector",
  "get_detector",
]
