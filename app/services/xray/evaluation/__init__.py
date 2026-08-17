"""Phase 17 — educational model evaluation package.

Public API:

  from app.services.xray.evaluation import XrayModelEvaluationService
"""

from app.services.xray.evaluation.service import (
  EVALUATION_VERSION,
  SAFETY,
  XrayModelEvaluationService,
)

__all__ = [
  "EVALUATION_VERSION",
  "SAFETY",
  "XrayModelEvaluationService",
]
