"""X-ray upload and history service (Module 2).

Handles validate → store file → persist XrayAnalysis rows.
Preprocessing / vision / Gemini happen in later modules.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.xray_analysis_model import (
  XRAY_BODY_PARTS,
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_STATUS_UPLOADED,
  XrayAnalysis,
)
from app.services.xray.patient_info import PatientClinicalInfo
from app.services.xray.validators import ValidatedXrayUpload, XrayUploadValidator
from app.utils import utc_now

logger = logging.getLogger(__name__)


@dataclass
class XrayUploadItem:
  """One successfully saved X-ray in a batch."""

  xray_id: int
  original_filename: str
  file_type: str
  file_size: int
  file_path: str
  body_part: str | None
  status: str
  width: int | None = None
  height: int | None = None

  def to_dict(self) -> dict:
    return {
      "id": self.xray_id,
      "xray_id": self.xray_id,
      "original_filename": self.original_filename,
      "file_type": self.file_type,
      "file_size": self.file_size,
      "file_path": self.file_path,
      "body_part": self.body_part,
      "status": self.status,
      "width": self.width,
      "height": self.height,
    }


@dataclass
class XrayBatchUploadResult:
  """Outcome of a multi-file X-ray upload."""

  success: bool
  batch_id: str
  files: list[XrayUploadItem] = field(default_factory=list)
  errors: list[str] = field(default_factory=list)
  files_received: int = 0
  files_saved: int = 0
  total_size_bytes: int = 0

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "batch_id": self.batch_id,
      "files_received": self.files_received,
      "files_saved": self.files_saved,
      "total_size_bytes": self.total_size_bytes,
      "files": [f.to_dict() for f in self.files],
      "xrays": [f.to_dict() for f in self.files],
      "errors": self.errors,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    }


class XrayUploadService:
  """Persist one or many X-ray images for a user (upload-only Module 2)."""

  @classmethod
  def upload_batch(
    cls,
    user_id: int,
    files: list[FileStorage],
    body_part: str | None = None,
    clinical: PatientClinicalInfo | None = None,
  ) -> XrayBatchUploadResult:
    """Validate and save multiple X-ray images as one upload batch."""
    batch_id = uuid.uuid4().hex
    cfg = current_app.config
    max_files = int(cfg.get("XRAY_MAX_FILES", 20))
    max_total = int(cfg.get("XRAY_MAX_TOTAL_BYTES", 100 * 1024 * 1024))
    max_file = int(cfg.get("XRAY_MAX_FILE_BYTES", 25 * 1024 * 1024))
    min_w = int(cfg.get("XRAY_MIN_WIDTH", 64))
    min_h = int(cfg.get("XRAY_MIN_HEIGHT", 64))

    existing_hashes = {
      h
      for (h,) in db.session.query(XrayAnalysis.content_hash)
      .filter(XrayAnalysis.user_id == user_id, XrayAnalysis.content_hash.isnot(None))
      .all()
    }

    allowed_ext = cfg.get("XRAY_ALLOWED_EXTENSIONS") or ("jpg", "jpeg", "png", "dcm", "dicom")
    max_w = int(cfg.get("XRAY_MAX_WIDTH", 10000))
    max_h = int(cfg.get("XRAY_MAX_HEIGHT", 10000))
    validator = XrayUploadValidator(
      max_files=max_files,
      max_total_bytes=max_total,
      max_file_bytes=max_file,
      min_width=min_w,
      min_height=min_h,
      max_width=max_w,
      max_height=max_h,
      existing_hashes=existing_hashes,
      allowed_extensions=allowed_ext,
    )
    validation = validator.validate(files)

    result = XrayBatchUploadResult(
      success=False,
      batch_id=batch_id,
      files_received=len([f for f in files if f is not None]),
      total_size_bytes=validation.total_size_bytes,
    )

    if not validation.ok:
      result.errors = validation.error_messages()
      logger.warning(
        "X-ray upload rejected user=%s batch=%s errors=%s",
        user_id,
        batch_id,
        result.errors,
      )
      return result

    upload_dir = cfg["XRAY_UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)
    resolved_body = (clinical.body_part if clinical else None) or cls._normalize_body_part(body_part)
    saved_paths: list[str] = []

    try:
      for validated in validation.files:
        item = cls._persist_one(
          user_id,
          validated,
          upload_dir,
          batch_id,
          resolved_body,
          clinical=clinical,
        )
        saved_paths.append(item.file_path)
        result.files.append(item)

      db.session.commit()
      result.success = True
      result.files_saved = len(result.files)
      logger.info(
        "X-ray upload OK user=%s batch=%s saved=%s clinical=%s",
        user_id,
        batch_id,
        result.files_saved,
        bool(clinical),
      )
      return result
    except Exception:
      db.session.rollback()
      for path in saved_paths:
        try:
          if os.path.isfile(path):
            os.remove(path)
        except OSError:
          pass
      logger.exception("Failed to upload X-ray batch for user=%s", user_id)
      result.errors.append("Failed to save uploaded X-ray images.")
      result.files = []
      return result

  @classmethod
  def apply_clinical_info(
    cls,
    xray_id: int,
    user_id: int,
    clinical: PatientClinicalInfo,
  ) -> XrayAnalysis | None:
    """Persist validated patient clinical fields onto an owned X-ray row."""
    row = cls.get_for_user(xray_id, user_id)
    if not row:
      return None
    cls._assign_clinical(row, clinical)
    row.updated_at = utc_now()
    db.session.commit()
    logger.info(
      "Patient clinical info saved xray_id=%s user=%s age=%s body_part=%s",
      xray_id,
      user_id,
      clinical.patient_age,
      clinical.body_part,
    )
    return row

  @classmethod
  def _persist_one(
    cls,
    user_id: int,
    validated: ValidatedXrayUpload,
    upload_dir: str,
    batch_id: str,
    body_part: str | None,
    clinical: PatientClinicalInfo | None = None,
  ) -> XrayUploadItem:
    # DICOM is validated then converted to PNG for the OpenCV/PIL pipeline.
    if validated.normalized_bytes is not None:
      store_ext = (validated.stored_extension or "png").lstrip(".")
      base = secure_filename(validated.filename.rsplit(".", 1)[0]) or "xray"
      safe_name = f"{base}.{store_ext}"
      stored = f"{uuid.uuid4().hex}_{safe_name}"
      dest = os.path.join(upload_dir, stored)
      with open(dest, "wb") as fh:
        fh.write(validated.normalized_bytes)
      stored_size = len(validated.normalized_bytes)
    else:
      safe_name = secure_filename(validated.filename) or f"xray.{validated.extension}"
      stored = f"{uuid.uuid4().hex}_{safe_name}"
      dest = os.path.join(upload_dir, stored)
      validated.storage.save(dest)
      stored_size = validated.size_bytes

    row = XrayAnalysis(
      user_id=user_id,
      filename=validated.filename[:255],
      stored_filename=stored[:255],
      file_path=dest,
      file_type=validated.file_type,
      file_size=stored_size,
      content_hash=validated.content_hash,
      batch_id=batch_id,
      body_part=body_part,
      status=XRAY_STATUS_UPLOADED,
      disclaimer=XRAY_MEDICAL_DISCLAIMER,
      upload_date=utc_now(),
      created_at=utc_now(),
      updated_at=utc_now(),
    )
    if clinical:
      cls._assign_clinical(row, clinical)
    db.session.add(row)
    db.session.flush()

    return XrayUploadItem(
      xray_id=row.id,
      original_filename=row.filename,
      file_type=row.file_type or validated.file_type,
      file_size=row.file_size or validated.size_bytes,
      file_path=row.file_path,
      body_part=row.body_part,
      status=row.status,
      width=validated.width,
      height=validated.height,
    )

  @staticmethod
  def _assign_clinical(row: XrayAnalysis, clinical: PatientClinicalInfo) -> None:
    row.patient_age = clinical.patient_age
    row.gender = clinical.gender
    row.body_part = clinical.body_part
    row.symptoms = clinical.symptoms
    row.reason_for_exam = clinical.reason_for_exam
    row.smoking_history = clinical.smoking_history
    row.clinical_extras = clinical.clinical_extras or {}

  @staticmethod
  def list_history(
    user_id: int,
    body_part: str | None = None,
    status: str | None = None,
    gender: str | None = None,
    smoking_history: str | None = None,
    age_min: int | None = None,
    age_max: int | None = None,
    date_from=None,
    date_to=None,
    limit: int | None = None,
    offset: int = 0,
  ) -> tuple[list[XrayAnalysis], int]:
    """
    Return the user's X-ray history, newest first (Phase 15).

    Supports clinical filters, optional upload-date range, and pagination.
    Returns (rows, total_matching_count).
    """
    from datetime import datetime, timedelta

    query = XrayAnalysis.query.filter_by(user_id=user_id)
    if body_part:
      query = query.filter(XrayAnalysis.body_part.ilike(body_part.strip()))
    if status:
      query = query.filter_by(status=status.strip().lower())
    if gender:
      query = query.filter(XrayAnalysis.gender.ilike(gender.strip()))
    if smoking_history:
      query = query.filter(XrayAnalysis.smoking_history.ilike(smoking_history.strip()))
    if age_min is not None:
      query = query.filter(XrayAnalysis.patient_age >= int(age_min))
    if age_max is not None:
      query = query.filter(XrayAnalysis.patient_age <= int(age_max))

    if date_from is not None:
      if isinstance(date_from, str):
        try:
          date_from = datetime.fromisoformat(date_from.replace("Z", "+00:00")).replace(
            tzinfo=None
          )
        except ValueError as exc:
          raise ValueError(f"date_from must be ISO date/datetime ({exc})") from exc
      query = query.filter(XrayAnalysis.upload_date >= date_from)
    if date_to is not None:
      if isinstance(date_to, str):
        raw_to = str(date_to).strip()
        try:
          parsed = datetime.fromisoformat(raw_to.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError as exc:
          raise ValueError(f"date_to must be ISO date/datetime ({exc})") from exc
        # Inclusive end-of-day when only a date is provided (YYYY-MM-DD)
        if len(raw_to) <= 10:
          parsed = parsed + timedelta(days=1) - timedelta(microseconds=1)
        date_to = parsed
      query = query.filter(XrayAnalysis.upload_date <= date_to)

    total = query.count()
    query = query.order_by(XrayAnalysis.created_at.desc())
    if offset:
      query = query.offset(max(0, int(offset)))
    if limit is not None:
      query = query.limit(max(1, int(limit)))
    return query.all(), int(total)

  @staticmethod
  def get_for_user(xray_id: int, user_id: int) -> XrayAnalysis | None:
    """Fetch a single X-ray owned by the user."""
    return XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()

  @classmethod
  def delete_row(cls, row: XrayAnalysis) -> None:
    """Delete an X-ray row and associated image files."""
    paths = [row.file_path, row.preprocessed_path, row.heatmap_path]
    if row.heatmap_path and row.heatmap_path.endswith("_heatmap.png"):
      paths.append(row.heatmap_path.replace("_heatmap.png", "_overlay.png"))
    xray_id = row.id
    user_id = row.user_id
    db.session.delete(row)
    db.session.commit()

    for path in paths:
      if path and os.path.isfile(path):
        try:
          os.remove(path)
        except OSError:
          logger.warning("Could not delete X-ray file %s", path)
    logger.info("Deleted X-ray id=%s user=%s", xray_id, user_id)

  @classmethod
  def delete_for_user(cls, xray_id: int, user_id: int) -> bool:
    """Delete an X-ray record and its files if owned by the user."""
    row = cls.get_for_user(xray_id, user_id)
    if not row:
      return False
    cls.delete_row(row)
    return True

  @classmethod
  def delete_by_id(cls, xray_id: int) -> bool:
    """Admin delete — any X-ray by id (files included)."""
    row = db.session.get(XrayAnalysis, xray_id)
    if not row:
      return False
    cls.delete_row(row)
    return True

  @staticmethod
  def _normalize_body_part(body_part: str | None) -> str | None:
    if not body_part:
      return None
    cleaned = body_part.strip()
    if not cleaned:
      return None
    lookup = {p.lower(): p for p in XRAY_BODY_PARTS}
    return lookup.get(cleaned.lower(), cleaned[:50])
