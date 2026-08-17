"""Smart model router — select specialist by body part (Phase 6)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.services.xray.body_detection.detector import BodyPartDetector
from app.services.xray.models.specialists import (
  SpecializedHeuristicModel,
  build_specialist_catalog,
)
from app.services.xray.vision_model import BaseVisionModel

logger = logging.getLogger(__name__)

# Map clinical / detected labels → specialist key
_PART_TO_SPECIALIST: dict[str, str] = {
  "chest": "chest",
  "hand": "hand",
  "finger": "hand",
  "wrist": "hand",
  "elbow": "hand",
  "leg": "leg",
  "femur": "leg",
  "ankle": "foot",
  "foot": "foot",
  "spine": "spine",
  "knee": "knee",
  "shoulder": "shoulder",
  "clavicle": "shoulder",
  "pelvis": "pelvis",
  "hip": "pelvis",
  "dental": "dental",
  "skull": "dental",
}


@dataclass
class ModelRoute:
  """Resolved routing decision for one analysis."""

  specialist_key: str
  model_name: str
  future_backend: str
  body_part: str | None
  projection: str | None = None
  reason: str = ""
  fallback_used: bool = False
  available_specialists: list[str] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    return {
      "specialist_key": self.specialist_key,
      "model_name": self.model_name,
      "future_backend": self.future_backend,
      "body_part": self.body_part,
      "projection": self.projection,
      "reason": self.reason,
      "fallback_used": self.fallback_used,
      "available_specialists": self.available_specialists,
      "version": "phase6-v1",
      "disclaimer": (
        "Model routing selects an educational specialist backend. "
        "It is not a diagnosis."
      ),
    }


class SmartModelRouter:
  """Never use one model for every image — route by anatomy."""

  def __init__(self, onnx_path: str | None = None):
    self.catalog = build_specialist_catalog(onnx_path=onnx_path)

  def resolve(
    self,
    *,
    body_part: str | None = None,
    projection: str | None = None,
    preferred: str | None = None,
  ) -> tuple[BaseVisionModel, ModelRoute]:
    available = [k for k, m in self.catalog.items() if m.is_available()]
    preferred_key = (preferred or "").strip().lower()

    if preferred_key and preferred_key in self.catalog:
      model = self.catalog[preferred_key]
      if model.is_available():
        route = ModelRoute(
          specialist_key=preferred_key,
          model_name=model.name,
          future_backend=getattr(model, "future_backend", "heuristic"),
          body_part=body_part,
          projection=projection,
          reason=f"Explicit preferred specialist '{preferred_key}'.",
          available_specialists=available,
        )
        return model, route

    key = self._map_body_part(body_part)
    model = self.catalog.get(key) or self.catalog["generic"]
    fallback = key not in self.catalog or not model.is_available()
    if not model.is_available():
      model = self.catalog["generic"]
      key = "generic"
      fallback = True

    # Prefer neural chest backend when configured
    if key == "chest" and isinstance(model, SpecializedHeuristicModel):
      neural = getattr(model, "preferred_neural", lambda: None)()
      if neural is not None and neural.is_available():
        # Still heuristic analyze until ONNX implemented — route metadata notes readiness
        pass

    route = ModelRoute(
      specialist_key=key,
      model_name=model.name,
      future_backend=getattr(model, "future_backend", "heuristic"),
      body_part=body_part,
      projection=projection,
      reason=(
        f"Routed by body part '{body_part or 'Unknown'}' → specialist '{key}'."
        + (" Fallback generic used." if fallback and key == "generic" else "")
      ),
      fallback_used=fallback and key == "generic" and self._map_body_part(body_part) != "generic",
      available_specialists=available,
    )
    logger.info(
      "SmartModelRouter selected=%s model=%s body_part=%s projection=%s",
      key,
      model.name,
      body_part,
      projection,
    )
    return model, route

  @staticmethod
  def _map_body_part(body_part: str | None) -> str:
    canonical = BodyPartDetector.canonicalize(body_part)
    raw = (canonical or body_part or "").strip().lower()
    if not raw:
      return "generic"
    if raw in _PART_TO_SPECIALIST:
      return _PART_TO_SPECIALIST[raw]
    # try first token
    token = raw.split()[0]
    return _PART_TO_SPECIALIST.get(token, "generic")
