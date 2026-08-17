"""Medical vision model interface and implementations (Module 4).

Interchangeable backends for AI-assisted X-ray finding detection.
All outputs are educational / decision-support only — never definitive diagnoses.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

ANALYSIS_VERSION = "1.0.0"

# Educational finding labels (never definitive diagnoses)
FINDING_NO_ABNORMALITY = "No obvious abnormality detected"
FINDING_LUNG_OPACITY = "Possible Lung Opacity"
FINDING_PNEUMONIA = "Possible Pneumonia"
FINDING_EFFUSION = "Possible Pleural Effusion"
FINDING_CARDIOMEGALY = "Possible Cardiomegaly"
FINDING_FRACTURE = "Possible Fracture"


@dataclass
class FindingCandidate:
  """One possible educational finding with probability."""

  label: str
  probability: float
  region: str | None = None
  rationale: str | None = None  # technical image-feature rationale (not a diagnosis)

  def to_dict(self) -> dict:
    return {
      "label": self.label,
      "probability": round(float(self.probability), 4),
      "region": self.region,
      "rationale": self.rationale,
      "certainty": "possible",  # hard-coded safety marker
    }


@dataclass
class VisionAnalysisResult:
  """Structured vision-model output."""

  success: bool
  possible_findings: list[FindingCandidate] = field(default_factory=list)
  confidence: float = 0.0
  body_part: str | None = None
  model_name: str = "unknown"
  analysis_version: str = ANALYSIS_VERSION
  processing_time_ms: int = 0
  message: str = ""
  error_code: str | None = None
  raw_features: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "possible_findings": [f.to_dict() for f in self.possible_findings],
      "confidence": round(float(self.confidence), 4),
      "body_part": self.body_part,
      "model_name": self.model_name,
      "analysis_version": self.analysis_version,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "error_code": self.error_code,
      "raw_features": self.raw_features,
      "safety": {
        "definitive_diagnosis": False,
        "wording": "possible_findings_only",
        "note": (
          "Findings are possible observations for educational support only "
          "and must be interpreted by a qualified clinician."
        ),
      },
    }


class BaseVisionModel(ABC):
  """Abstract medical vision backend — swap implementations without changing callers."""

  name: str = "base"
  version: str = ANALYSIS_VERSION

  @abstractmethod
  def analyze(self, image_path: str, body_part: str | None = None) -> VisionAnalysisResult:
    """Analyze a (preferably preprocessed) radiograph and return structured findings."""

  @abstractmethod
  def is_available(self) -> bool:
    """Return True if this backend can run in the current environment."""


class HeuristicRadiographModel(BaseVisionModel):
  """
  Educational OpenCV/NumPy heuristic model (always available).

  Uses intensity / asymmetry / silhouette cues as *soft signals* only.
  Not a clinical diagnostic model. Suitable as a default until an ONNX/Torch
  chest model is plugged into the registry.
  """

  name = "medimentora-heuristic-radiograph-v1"
  version = ANALYSIS_VERSION

  def is_available(self) -> bool:
    try:
      import cv2  # noqa: F401
      import numpy  # noqa: F401
      return True
    except ImportError:
      return False

  def analyze(self, image_path: str, body_part: str | None = None) -> VisionAnalysisResult:
    started = time.perf_counter()
    part = (body_part or "Unknown").strip() or "Unknown"

    try:
      import cv2
      import numpy as np
    except ImportError:
      return VisionAnalysisResult(
        success=False,
        message="OpenCV/NumPy required for heuristic vision model.",
        error_code="opencv_missing",
        model_name=self.name,
        processing_time_ms=self._ms(started),
      )

    gray = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if gray is None:
      return VisionAnalysisResult(
        success=False,
        message="Could not read image for vision analysis.",
        error_code="unreadable_image",
        model_name=self.name,
        body_part=part,
        processing_time_ms=self._ms(started),
      )

    h, w = gray.shape[:2]
    if h < 32 or w < 32:
      return VisionAnalysisResult(
        success=False,
        message="Image too small for meaningful analysis.",
        error_code="resolution_too_low",
        model_name=self.name,
        body_part=part,
        processing_time_ms=self._ms(started),
      )

    features = self._extract_features(gray, np)
    findings = self._map_features_to_findings(features, part)

    if not findings:
      findings = [
        FindingCandidate(
          label=FINDING_NO_ABNORMALITY,
          probability=0.55,
          region="global",
          rationale="No strong heuristic asymmetry or opacity signals were detected.",
        )
      ]

    # Overall confidence = max probability among findings (capped for educational model)
    confidence = min(0.85, max(f.probability for f in findings))

    return VisionAnalysisResult(
      success=True,
      possible_findings=findings,
      confidence=confidence,
      body_part=part,
      model_name=self.name,
      analysis_version=self.version,
      processing_time_ms=self._ms(started),
      message="Heuristic educational vision analysis completed.",
      raw_features=features,
    )

  def _extract_features(self, gray, np) -> dict[str, Any]:
    h, w = gray.shape
    # Normalize to 0–1
    norm = gray.astype("float32") / 255.0
    mean = float(np.mean(norm))
    std = float(np.std(norm))

    # Quadrants / lung-ish zones (upper/lower, left/right)
    mid_y, mid_x = h // 2, w // 2
    zones = {
      "upper_left": norm[:mid_y, :mid_x],
      "upper_right": norm[:mid_y, mid_x:],
      "lower_left": norm[mid_y:, :mid_x],
      "lower_right": norm[mid_y:, mid_x:],
      "center": norm[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4],
    }
    zone_means = {k: float(np.mean(v)) if v.size else 0.0 for k, v in zones.items()}
    zone_stds = {k: float(np.std(v)) if v.size else 0.0 for k, v in zones.items()}

    left_mean = (zone_means["upper_left"] + zone_means["lower_left"]) / 2
    right_mean = (zone_means["upper_right"] + zone_means["lower_right"]) / 2
    asymmetry = abs(left_mean - right_mean)

    lower_mean = (zone_means["lower_left"] + zone_means["lower_right"]) / 2
    upper_mean = (zone_means["upper_left"] + zone_means["upper_right"]) / 2
    lower_upper_delta = lower_mean - upper_mean

    # Edge density as a crude fracture / texture cue (esp. extremities)
    edges = cv2_canny_safe(gray)
    edge_density = float(np.mean(edges > 0)) if edges is not None else 0.0

    # Central silhouette prominence (cardiomegaly soft cue on chest)
    center_brightness = zone_means["center"]

    return {
      "width": w,
      "height": h,
      "mean_intensity": round(mean, 4),
      "std_intensity": round(std, 4),
      "zone_means": {k: round(v, 4) for k, v in zone_means.items()},
      "zone_stds": {k: round(v, 4) for k, v in zone_stds.items()},
      "left_right_asymmetry": round(asymmetry, 4),
      "lower_upper_delta": round(lower_upper_delta, 4),
      "edge_density": round(edge_density, 4),
      "center_brightness": round(center_brightness, 4),
    }

  def _map_features_to_findings(self, features: dict[str, Any], body_part: str) -> list[FindingCandidate]:
    findings: list[FindingCandidate] = []
    part = body_part.lower()
    asymmetry = float(features.get("left_right_asymmetry") or 0)
    std = float(features.get("std_intensity") or 0)
    lower_delta = float(features.get("lower_upper_delta") or 0)
    edge = float(features.get("edge_density") or 0)
    center = float(features.get("center_brightness") or 0)
    zone_stds = features.get("zone_stds") or {}

    is_chest = part in ("chest", "unknown", "other", "")
    is_extremity = part in (
      "hand",
      "finger",
      "wrist",
      "elbow",
      "leg",
      "femur",
      "ankle",
      "foot",
      "spine",
      "dental",
      "skull",
      "knee",
      "shoulder",
      "clavicle",
      "pelvis",
      "hip",
    )

    # Opacity / pneumonia soft signals (chest)
    if is_chest and (asymmetry > 0.08 or max(zone_stds.values() or [0]) > 0.18):
      opacity_p = min(0.78, 0.35 + asymmetry * 2.5 + std * 0.5)
      findings.append(
        FindingCandidate(
          label=FINDING_LUNG_OPACITY,
          probability=opacity_p,
          region="asymmetric_lung_zone",
          rationale="Regional intensity asymmetry / texture variation detected (educational heuristic).",
        )
      )
      if opacity_p >= 0.5 and asymmetry > 0.1:
        findings.append(
          FindingCandidate(
            label=FINDING_PNEUMONIA,
            probability=min(0.7, opacity_p * 0.85),
            region="asymmetric_lung_zone",
            rationale="Opacity-like pattern may be consistent with infectious processes — clinical correlation required.",
          )
        )

    # Pleural effusion soft cue: lower zones relatively denser
    if is_chest and lower_delta > 0.06:
      findings.append(
        FindingCandidate(
          label=FINDING_EFFUSION,
          probability=min(0.72, 0.3 + lower_delta * 2.0),
          region="lower_lung_zones",
          rationale="Lower-zone density relatively increased versus upper zones (educational heuristic).",
        )
      )

    # Cardiomegaly soft cue: bright central silhouette
    if is_chest and center > 0.45 and std > 0.1:
      findings.append(
        FindingCandidate(
          label=FINDING_CARDIOMEGALY,
          probability=min(0.68, 0.28 + (center - 0.4) * 1.5),
          region="cardiac_silhouette",
          rationale="Central silhouette prominence relative to surrounding lung fields (educational heuristic).",
        )
      )

    # Fracture soft cue for extremities / spine / dental
    if is_extremity and edge > 0.12:
      findings.append(
        FindingCandidate(
          label=FINDING_FRACTURE,
          probability=min(0.65, 0.25 + edge * 1.8),
          region=body_part or "extremity",
          rationale="Elevated edge density that can appear with cortical disruption — not diagnostic.",
        )
      )

    # Keep top findings only
    findings.sort(key=lambda f: f.probability, reverse=True)
    return findings[:5]

  @staticmethod
  def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def cv2_canny_safe(gray):
  try:
    import cv2

    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    return cv2.Canny(blurred, 60, 140)
  except Exception:
    return None


class OnnxVisionModelStub(BaseVisionModel):
  """
  Future-ready ONNX chest model placeholder.

  Set XRAY_VISION_ONNX_PATH to enable when a model file is available.
  Until then, is_available() returns False and the registry falls back.
  """

  name = "medimentora-onnx-chest-stub"
  version = ANALYSIS_VERSION

  def __init__(self, model_path: str | None = None):
    self.model_path = model_path

  def is_available(self) -> bool:
    # Stub only — a configured path does not mean inference works yet.
    # Keep False so the registry falls back to the educational heuristic model.
    return False

  def analyze(self, image_path: str, body_part: str | None = None) -> VisionAnalysisResult:
    # Intentional stub — real ONNX inference will be plugged in later.
    return VisionAnalysisResult(
      success=False,
      message=(
        "ONNX vision model path is configured but inference is not implemented yet. "
        "Fall back to the heuristic educational model."
      ),
      error_code="onnx_not_implemented",
      model_name=self.name,
      body_part=body_part,
    )


class VisionModelRegistry:
  """Resolve the active vision backend from config / availability / body part."""

  @classmethod
  def get_model(cls, preferred: str | None = None, body_part: str | None = None) -> BaseVisionModel:
    """Backward-compatible single-model resolve (uses smart router when body_part set)."""
    model, _route = cls.get_model_for_case(preferred=preferred, body_part=body_part)
    return model

  @classmethod
  def get_model_for_case(
    cls,
    *,
    preferred: str | None = None,
    body_part: str | None = None,
    projection: str | None = None,
  ) -> tuple[BaseVisionModel, dict]:
    """Phase 6 — smart route to a body-part specialist."""
    from flask import current_app, has_app_context

    name = (preferred or "").strip().lower()
    onnx_path = None
    if has_app_context():
      if not name:
        name = str(current_app.config.get("XRAY_VISION_MODEL", "auto")).lower()
      onnx_path = current_app.config.get("XRAY_VISION_ONNX_PATH") or None

    # Explicit legacy ONNX request
    if name == "onnx":
      onnx_model = OnnxVisionModelStub(onnx_path)
      route = {
        "specialist_key": "chest",
        "model_name": onnx_model.name,
        "future_backend": "onnx",
        "body_part": body_part,
        "projection": projection,
        "reason": "Explicit ONNX preference.",
        "fallback_used": not onnx_model.is_available(),
        "version": "phase6-v1",
      }
      if onnx_model.is_available():
        return onnx_model, route
      # fall through to router

    from app.services.xray.models.registry import SpecializedModelRegistry

    model, route_obj = SpecializedModelRegistry.get_model_for_case(
      body_part=body_part,
      projection=projection,
      preferred=None if name in ("auto", "onnx", "") else name,
    )
    return model, route_obj.to_dict()
