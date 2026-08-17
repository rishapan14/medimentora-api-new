"""Projection classifiers for educational radiograph routing (Phase 5).

Labels (with confidence):
  AP, PA, Lateral, Oblique, Unknown

Default backend is an OpenCV heuristic. Future models can implement
``ProjectionDetector`` and register via ``get_projection_detector()``.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

PROJECTION_LABELS: tuple[str, ...] = (
  "AP",
  "PA",
  "Lateral",
  "Oblique",
  "Unknown",
)

_ALIAS_TO_CANONICAL = {
  "ap": "AP",
  "anteroposterior": "AP",
  "antero-posterior": "AP",
  "pa": "PA",
  "posteroanterior": "PA",
  "postero-anterior": "PA",
  "lateral": "Lateral",
  "lat": "Lateral",
  "oblique": "Oblique",
  "obl": "Oblique",
  "unknown": "Unknown",
  "other": "Unknown",
  "axial": "Unknown",
  "skyline": "Unknown",
}


@dataclass
class ProjectionCandidate:
  label: str
  confidence: float
  rationale: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "label": self.label,
      "confidence": round(float(self.confidence), 4),
      "rationale": self.rationale,
    }


@dataclass
class ProjectionDetectionResult:
  success: bool
  projection: str | None = None
  confidence: float = 0.0
  candidates: list[ProjectionCandidate] = field(default_factory=list)
  features: dict[str, Any] = field(default_factory=dict)
  model_name: str = "heuristic_projection_v1"
  message: str = ""
  error_code: str | None = None
  version: str = "phase5-v1"

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "projection": self.projection,
      "confidence": round(float(self.confidence), 4),
      "candidates": [c.to_dict() for c in self.candidates],
      "features": self.features,
      "model_name": self.model_name,
      "message": self.message,
      "error_code": self.error_code,
      "version": self.version,
      "disclaimer": (
        "Automatic projection detection is educational decision-support only. "
        "It is not a diagnosis and may disagree with clinical labeling."
      ),
    }


class ProjectionDetector(ABC):
  name: str = "base"

  @abstractmethod
  def detect(self, image_path: str, *, body_part: str | None = None) -> ProjectionDetectionResult:
    raise NotImplementedError

  @staticmethod
  def canonicalize(label: str | None) -> str | None:
    if not label:
      return None
    key = label.strip().lower()
    if key in _ALIAS_TO_CANONICAL:
      return _ALIAS_TO_CANONICAL[key]
    for part in PROJECTION_LABELS:
      if part.lower() == key:
        return part
    return None


class HeuristicProjectionDetector(ProjectionDetector):
  """Geometry / symmetry heuristics for AP, PA, Lateral, Oblique, Unknown."""

  name = "heuristic_projection_v1"
  min_confident = 0.28

  def detect(self, image_path: str, *, body_part: str | None = None) -> ProjectionDetectionResult:
    if not image_path or not os.path.isfile(image_path):
      return ProjectionDetectionResult(
        success=False,
        message="Image not found for projection detection.",
        error_code="missing_file",
        model_name=self.name,
      )

    try:
      import cv2
      import numpy as np
    except ImportError:
      return ProjectionDetectionResult(
        success=False,
        message="OpenCV is required for projection detection.",
        error_code="opencv_missing",
        model_name=self.name,
      )

    try:
      gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
      if gray is None:
        return ProjectionDetectionResult(
          success=False,
          message="Could not read image for projection detection.",
          error_code="unreadable_image",
          model_name=self.name,
        )

      features = self._extract_features(gray, cv2, np)
      features["body_part_hint"] = body_part
      scores = self._score_projections(features, body_part=body_part)

      ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
      candidates = [
        ProjectionCandidate(
          label=label,
          confidence=float(info["score"]),
          rationale=info.get("rationale"),
        )
        for label, info in ranked
        if label != "Unknown" and info["score"] > 0.04
      ]

      if not candidates:
        return ProjectionDetectionResult(
          success=True,
          projection="Unknown",
          confidence=0.5,
          candidates=[
            ProjectionCandidate(label="Unknown", confidence=0.5, rationale="Insufficient cues")
          ],
          features=features,
          model_name=self.name,
          message="Projection could not be determined confidently (Unknown).",
        )

      raw = np.array([c.confidence for c in candidates], dtype=np.float64)
      exp = np.exp(raw - raw.max())
      probs = exp / (exp.sum() + 1e-9)
      for i, c in enumerate(candidates):
        c.confidence = float(probs[i])

      top = candidates[0]
      if top.confidence < self.min_confident:
        unknown = ProjectionCandidate(
          label="Unknown",
          confidence=round(1.0 - top.confidence, 4),
          rationale="Top projection confidence below threshold",
        )
        return ProjectionDetectionResult(
          success=True,
          projection="Unknown",
          confidence=float(unknown.confidence),
          candidates=[unknown, *candidates[:3]],
          features=features,
          model_name=self.name,
          message="Projection uncertain — reported as Unknown.",
        )

      return ProjectionDetectionResult(
        success=True,
        projection=top.label,
        confidence=float(top.confidence),
        candidates=candidates[:4],
        features=features,
        model_name=self.name,
        message=f"Suggested projection: {top.label} ({top.confidence:.0%} confidence).",
      )
    except Exception as exc:
      logger.exception("Projection detection failed: %s", exc)
      return ProjectionDetectionResult(
        success=False,
        message="Projection detection failed unexpectedly.",
        error_code="detect_failed",
        model_name=self.name,
      )

  def _extract_features(self, gray, cv2, np) -> dict[str, Any]:
    h, w = gray.shape[:2]
    aspect = w / max(h, 1)

    left = gray[:, : w // 2]
    right = gray[:, w // 2 :]
    # Left-right symmetry (AP/PA higher; lateral lower)
    if left.shape[1] != right.shape[1]:
      right = right[:, : left.shape[1]]
    flipped = np.fliplr(right.astype(np.float32))
    sym_err = float(np.mean(np.abs(left.astype(np.float32) - flipped)))
    symmetry = 1.0 / (1.0 + sym_err / 40.0)

    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    # Diagonal energy for oblique
    g45 = cv2.Sobel(gray, cv2.CV_64F, 1, 1, ksize=3)
    ex = float(np.mean(np.abs(gx)))
    ey = float(np.mean(np.abs(gy)))
    ediag = float(np.mean(np.abs(g45)))
    edge_ratio = ey / (ex + 1e-6)
    diag_ratio = ediag / ((ex + ey) / 2.0 + 1e-6)

    mean = float(np.mean(gray))
    std = float(np.std(gray))
    # Clavicle / upper vs lower brightness (soft PA vs AP cue)
    upper = float(np.mean(gray[: h // 3, :]))
    lower = float(np.mean(gray[2 * h // 3 :, :]))
    upper_lower_delta = upper - lower

    # Central column prominence (lateral ribs / mediastinum side view)
    col = np.mean(gray.astype(np.float32), axis=0)
    col_peak = float(np.max(col) - np.median(col))
    col_argmax = int(np.argmax(col))
    col_center_bias = abs(col_argmax - w / 2.0) / max(w / 2.0, 1.0)

    return {
      "width": w,
      "height": h,
      "aspect_ratio": round(aspect, 3),
      "lr_symmetry": round(symmetry, 3),
      "lr_symmetry_error": round(sym_err, 2),
      "edge_ratio_yx": round(edge_ratio, 3),
      "diag_edge_ratio": round(diag_ratio, 3),
      "mean_intensity": round(mean, 2),
      "std_intensity": round(std, 2),
      "upper_lower_delta": round(upper_lower_delta, 2),
      "column_peak": round(col_peak, 2),
      "column_center_bias": round(col_center_bias, 3),
    }

  def _score_projections(
    self, f: dict[str, Any], *, body_part: str | None
  ) -> dict[str, dict[str, Any]]:
    sym = float(f["lr_symmetry"])
    aspect = float(f["aspect_ratio"])
    edge_ratio = float(f["edge_ratio_yx"])
    diag = float(f["diag_edge_ratio"])
    upper_lower = float(f["upper_lower_delta"])
    col_bias = float(f["column_center_bias"])
    col_peak = float(f["column_peak"])
    part = (body_part or "").strip().lower()

    scores: dict[str, dict[str, Any]] = {
      label: {"score": 0.05, "rationale": ""} for label in PROJECTION_LABELS
    }

    # Lateral: low L-R symmetry, often portrait/square, off-center column
    lateral = 0.1
    if sym < 0.55:
      lateral += 0.35
    elif sym < 0.7:
      lateral += 0.15
    if aspect <= 1.05:
      lateral += 0.15
    if col_bias > 0.15:
      lateral += 0.2
    if edge_ratio > 1.0:
      lateral += 0.1
    if part in ("spine", "chest"):
      lateral += 0.05
    scores["Lateral"] = {"score": lateral, "rationale": "Low left-right symmetry / side-view cues"}

    # Oblique: moderate asymmetry + elevated diagonal edges
    oblique = 0.08
    if 0.55 <= sym <= 0.82:
      oblique += 0.25
    if diag > 0.85:
      oblique += 0.3
    if 0.15 < col_bias < 0.45:
      oblique += 0.15
    scores["Oblique"] = {"score": oblique, "rationale": "Moderate asymmetry with diagonal edge energy"}

    # Frontal family (AP/PA): high symmetry
    frontal_base = 0.1
    if sym >= 0.75:
      frontal_base += 0.35
    elif sym >= 0.65:
      frontal_base += 0.2
    if aspect >= 0.85:
      frontal_base += 0.1
    if col_bias < 0.2:
      frontal_base += 0.1

    # Soft PA vs AP split (educational only — unreliable without markers)
    pa = frontal_base
    ap = frontal_base
    if upper_lower < -5:
      # Lower thorax brighter relative — weak PA-like cue
      pa += 0.12
      ap += 0.04
    elif upper_lower > 8:
      ap += 0.12
      pa += 0.04
    else:
      ap += 0.08
      pa += 0.08
    if col_peak > 25 and sym > 0.7:
      pa += 0.05
    scores["PA"] = {"score": pa, "rationale": "High symmetry frontal pattern (PA-leaning cues)"}
    scores["AP"] = {"score": ap, "rationale": "High symmetry frontal pattern (AP-leaning cues)"}

    # Unknown stays low unless others are weak (handled by threshold)
    scores["Unknown"] = {"score": 0.05, "rationale": "Fallback when cues conflict"}

    return scores


def get_projection_detector(name: str | None = None) -> ProjectionDetector:
  key = (name or "heuristic").strip().lower()
  if key in ("heuristic", "auto", "heuristic_projection_v1", ""):
    return HeuristicProjectionDetector()
  logger.warning("Unknown projection detector '%s'; falling back to heuristic", name)
  return HeuristicProjectionDetector()
