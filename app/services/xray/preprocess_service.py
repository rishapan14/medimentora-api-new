"""Orchestrate X-ray preprocessing for persisted records (Module 3)."""

from __future__ import annotations

import logging
import os
import uuid

from flask import current_app

from app.extensions import db
from app.models.xray_analysis_model import (
  XRAY_STATUS_FAILED,
  XRAY_STATUS_PREPROCESSING,
  XRAY_STATUS_UPLOADED,
  XrayAnalysis,
)
from app.services.xray.image_preprocessor import ImagePreprocessor, XrayPreprocessResult
from app.services.xray.quality import ImageQualityAssessor
from app.services.xray.body_detection import BodyPartDetector, get_detector
from app.services.xray.projection_detection import (
  ProjectionDetector,
  get_projection_detector,
)
from app.utils import utc_now

logger = logging.getLogger(__name__)


class XrayPreprocessService:
  """Run ImagePreprocessor on an owned XrayAnalysis row and persist artifacts."""

  @classmethod
  def preprocess_for_user(cls, xray_id: int, user_id: int, force: bool = False) -> tuple[XrayAnalysis | None, XrayPreprocessResult]:
    """
    Preprocess an X-ray owned by the user.

    Args:
      xray_id: Database id.
      user_id: Owner id (JWT subject).
      force: Re-run even if preprocessed_path already exists.

    Returns:
      (row_or_None, preprocess_result)
    """
    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, XrayPreprocessResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
      )

    if row.preprocessed_path and os.path.isfile(row.preprocessed_path) and not force:
      cached = XrayPreprocessResult(
        success=True,
        path=row.preprocessed_path,
        applied_steps=["cached"],
        message="Using existing preprocessed image.",
      )
      if isinstance(row.image_quality, dict):
        cached.quality = row.image_quality
      return row, cached

    if not row.file_path or not os.path.isfile(row.file_path):
      row.status = XRAY_STATUS_FAILED
      row.error_message = "Original X-ray file is missing from storage."
      row.updated_at = utc_now()
      db.session.commit()
      return row, XrayPreprocessResult(
        success=False,
        message=row.error_message,
        error_code="missing_file",
      )

    row.status = XRAY_STATUS_PREPROCESSING
    row.error_message = None
    row.updated_at = utc_now()
    db.session.commit()

    # Phase 2 — assess original upload quality before enhancement
    quality = ImageQualityAssessor().assess(row.file_path)
    if quality.success:
      row.image_quality = quality.to_dict()
      db.session.commit()
      logger.info(
        "X-ray quality id=%s score=%.1f grade=%s poor=%s issues=%s",
        xray_id,
        quality.quality_score,
        quality.grade,
        quality.is_poor,
        [i.code for i in quality.issues],
      )
    else:
      logger.warning(
        "X-ray quality assessment skipped id=%s: %s",
        xray_id,
        quality.message,
      )

    output_path = cls._build_output_path(row)
    preprocessor = ImagePreprocessor(
      target_max_dim=int(current_app.config.get("XRAY_PREPROCESS_MAX_DIM", 2048)),
      target_min_dim=int(current_app.config.get("XRAY_PREPROCESS_MIN_DIM", 512)),
    )
    result = preprocessor.enhance(row.file_path, output_path=output_path)
    result.quality = quality.to_dict() if quality.success else quality.to_dict()

    if not result.success:
      row.status = XRAY_STATUS_FAILED
      row.error_message = result.message
      row.updated_at = utc_now()
      db.session.commit()
      logger.warning("X-ray preprocess failed id=%s: %s", xray_id, result.message)
      return row, result

    # Remove previous preprocessed file if replaced
    old = row.preprocessed_path
    if old and old != result.path and os.path.isfile(old):
      try:
        os.remove(old)
      except OSError:
        pass

    row.preprocessed_path = result.path
    row.preprocess_meta = {
      "applied_steps": result.applied_steps,
      "original_size": list(result.original_size),
      "final_size": list(result.final_size),
      "rotation_degrees": round(float(result.rotation_degrees or 0.0), 2),
      "processing_time_ms": result.processing_time_ms,
      "mean_intensity": result.mean_intensity,
      "std_intensity": result.std_intensity,
      "normalization": result.normalization,
      "warnings": result.warnings,
      "version": "phase3-v1",
    }

    # Phase 4 — body-part detection on the enhanced image (does not override clinical label)
    detect_path = result.path if result.path and os.path.isfile(result.path) else row.file_path
    detection = get_detector().detect(detect_path)
    if detection.success:
      payload = detection.to_dict()
      declared = BodyPartDetector.canonicalize(row.body_part)
      detected = detection.body_part
      payload["declared_body_part"] = row.body_part
      payload["declared_canonical"] = declared
      payload["agrees_with_declared"] = (
        bool(declared and detected and declared.lower() == detected.lower())
        if declared and detected
        else None
      )
      row.body_detection = payload
      # Fill missing clinical body_part only — never overwrite user selection
      if not row.body_part and detected:
        row.body_part = detected
      logger.info(
        "X-ray body-part id=%s detected=%s conf=%.2f declared=%s",
        xray_id,
        detected,
        detection.confidence,
        row.body_part,
      )
    else:
      logger.warning("Body-part detection skipped id=%s: %s", xray_id, detection.message)

    # Phase 5 — projection detection (does not overwrite declared clinical projection)
    proj = get_projection_detector().detect(
      detect_path,
      body_part=(row.body_detection or {}).get("body_part") if isinstance(row.body_detection, dict) else row.body_part,
    )
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
      # Fill missing projection only
      if isinstance(extras, dict) and not extras.get("projection") and proj.projection and proj.projection != "Unknown":
        extras = dict(extras)
        extras["projection"] = proj.projection
        row.clinical_extras = extras
      logger.info(
        "X-ray projection id=%s detected=%s conf=%.2f declared=%s",
        xray_id,
        proj.projection,
        proj.confidence,
        payload.get("declared_projection"),
      )
    else:
      logger.warning("Projection detection skipped id=%s: %s", xray_id, proj.message)

    row.status = XRAY_STATUS_UPLOADED  # ready for vision analysis (Module 4)
    row.error_message = None
    # Accumulate light timing if empty
    if result.processing_time_ms:
      row.processing_time = (row.processing_time or 0) + int(result.processing_time_ms)
    row.updated_at = utc_now()
    db.session.commit()

    logger.info(
      "X-ray preprocess OK id=%s steps=%s ms=%s",
      xray_id,
      ",".join(result.applied_steps),
      result.processing_time_ms,
    )
    return row, result

  @classmethod
  def preprocess_batch_for_user(
    cls,
    user_id: int,
    xray_ids: list[int],
    force: bool = False,
  ) -> list[dict]:
    """Preprocess multiple owned X-rays; returns per-id summaries."""
    summaries = []
    for xray_id in xray_ids:
      row, result = cls.preprocess_for_user(xray_id, user_id, force=force)
      summaries.append(
        {
          "xray_id": xray_id,
          "success": result.success,
          "status": row.status if row else None,
          "preprocessed_path": row.preprocessed_path if row else None,
          "image_quality": (row.image_quality if row and isinstance(row.image_quality, dict) else None)
          or getattr(result, "quality", None),
          "preprocess": result.to_dict(),
        }
      )
    return summaries

  @staticmethod
  def _build_output_path(row: XrayAnalysis) -> str:
    folder = current_app.config["XRAY_PREPROCESSED_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    base = os.path.splitext(os.path.basename(row.stored_filename or row.filename or "xray"))[0]
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)[:80] or "xray"
    return os.path.join(folder, f"{row.id}_{uuid.uuid4().hex[:10]}_{safe}_preprocessed.png")
