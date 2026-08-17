"""Body-part classifiers for educational radiograph routing (Phase 4).

Supported labels (with confidence):
  Chest, Hand, Leg, Foot, Spine, Shoulder, Pelvis, Dental, Knee

The default backend is a lightweight OpenCV heuristic. Future models can
implement ``BodyPartDetector`` and register via ``get_detector()``.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

BODY_PART_LABELS: tuple[str, ...] = (
  "Chest",
  "Hand",
  "Leg",
  "Foot",
  "Spine",
  "Shoulder",
  "Pelvis",
  "Dental",
  "Knee",
)

# Map close clinical form labels → Phase 4 detector vocabulary
_ALIAS_TO_CANONICAL = {
  "chest": "Chest",
  "thorax": "Chest",
  "hand": "Hand",
  "finger": "Hand",
  "wrist": "Hand",
  "leg": "Leg",
  "femur": "Leg",
  "ankle": "Foot",
  "foot": "Foot",
  "spine": "Spine",
  "shoulder": "Shoulder",
  "clavicle": "Shoulder",
  "pelvis": "Pelvis",
  "hip": "Pelvis",
  "dental": "Dental",
  "skull": "Dental",
  "knee": "Knee",
  "elbow": "Hand",
}


@dataclass
class BodyPartCandidate:
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
class BodyPartDetectionResult:
  success: bool
  body_part: str | None = None
  confidence: float = 0.0
  candidates: list[BodyPartCandidate] = field(default_factory=list)
  features: dict[str, Any] = field(default_factory=dict)
  model_name: str = "heuristic_body_part_v1"
  message: str = ""
  error_code: str | None = None
  version: str = "phase4-v1"

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "body_part": self.body_part,
      "confidence": round(float(self.confidence), 4),
      "candidates": [c.to_dict() for c in self.candidates],
      "features": self.features,
      "model_name": self.model_name,
      "message": self.message,
      "error_code": self.error_code,
      "version": self.version,
      "disclaimer": (
        "Automatic body-part detection is educational decision-support only. "
        "It is not a diagnosis and may disagree with clinical labeling."
      ),
    }


class BodyPartDetector(ABC):
  """Interface for body-part classifiers (heuristic or neural)."""

  name: str = "base"

  @abstractmethod
  def detect(self, image_path: str) -> BodyPartDetectionResult:
    raise NotImplementedError

  @staticmethod
  def canonicalize(label: str | None) -> str | None:
    if not label:
      return None
    key = label.strip().lower()
    if key in _ALIAS_TO_CANONICAL:
      return _ALIAS_TO_CANONICAL[key]
    for part in BODY_PART_LABELS:
      if part.lower() == key:
        return part
    return None


class HeuristicBodyPartDetector(BodyPartDetector):
  """Geometry + intensity heuristics for educational body-part suggestions."""

  name = "heuristic_body_part_v1"

  def detect(self, image_path: str) -> BodyPartDetectionResult:
    if not image_path or not os.path.isfile(image_path):
      return BodyPartDetectionResult(
        success=False,
        message="Image not found for body-part detection.",
        error_code="missing_file",
        model_name=self.name,
      )

    try:
      import cv2
      import numpy as np
    except ImportError:
      return BodyPartDetectionResult(
        success=False,
        message="OpenCV is required for body-part detection.",
        error_code="opencv_missing",
        model_name=self.name,
      )

    try:
      gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
      if gray is None:
        return BodyPartDetectionResult(
          success=False,
          message="Could not read image for body-part detection.",
          error_code="unreadable_image",
          model_name=self.name,
        )
      features = self._extract_features(gray, cv2, np)
      scores = self._score_parts(features)
      ranked = sorted(scores.items(), key=lambda kv: kv[1]["score"], reverse=True)
      candidates = [
        BodyPartCandidate(
          label=label,
          confidence=float(info["score"]),
          rationale=info.get("rationale"),
        )
        for label, info in ranked[:5]
        if info["score"] > 0.05
      ]
      if not candidates:
        return BodyPartDetectionResult(
          success=True,
          body_part=None,
          confidence=0.0,
          candidates=[],
          features=features,
          model_name=self.name,
          message="Could not confidently classify body part.",
        )

      top = candidates[0]
      # Softmax-ish calibration across top scores
      raw = np.array([c.confidence for c in candidates], dtype=np.float64)
      exp = np.exp(raw - raw.max())
      probs = exp / (exp.sum() + 1e-9)
      for i, c in enumerate(candidates):
        c.confidence = float(probs[i])

      return BodyPartDetectionResult(
        success=True,
        body_part=top.label,
        confidence=float(candidates[0].confidence),
        candidates=candidates,
        features=features,
        model_name=self.name,
        message=f"Suggested body part: {candidates[0].label} ({candidates[0].confidence:.0%} confidence).",
      )
    except Exception as exc:
      logger.exception("Body-part detection failed: %s", exc)
      return BodyPartDetectionResult(
        success=False,
        message="Body-part detection failed unexpectedly.",
        error_code="detect_failed",
        model_name=self.name,
      )

  def _extract_features(self, gray, cv2, np) -> dict[str, Any]:
    h, w = gray.shape[:2]
    aspect = w / max(h, 1)
    mean = float(np.mean(gray))
    std = float(np.std(gray))

    # Content bounding box fill
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(mask)
    if coords is not None:
      x, y, bw, bh = cv2.boundingRect(coords)
      fill = (bw * bh) / float(max(w * h, 1))
      content_aspect = bw / max(bh, 1)
    else:
      fill, content_aspect = 1.0, aspect
      x = y = 0
      bw, bh = w, h

    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    ex = float(np.mean(np.abs(gx)))
    ey = float(np.mean(np.abs(gy)))
    edge_ratio = ey / (ex + 1e-6)

    # Central vs peripheral brightness (chest lungs tend to darken sides)
    third_w = max(1, w // 3)
    left = float(np.mean(gray[:, :third_w]))
    mid = float(np.mean(gray[:, third_w : 2 * third_w]))
    right = float(np.mean(gray[:, 2 * third_w :]))
    side_darker = mid - 0.5 * (left + right)

    # High-frequency energy (bones / teeth)
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Compactness / circularity hint for dental / joints
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    circularity = 0.0
    if contours:
      c = max(contours, key=cv2.contourArea)
      area = float(cv2.contourArea(c))
      peri = float(cv2.arcLength(c, True))
      if peri > 1:
        circularity = float(4.0 * np.pi * area / (peri * peri))

    # Vertical column energy (spine)
    col_profile = np.mean(gray.astype(np.float32), axis=0)
    row_profile = np.mean(gray.astype(np.float32), axis=1)
    col_peak = float(np.max(col_profile) - np.median(col_profile))
    row_var = float(np.var(row_profile))

    return {
      "width": w,
      "height": h,
      "aspect_ratio": round(aspect, 3),
      "content_aspect": round(float(content_aspect), 3),
      "content_fill": round(float(fill), 3),
      "mean_intensity": round(mean, 2),
      "std_intensity": round(std, 2),
      "edge_energy_x": round(ex, 2),
      "edge_energy_y": round(ey, 2),
      "edge_ratio_yx": round(edge_ratio, 3),
      "side_darker_delta": round(float(side_darker), 2),
      "laplacian_var": round(lap, 2),
      "circularity": round(circularity, 3),
      "column_peak": round(col_peak, 2),
      "row_profile_var": round(row_var, 2),
      "bbox": [int(x), int(y), int(bw), int(bh)],
    }

  def _score_parts(self, f: dict[str, Any]) -> dict[str, dict[str, Any]]:
    aspect = float(f["aspect_ratio"])
    content_aspect = float(f["content_aspect"])
    fill = float(f["content_fill"])
    edge_ratio = float(f["edge_ratio_yx"])
    side_darker = float(f["side_darker_delta"])
    lap = float(f["laplacian_var"])
    circularity = float(f["circularity"])
    col_peak = float(f["column_peak"])
    row_var = float(f["row_profile_var"])
    std = float(f["std_intensity"])
    h = float(f["height"])
    w = float(f["width"])

    scores: dict[str, dict[str, Any]] = {p: {"score": 0.05, "rationale": ""} for p in BODY_PART_LABELS}

    # Chest: near-square / landscape, sides darker than mediastinum, moderate fill
    chest = 0.15
    if 0.75 <= aspect <= 1.45:
      chest += 0.25
    if side_darker > 8:
      chest += 0.3
    if 0.55 <= fill <= 0.98:
      chest += 0.15
    if std > 25:
      chest += 0.1
    scores["Chest"] = {"score": chest, "rationale": "Lateral darkness and thoracic aspect ratio"}

    # Hand: more square/compact, high bone edge energy, often smaller FOV feel via high lap
    hand = 0.1
    if 0.7 <= aspect <= 1.35:
      hand += 0.15
    if lap > 120:
      hand += 0.25
    if circularity > 0.25:
      hand += 0.1
    if fill < 0.85:
      hand += 0.1
    scores["Hand"] = {"score": hand, "rationale": "High bone-edge texture typical of hand/wrist"}

    # Foot: wider than tall often, high edge texture
    foot = 0.08
    if aspect >= 1.15:
      foot += 0.25
    if lap > 100:
      foot += 0.2
    if content_aspect > 1.1:
      foot += 0.15
    scores["Foot"] = {"score": foot, "rationale": "Wide FOV with fine bone detail"}

    # Leg: tall, strong vertical edges
    leg = 0.08
    if aspect <= 0.75 or content_aspect <= 0.8:
      leg += 0.3
    if edge_ratio > 1.05:
      leg += 0.2
    if h > w * 1.15:
      leg += 0.15
    scores["Leg"] = {"score": leg, "rationale": "Elongated vertical anatomy"}

    # Spine: very tall or strong central column peak
    spine = 0.08
    if aspect <= 0.65 or content_aspect <= 0.7:
      spine += 0.25
    if col_peak > 18:
      spine += 0.3
    if edge_ratio > 1.1:
      spine += 0.15
    scores["Spine"] = {"score": spine, "rationale": "Central vertical column energy"}

    # Shoulder: landscape, moderate texture, asymmetric fill
    shoulder = 0.08
    if aspect >= 1.05:
      shoulder += 0.2
    if 40 < lap < 220:
      shoulder += 0.15
    if fill > 0.6:
      shoulder += 0.1
    if side_darker < 12:
      shoulder += 0.1
    scores["Shoulder"] = {"score": shoulder, "rationale": "Wide girdle-style framing"}

    # Pelvis: wide, lower circularity, moderate contrast
    pelvis = 0.08
    if aspect >= 1.1:
      pelvis += 0.25
    if 0.7 <= fill <= 0.98:
      pelvis += 0.15
    if 20 < std < 70:
      pelvis += 0.1
    if circularity < 0.45:
      pelvis += 0.1
    scores["Pelvis"] = {"score": pelvis, "rationale": "Broad transverse anatomy"}

    # Dental: compact, high circularity / high-frequency enamel-like edges
    dental = 0.08
    if 0.75 <= aspect <= 1.4:
      dental += 0.1
    if circularity > 0.35:
      dental += 0.25
    if lap > 150:
      dental += 0.25
    if fill < 0.75:
      dental += 0.1
    scores["Dental"] = {"score": dental, "rationale": "Compact high-frequency dental pattern"}

    # Knee: near-square joint, moderate edges, central bright plateau
    knee = 0.1
    if 0.8 <= aspect <= 1.25:
      knee += 0.2
    if 50 < lap < 200:
      knee += 0.2
    if row_var > 80:
      knee += 0.15
    if 0.55 <= fill <= 0.95:
      knee += 0.1
    scores["Knee"] = {"score": knee, "rationale": "Joint-centered square framing"}

    return scores


def get_detector(name: str | None = None) -> BodyPartDetector:
  """Factory for body-part detectors (extensible for future ML backends)."""
  key = (name or "heuristic").strip().lower()
  if key in ("heuristic", "auto", "heuristic_body_part_v1", ""):
    return HeuristicBodyPartDetector()
  # Future: onnx_chest_router, monai_body_part, etc.
  logger.warning("Unknown body-part detector '%s'; falling back to heuristic", name)
  return HeuristicBodyPartDetector()
