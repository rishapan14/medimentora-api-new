"""Vision analysis orchestration for X-ray records (Module 4).

Ensures preprocessing (Module 3) then runs the selected vision backend,
persisting educational possible findings — never definitive diagnoses.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.extensions import db
from app.models.xray_analysis_model import (
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_STATUS_ANALYZING,
  XRAY_STATUS_COMPLETED,
  XRAY_STATUS_FAILED,
  XrayAnalysis,
)
from app.services.xray.preprocess_service import XrayPreprocessService
from app.services.xray.vision_model import VisionAnalysisResult, VisionModelRegistry
from app.utils import utc_now

logger = logging.getLogger(__name__)


class VisionModelService:
  """Run medical vision analysis on an owned X-ray and persist results."""

  @classmethod
  def analyze_for_user(
    cls,
    xray_id: int,
    user_id: int,
    body_part: str | None = None,
    force_preprocess: bool = False,
    clinical=None,
  ) -> tuple[XrayAnalysis | None, VisionAnalysisResult]:
    """
    Analyze one X-ray owned by the user.

    Steps:
      1. Load ownership-scoped row
      2. Apply patient clinical info when provided
      3. Ensure preprocessed image exists
      4. Run vision model
      5. Persist possible_findings, confidence, model metadata
    """
    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, VisionAnalysisResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
      )

    if clinical is not None:
      from app.services.xray.upload_service import XrayUploadService

      XrayUploadService._assign_clinical(row, clinical)
      row.updated_at = utc_now()
      db.session.flush()
    elif body_part:
      from app.services.xray.upload_service import XrayUploadService

      row.body_part = XrayUploadService._normalize_body_part(body_part) or row.body_part

    # Ensure preprocessing
    row, prep = XrayPreprocessService.preprocess_for_user(
      xray_id,
      user_id,
      force=force_preprocess,
    )
    if row is None:
      return None, VisionAnalysisResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
      )
    if not prep.success or not row.preprocessed_path or not os.path.isfile(row.preprocessed_path):
      # Fall back to original if preprocess failed but original exists
      image_path = row.file_path if row.file_path and os.path.isfile(row.file_path) else None
      if not image_path:
        row.status = XRAY_STATUS_FAILED
        row.error_message = prep.message or "No image available for vision analysis."
        row.updated_at = utc_now()
        db.session.commit()
        return row, VisionAnalysisResult(
          success=False,
          message=row.error_message,
          error_code="missing_image",
        )
      logger.warning("Using original image for vision id=%s (preprocess failed)", xray_id)
    else:
      image_path = row.preprocessed_path

    # Phase 4 — ensure body-part detection exists (e.g. cached preprocess without detection)
    if not isinstance(getattr(row, "body_detection", None), dict) or not row.body_detection.get("success"):
      try:
        from app.services.xray.body_detection import BodyPartDetector, get_detector

        detection = get_detector().detect(image_path)
        if detection.success:
          payload = detection.to_dict()
          declared = BodyPartDetector.canonicalize(row.body_part)
          payload["declared_body_part"] = row.body_part
          payload["declared_canonical"] = declared
          payload["agrees_with_declared"] = (
            bool(declared and detection.body_part and declared.lower() == detection.body_part.lower())
            if declared and detection.body_part
            else None
          )
          row.body_detection = payload
          if not row.body_part and detection.body_part:
            row.body_part = detection.body_part
          db.session.commit()
      except Exception:
        logger.exception("Body-part detection during analyze failed id=%s", xray_id)

    # Phase 5 — ensure projection detection exists
    if not isinstance(getattr(row, "projection_detection", None), dict) or not row.projection_detection.get("success"):
      try:
        from app.services.xray.projection_detection import (
          ProjectionDetector,
          get_projection_detector,
        )

        body_hint = None
        if isinstance(row.body_detection, dict):
          body_hint = row.body_detection.get("body_part")
        body_hint = body_hint or row.body_part
        proj = get_projection_detector().detect(image_path, body_part=body_hint)
        if proj.success:
          extras = row.clinical_extras if isinstance(row.clinical_extras, dict) else {}
          declared_proj = ProjectionDetector.canonicalize(
            extras.get("projection") if isinstance(extras, dict) else None
          )
          payload = proj.to_dict()
          payload["declared_projection"] = extras.get("projection") if isinstance(extras, dict) else None
          payload["declared_canonical"] = declared_proj
          payload["agrees_with_declared"] = (
            bool(declared_proj and proj.projection and declared_proj.lower() == proj.projection.lower())
            if declared_proj and proj.projection
            else None
          )
          row.projection_detection = payload
          if isinstance(extras, dict) and not extras.get("projection") and proj.projection and proj.projection != "Unknown":
            extras = dict(extras)
            extras["projection"] = proj.projection
            row.clinical_extras = extras
          db.session.commit()
      except Exception:
        logger.exception("Projection detection during analyze failed id=%s", xray_id)

    row.status = XRAY_STATUS_ANALYZING
    row.error_message = None
    row.updated_at = utc_now()
    db.session.commit()

    started = time.perf_counter()
    extras = row.clinical_extras if isinstance(row.clinical_extras, dict) else {}
    projection = None
    if isinstance(row.projection_detection, dict):
      projection = row.projection_detection.get("projection")
    if not projection and isinstance(extras, dict):
      projection = extras.get("projection")

    route_body = row.body_part
    if isinstance(row.body_detection, dict) and row.body_detection.get("body_part"):
      # Prefer declared clinical label for routing when present; else detected
      route_body = row.body_part or row.body_detection.get("body_part")

    model, route = VisionModelRegistry.get_model_for_case(
      body_part=route_body,
      projection=projection if isinstance(projection, str) else None,
    )
    result = model.analyze(image_path, body_part=row.body_part)
    elapsed = int((time.perf_counter() - started) * 1000)
    result.processing_time_ms = result.processing_time_ms or elapsed
    result.raw_features = {**(result.raw_features or {}), "model_routing": route}
    row.model_routing = route

    if not result.success:
      row.status = XRAY_STATUS_FAILED
      row.error_message = result.message
      row.model_name = result.model_name
      row.analysis_version = result.analysis_version
      row.updated_at = utc_now()
      db.session.commit()
      logger.warning("Vision analysis failed id=%s: %s", xray_id, result.message)
      return row, result

    # Phase 7 — optional secondary findings model for ensemble agreement
    secondary_findings: list[dict] = []
    specialist_key = (route or {}).get("specialist_key") if isinstance(route, dict) else None
    if specialist_key and specialist_key != "generic":
      try:
        from app.services.xray.models.specialists import GenericVisionModel

        secondary_model = GenericVisionModel()
        if secondary_model.is_available():
          secondary = secondary_model.analyze(image_path, body_part=row.body_part)
          if secondary.success:
            secondary_findings = [
              f.to_dict() if hasattr(f, "to_dict") else f for f in secondary.possible_findings
            ]
            elapsed += int(secondary.processing_time_ms or 0)
      except Exception:
        logger.exception("Secondary ensemble model failed id=%s", xray_id)

    from app.services.xray.analysis import MultiModelEnsemble, StructuredFindingsBuilder

    ensemble = MultiModelEnsemble.fuse(
      findings_result=result,
      body_detection=row.body_detection if isinstance(row.body_detection, dict) else None,
      projection_detection=row.projection_detection if isinstance(row.projection_detection, dict) else None,
      image_quality=row.image_quality if isinstance(row.image_quality, dict) else None,
      model_routing=route if isinstance(route, dict) else None,
      secondary_findings=secondary_findings,
    )
    row.ensemble_result = ensemble.to_dict()

    # Phase 8 — strict structured findings JSON (never free-form model text)
    extras = row.clinical_extras if isinstance(row.clinical_extras, dict) else {}
    declared_proj = extras.get("projection") if isinstance(extras, dict) else None
    structured = StructuredFindingsBuilder.from_ensemble(
      ensemble,
      body_part=row.body_part or result.body_part,
      projection=(
        (row.projection_detection or {}).get("projection")
        if isinstance(row.projection_detection, dict)
        else None
      )
      or declared_proj,
    )
    row.structured_findings = structured.to_dict()

    # Persist fused educational findings (aligned with structured schema)
    row.possible_findings = structured.findings or ensemble.fused_findings or [
      f.to_dict() for f in result.possible_findings
    ]
    row.confidence = float(
      structured.confidence[0]
      if structured.confidence
      else (ensemble.fused_confidence or result.confidence)
    )
    # Overall confidence prefers fused ensemble score when available
    if ensemble.fused_confidence:
      row.confidence = float(ensemble.fused_confidence)
    row.model_name = result.model_name
    row.analysis_version = result.analysis_version
    row.body_part = structured.body_part or result.body_part or row.body_part
    row.disclaimer = XRAY_MEDICAL_DISCLAIMER

    # Module 5 — AI explanation from structured findings only (never send images)
    from app.services.xray.ai_explainer import AIExplainerService

    explanation = AIExplainerService.explain_from_findings(
      possible_findings=row.possible_findings,
      confidence=row.confidence,
      body_part=row.body_part,
      model_name=row.model_name,
      patient_clinical=AIExplainerService._clinical_from_row(row),
    )
    if explanation.success:
      row.ai_summary = explanation.ai_summary
      row.structured_explanation = explanation.structured_explanation
      row.processing_time = (
        (row.processing_time or 0)
        + int(result.processing_time_ms)
        + int(ensemble.processing_time_ms)
        + int(explanation.processing_time_ms)
      )
    else:
      row.ai_summary = cls._build_placeholder_summary(result)
      row.structured_explanation = None
      row.processing_time = (
        (row.processing_time or 0)
        + int(result.processing_time_ms)
        + int(ensemble.processing_time_ms)
      )

    # Module 6 — educational attention heatmap (non-fatal if it fails)
    from flask import current_app, has_app_context

    from app.services.xray.heatmap import HeatmapService

    auto_heatmap = True
    if has_app_context():
      auto_heatmap = bool(current_app.config.get("XRAY_AUTO_HEATMAP", True))

    if auto_heatmap:
      image_for_heat = (
        row.preprocessed_path
        if row.preprocessed_path and os.path.isfile(row.preprocessed_path)
        else row.file_path
      )
      try:
        heat = HeatmapService.generate(
          image_for_heat,
          xray_id=row.id,
          findings=row.possible_findings,
          features=result.raw_features or None,
          body_part=row.body_part,
          prefer_gradcam=True,
        )
        if heat.success and heat.heatmap_path:
          if row.heatmap_path and row.heatmap_path != heat.heatmap_path:
            HeatmapService._safe_unlink(row.heatmap_path)
            overlay_old = row.heatmap_path.replace("_heatmap.png", "_overlay.png")
            if overlay_old != row.heatmap_path:
              HeatmapService._safe_unlink(overlay_old)
          row.heatmap_path = heat.heatmap_path
          row.heatmap_meta = heat.meta_for_storage()
          row.processing_time = (row.processing_time or 0) + int(heat.processing_time_ms)
        else:
          logger.warning("Heatmap skipped id=%s: %s", xray_id, heat.message)
      except Exception:
        logger.exception("Heatmap generation crashed id=%s", xray_id)

    # Phase 13 — learning recommendations (non-fatal)
    try:
      from app.services.xray.recommendation_service import XrayRecommendationService

      rec = XrayRecommendationService.build_recommendations(
        possible_findings=XrayRecommendationService.resolve_findings(row),
        body_part=row.body_part,
        patient_clinical=XrayRecommendationService._clinical_from_row(row),
        user_id=user_id,
        sync_user_recommendations=True,
      )
      if rec.success:
        row.learning_recommendations = rec.recommendations
    except Exception:
      logger.exception("Learning recommendations crashed id=%s", xray_id)

    # Phase 11 — Body Systems Hub recommendations from X-ray findings (non-fatal)
    try:
      from app.services.body_systems.hub_xray_recommendation_service import (
        HubXrayRecommendationService,
      )

      HubXrayRecommendationService.recommend_for_analysis(row, user_id=user_id)
    except Exception:
      logger.exception("Hub X-ray recommendations crashed id=%s", xray_id)

    # Educational healthy reference comparison (non-fatal)
    auto_comparison = True
    if has_app_context():
      auto_comparison = bool(current_app.config.get("XRAY_AUTO_COMPARISON", True))
    if auto_comparison:
      try:
        from app.services.xray.comparison_service import XrayComparisonService

        _, cmp_result = XrayComparisonService.compare_for_user(
          xray_id,
          user_id,
          persist=True,
          force_reselect=True,
        )
        if not cmp_result.success:
          logger.warning("Comparison skipped id=%s: %s", xray_id, cmp_result.message)
      except Exception:
        logger.exception("Educational comparison crashed id=%s", xray_id)

    row.status = XRAY_STATUS_COMPLETED
    row.analysis_date = utc_now()
    row.error_message = None
    row.updated_at = utc_now()
    db.session.commit()

    logger.info(
      "Vision analysis OK id=%s model=%s findings=%s confidence=%.3f explain=%s heatmap=%s recs=%s",
      xray_id,
      result.model_name,
      len(result.possible_findings),
      result.confidence,
      explanation.provider if explanation.success else "failed",
      bool(row.heatmap_path),
      len(row.learning_recommendations or []),
    )
    return row, result

  @classmethod
  def reanalyze_for_user(cls, xray_id: int, user_id: int) -> tuple[XrayAnalysis | None, VisionAnalysisResult]:
    """Re-run preprocessing + vision on an existing record."""
    return cls.analyze_for_user(xray_id, user_id, force_preprocess=True)

  @classmethod
  def analyze_batch_for_user(
    cls,
    user_id: int,
    xray_ids: list[int],
    body_part: str | None = None,
    clinical=None,
  ) -> list[dict]:
    """Analyze multiple owned X-rays; returns per-id summaries."""
    out = []
    for xray_id in xray_ids:
      row, result = cls.analyze_for_user(
        xray_id,
        user_id,
        body_part=body_part,
        clinical=clinical,
      )
      out.append(
        {
          "xray_id": xray_id,
          "success": result.success,
          "status": row.status if row else None,
          "xray": row.to_dict(include_explanation=True) if row else None,
          "vision": result.to_dict(),
        }
      )
    return out

  @classmethod
  def explain_for_user(cls, xray_id: int, user_id: int) -> tuple[XrayAnalysis | None, Any]:
    """Re-generate Phase 12 / Module 5 explanation from stored findings (no image, no re-vision)."""
    from app.services.xray.ai_explainer import AIExplainerService, ExplanationResult

    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, ExplanationResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
      )
    if not row.possible_findings:
      return row, ExplanationResult(
        success=False,
        message="No vision findings to explain. Run POST /api/xray/analyze first.",
        error_code="missing_findings",
      )

    explanation = AIExplainerService.explain_xray_row(row)
    if explanation.success:
      row.ai_summary = explanation.ai_summary
      # Preserve educational comparison keys when re-explaining findings
      existing = row.structured_explanation if isinstance(row.structured_explanation, dict) else {}
      merged = dict(explanation.structured_explanation or {})
      for key in ("educational_comparison", "comparison_reference"):
        if key in existing and key not in merged:
          merged[key] = existing[key]
      row.structured_explanation = merged
      row.disclaimer = XRAY_MEDICAL_DISCLAIMER
      row.processing_time = (row.processing_time or 0) + int(explanation.processing_time_ms)
      row.updated_at = utc_now()
      db.session.commit()
    return row, explanation

  @staticmethod
  def _build_placeholder_summary(result: VisionAnalysisResult) -> str:
    """Last-resort summary if the explainer service itself fails."""
    if not result.possible_findings:
      return (
        "Educational vision analysis completed. No structured findings were returned. "
        + XRAY_MEDICAL_DISCLAIMER
      )
    labels = ", ".join(f.label for f in result.possible_findings[:3])
    return (
      f"Educational vision analysis suggests the following possible findings: {labels}. "
      "These are not definitive diagnoses and require clinical interpretation. "
      + XRAY_MEDICAL_DISCLAIMER
    )
