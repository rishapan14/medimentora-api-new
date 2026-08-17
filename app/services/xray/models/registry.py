"""Registry facade used by vision_service (Phase 6)."""

from __future__ import annotations

from app.services.xray.models.router import ModelRoute, SmartModelRouter
from app.services.xray.vision_model import BaseVisionModel


class SpecializedModelRegistry:
  """Resolve specialist models via SmartModelRouter."""

  @classmethod
  def get_model_for_case(
    cls,
    *,
    body_part: str | None = None,
    projection: str | None = None,
    preferred: str | None = None,
  ) -> tuple[BaseVisionModel, ModelRoute]:
    from flask import current_app, has_app_context

    onnx_path = None
    config_preferred = preferred
    if has_app_context():
      onnx_path = current_app.config.get("XRAY_VISION_ONNX_PATH") or None
      if not config_preferred:
        cfg = str(current_app.config.get("XRAY_VISION_MODEL", "auto")).lower()
        # auto → router; explicit specialist keys allowed; heuristic forces generic
        if cfg in ("heuristic", "generic"):
          config_preferred = "generic"
        elif cfg not in ("auto", "onnx", ""):
          config_preferred = cfg

    router = SmartModelRouter(onnx_path=onnx_path)
    return router.resolve(
      body_part=body_part,
      projection=projection,
      preferred=config_preferred,
    )

  @classmethod
  def list_specialists(cls) -> list[dict]:
    router = SmartModelRouter()
    out = []
    for key, model in router.catalog.items():
      out.append(
        {
          "key": key,
          "model_name": model.name,
          "specialty": getattr(model, "specialty", key),
          "future_backend": getattr(model, "future_backend", "heuristic"),
          "supported_parts": list(getattr(model, "supported_parts", ())),
          "available": model.is_available(),
        }
      )
    return out
