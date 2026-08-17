"""Specialized radiograph vision backends (Phase 6).

Each specialist declares supported body parts and preferred future backend
(TorchXRayVision, MONAI, bone ONNX, etc.). Until weights are present, they
delegate to the educational heuristic engine with body-part-tuned findings.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from app.services.xray.vision_model import (
  ANALYSIS_VERSION,
  BaseVisionModel,
  FindingCandidate,
  HeuristicRadiographModel,
  OnnxVisionModelStub,
  VisionAnalysisResult,
)

logger = logging.getLogger(__name__)


class SpecializedHeuristicModel(HeuristicRadiographModel):
  """Heuristic backend branded for a body-part specialty."""

  specialty: str = "generic"
  supported_parts: tuple[str, ...] = ()
  future_backend: str = "heuristic"
  name: str = "medimentora-specialist-generic-v1"

  def analyze(self, image_path: str, body_part: str | None = None) -> VisionAnalysisResult:
    part = (body_part or self.specialty).strip() or self.specialty
    result = super().analyze(image_path, body_part=part)
    if result.success:
      result.model_name = self.name
      result.message = (
        f"{self.specialty} specialist educational analysis completed "
        f"(heuristic; future backend: {self.future_backend})."
      )
      result.raw_features = {
        **(result.raw_features or {}),
        "specialty": self.specialty,
        "future_backend": self.future_backend,
        "supported_parts": list(self.supported_parts),
      }
      # Retune findings for non-chest specialties
      result.possible_findings = self._specialize_findings(result.possible_findings, part)
      if result.possible_findings:
        result.confidence = min(0.85, max(f.probability for f in result.possible_findings))
    else:
      result.model_name = self.name
    return result

  def _specialize_findings(
    self, findings: list[FindingCandidate], body_part: str
  ) -> list[FindingCandidate]:
    part = body_part.lower()
    if self.specialty.lower() == "chest" or part in ("chest",):
      return findings

    # For bone/dental specialties, prefer fracture / alignment educational cues
    bone_labels = {"Possible Fracture"}
    kept = [f for f in findings if f.label in bone_labels]
    if not kept:
      # Soft default educational observation for specialty routing demos
      kept = [
        FindingCandidate(
          label="No obvious abnormality detected",
          probability=0.52,
          region=self.specialty,
          rationale=(
            f"No strong {self.specialty.lower()} heuristic signals detected. "
            "Educational observation only — not a diagnosis."
          ),
        )
      ]
    return kept[:5]


class ChestVisionModel(SpecializedHeuristicModel):
  specialty = "Chest"
  supported_parts = ("Chest",)
  future_backend = "torchxrayvision_or_monai"
  name = "medimentora-chest-torchxrayvision-ready-v1"

  def __init__(self, onnx_path: str | None = None):
    self._onnx_path = onnx_path

  def is_available(self) -> bool:
    return super().is_available()

  def preferred_neural(self) -> BaseVisionModel | None:
    stub = OnnxVisionModelStub(self._onnx_path)
    return stub if stub.is_available() else None


class HandVisionModel(SpecializedHeuristicModel):
  specialty = "Hand"
  supported_parts = ("Hand", "Finger", "Wrist", "Elbow")
  future_backend = "bone_fracture_onnx"
  name = "medimentora-hand-bone-model-ready-v1"


class LegVisionModel(SpecializedHeuristicModel):
  specialty = "Leg"
  supported_parts = ("Leg", "Femur", "Ankle")
  future_backend = "bone_fracture_onnx"
  name = "medimentora-leg-bone-model-ready-v1"


class FootVisionModel(SpecializedHeuristicModel):
  specialty = "Foot"
  supported_parts = ("Foot",)
  future_backend = "bone_fracture_onnx"
  name = "medimentora-foot-bone-model-ready-v1"


class SpineVisionModel(SpecializedHeuristicModel):
  specialty = "Spine"
  supported_parts = ("Spine",)
  future_backend = "spine_alignment_onnx"
  name = "medimentora-spine-model-ready-v1"


class KneeVisionModel(SpecializedHeuristicModel):
  specialty = "Knee"
  supported_parts = ("Knee",)
  future_backend = "knee_joint_onnx"
  name = "medimentora-knee-model-ready-v1"


class ShoulderVisionModel(SpecializedHeuristicModel):
  specialty = "Shoulder"
  supported_parts = ("Shoulder", "Clavicle")
  future_backend = "shoulder_bone_onnx"
  name = "medimentora-shoulder-model-ready-v1"


class PelvisVisionModel(SpecializedHeuristicModel):
  specialty = "Pelvis"
  supported_parts = ("Pelvis", "Hip")
  future_backend = "pelvis_bone_onnx"
  name = "medimentora-pelvis-model-ready-v1"


class DentalVisionModel(SpecializedHeuristicModel):
  specialty = "Dental"
  supported_parts = ("Dental", "Skull")
  future_backend = "dental_radiograph_onnx"
  name = "medimentora-dental-model-ready-v1"


class GenericVisionModel(SpecializedHeuristicModel):
  specialty = "Generic"
  supported_parts = ("Other", "Unknown")
  future_backend = "heuristic"
  name = "medimentora-generic-heuristic-v1"


def build_specialist_catalog(onnx_path: str | None = None) -> dict[str, SpecializedHeuristicModel]:
  """Instantiate all specialists (extensible registry map)."""
  return {
    "chest": ChestVisionModel(onnx_path=onnx_path),
    "hand": HandVisionModel(),
    "leg": LegVisionModel(),
    "foot": FootVisionModel(),
    "spine": SpineVisionModel(),
    "knee": KneeVisionModel(),
    "shoulder": ShoulderVisionModel(),
    "pelvis": PelvisVisionModel(),
    "dental": DentalVisionModel(),
    "generic": GenericVisionModel(),
  }


# Package layout mirrors architecture plan (chest/hand/... folders as namespaces)
def ensure_package_layout_docs() -> dict[str, Any]:
  return {
    "models": [
      "chest",
      "hand",
      "leg",
      "spine",
      "knee",
      "foot",
      "shoulder",
      "pelvis",
      "dental",
    ],
    "router": "SmartModelRouter",
    "note": "Folders under models/<part>/ may hold ONNX weights later.",
  }
