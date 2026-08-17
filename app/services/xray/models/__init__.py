"""Body-part specialized vision models + smart router (Phase 6).

Never use one model for every image. The router selects a specialist by
detected/declared body part. Specialists fall back to educational heuristics
until TorchXRayVision / MONAI / ONNX weights are configured.
"""

from app.services.xray.models.router import ModelRoute, SmartModelRouter
from app.services.xray.models.registry import SpecializedModelRegistry

__all__ = [
  "ModelRoute",
  "SmartModelRouter",
  "SpecializedModelRegistry",
]
