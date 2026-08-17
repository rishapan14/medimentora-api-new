"""Production Reference Library Manager — database-driven healthy X-ray refs.

Responsibilities:
  - Scan disk / sync metadata into MySQL
  - CRUD + bulk upload for admin
  - Closest-match selection (never crashes)
  - Soft empty when library has no usable images
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from flask import current_app, has_app_context
from PIL import Image
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.xray_analysis_model import (
  XRAY_AGE_GROUPS,
  XRAY_BODY_PARTS,
  XRAY_GENDER_RELEVANT_BODY_PARTS,
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_PROJECTIONS,
  XRAY_REFERENCE_GENDERS,
)
from app.models.xray_reference_model import XrayReferenceImage
from app.services.xray.reference_library import (
  CHILD_AGE_MAX,
  IMAGE_EXTENSIONS,
  ReferenceImage,
  ReferenceLibraryService,
  ReferenceSelectionResult,
)
from app.utils import utc_now

logger = logging.getLogger(__name__)

EMPTY_LIBRARY_MESSAGE = (
  "No healthy reference image is currently available for this body part. "
  "The AI analysis can still be viewed, and comparison will become available "
  "after reference images are added."
)


@dataclass
class LibraryManagerResult:
  success: bool
  message: str = ""
  error_code: str | None = None
  data: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "message": self.message,
      "error_code": self.error_code,
      "data": self.data,
    }


class ReferenceLibraryManager:
  """Scalable DB-backed manager for healthy educational reference X-rays."""

  # ------------------------------------------------------------------ paths

  @classmethod
  def library_root(cls) -> str:
    return ReferenceLibraryService.library_root()

  @classmethod
  def ensure_root(cls) -> str:
    root = cls.library_root()
    os.makedirs(root, exist_ok=True)
    return root

  # ------------------------------------------------------------------ query

  @classmethod
  def count_active(cls) -> int:
    try:
      return XrayReferenceImage.query.filter_by(is_active=True).count()
    except Exception:
      logger.exception("Failed counting reference images")
      return 0

  @classmethod
  def list_references(
    cls,
    *,
    body_part: str | None = None,
    projection: str | None = None,
    age_group: str | None = None,
    gender: str | None = None,
    q: str | None = None,
    active_only: bool = True,
    limit: int = 500,
    offset: int = 0,
  ) -> list[XrayReferenceImage]:
    query = XrayReferenceImage.query
    if active_only:
      query = query.filter_by(is_active=True)
    if body_part:
      query = query.filter(XrayReferenceImage.body_part.ilike(body_part.strip()))
    if projection:
      query = query.filter(XrayReferenceImage.projection.ilike(projection.strip()))
    if age_group:
      query = query.filter(XrayReferenceImage.age_group.ilike(age_group.strip()))
    if gender:
      query = query.filter(XrayReferenceImage.gender.ilike(gender.strip()))
    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        db.or_(
          XrayReferenceImage.label.ilike(like),
          XrayReferenceImage.notes.ilike(like),
          XrayReferenceImage.public_id.ilike(like),
          XrayReferenceImage.original_filename.ilike(like),
          XrayReferenceImage.source.ilike(like),
          XrayReferenceImage.body_part.ilike(like),
          XrayReferenceImage.projection.ilike(like),
        )
      )
    return (
      query.order_by(XrayReferenceImage.updated_at.desc(), XrayReferenceImage.id.desc())
      .offset(max(0, offset))
      .limit(min(max(limit, 1), 1000))
      .all()
    )

  @classmethod
  def get_by_id(cls, ref_id: int) -> XrayReferenceImage | None:
    return db.session.get(XrayReferenceImage, ref_id)

  @classmethod
  def get_by_public_id(cls, public_id: str) -> XrayReferenceImage | None:
    return XrayReferenceImage.query.filter_by(public_id=public_id).first()

  @classmethod
  def to_runtime_image(cls, row: XrayReferenceImage) -> ReferenceImage | None:
    root = cls.library_root()
    abs_path = row.absolute_path(root)
    if not os.path.isfile(abs_path):
      logger.warning(
        "Missing reference file on disk id=%s path=%s",
        row.id,
        row.relative_path,
      )
      return None
    return ReferenceImage(
      id=row.public_id,
      body_part=row.body_part,
      projection=row.projection or "Other",
      age_group=row.age_group or "Adult",
      gender=row.gender or "Unisex",
      relative_path=row.relative_path.replace("\\", "/"),
      absolute_path=abs_path,
      label=row.label or f"Healthy {row.body_part} reference",
      notes=row.notes or "",
      license=row.license or "",
      source=row.source or "",
      gender_relevant=bool(row.gender_relevant),
    )

  # ------------------------------------------------------------------ select

  @classmethod
  def select_reference(
    cls,
    *,
    body_part: str | None,
    patient_age: int | None = None,
    gender: str | None = None,
    projection: str | None = None,
    limit_alternatives: int = 3,
  ) -> ReferenceSelectionResult:
    """Pick closest active reference. Soft-empty when none usable — never raises."""
    try:
      rows = cls.list_references(active_only=True, limit=1000)
      refs: list[ReferenceImage] = []
      for row in rows:
        runtime = cls.to_runtime_image(row)
        if runtime:
          refs.append(runtime)
        else:
          logger.info("Skipping missing-on-disk reference id=%s", row.id)

      if not refs:
        # Transitional disk fallback before DB sync (never hard-fail here)
        try:
          ReferenceLibraryService.ensure_library()
          refs = [
            r
            for r in ReferenceLibraryService._load_references()
            if os.path.isfile(r.absolute_path)
          ]
        except Exception:
          logger.exception("Disk fallback for reference selection failed")
          refs = []

      if not refs:
        logger.info(
          "Reference library empty or unusable (body_part=%s projection=%s)",
          body_part,
          projection,
        )
        return ReferenceSelectionResult(
          success=False,
          matched_body_part=ReferenceLibraryService.normalize_body_part(body_part),
          matched_age_group=ReferenceLibraryService.age_group_from_age(patient_age),
          matched_projection=ReferenceLibraryService.normalize_projection(projection),
          message=EMPTY_LIBRARY_MESSAGE,
          error_code="empty_library",
        )

      # Prefer same body part; if none, fall back to closest overall (educational)
      wanted_part = ReferenceLibraryService.normalize_body_part(body_part)
      same_body = [r for r in refs if r.body_part.lower() == wanted_part.lower()]
      candidates = same_body if same_body else refs
      cross_body = not bool(same_body)

      wanted_age = ReferenceLibraryService.age_group_from_age(patient_age)
      wanted_gender = ReferenceLibraryService.normalize_gender(gender)
      wanted_projection = ReferenceLibraryService.normalize_projection(projection)
      use_gender = (
        ReferenceLibraryService.gender_is_relevant(wanted_part) and wanted_gender is not None
      )

      if wanted_projection and same_body:
        proj_matched = [
          r for r in candidates if r.projection.lower() == wanted_projection.lower()
        ]
        if proj_matched:
          candidates = proj_matched

      scored: list[tuple[int, ReferenceImage]] = []
      for ref in candidates:
        score = 0
        if ref.body_part.lower() == wanted_part.lower():
          score += 200
        else:
          score += 5  # cross-body educational fallback only

        if wanted_projection:
          if ref.projection.lower() == wanted_projection.lower():
            score += 150
          elif ref.projection.lower() == "other":
            score += 20
          else:
            score -= 40
        elif ref.projection.upper() in ("PA", "AP"):
          score += 10

        if ref.age_group.lower() == wanted_age.lower():
          score += 100
        elif wanted_age == "Child" and ref.age_group.lower() == "adult":
          score += 5
        elif wanted_age == "Adult" and ref.age_group.lower() == "child":
          score -= 20

        if use_gender:
          if ref.gender.lower() == wanted_gender.lower():
            score += 40
          elif ref.gender.lower() == "unisex":
            score += 15
        else:
          if ref.gender.lower() == "unisex":
            score += 25
          elif wanted_gender and ref.gender.lower() == wanted_gender.lower():
            score += 5

        scored.append((score, ref))

      scored.sort(key=lambda x: (-x[0], x[1].id))
      best_score, primary = scored[0]
      alts = [ref for _, ref in scored[1 : 1 + limit_alternatives]]

      if cross_body:
        message = (
          f"No exact {wanted_part} healthy reference was found. "
          f"Showing the closest educational reference "
          f"({primary.body_part} {primary.projection}). "
          "Educational only — not a diagnosis."
        )
        error_code = None
      else:
        message = (
          f"Selected healthy {primary.body_part} {primary.projection} reference "
          f"({primary.age_group}"
          f"{', ' + primary.gender if use_gender else ''}). "
          "Educational only — not a diagnosis."
        )
        error_code = None

      return ReferenceSelectionResult(
        success=True,
        primary=primary,
        alternatives=alts,
        matched_age_group=wanted_age,
        matched_body_part=wanted_part,
        matched_projection=wanted_projection or primary.projection,
        gender_used=use_gender,
        score=best_score,
        message=message,
        error_code=error_code,
      )
    except Exception:
      logger.exception("Reference selection failed — returning soft empty")
      return ReferenceSelectionResult(
        success=False,
        message=EMPTY_LIBRARY_MESSAGE,
        error_code="empty_library",
      )

  @classmethod
  def select_for_xray_row(cls, row) -> ReferenceSelectionResult:
    extras = getattr(row, "clinical_extras", None)
    if not isinstance(extras, dict):
      extras = {}
    projection = ReferenceLibraryService.detect_projection(
      explicit=extras.get("projection"),
      clinical_extras=extras,
      reason_for_exam=getattr(row, "reason_for_exam", None),
      symptoms=getattr(row, "symptoms", None),
      filename=getattr(row, "filename", None),
    )
    return cls.select_reference(
      body_part=getattr(row, "body_part", None),
      patient_age=getattr(row, "patient_age", None),
      gender=getattr(row, "gender", None),
      projection=projection,
    )

  # ------------------------------------------------------------------ scan / sync

  @classmethod
  def sync_from_disk(cls, *, uploaded_by: int | None = None) -> LibraryManagerResult:
    """Scan library folder tree and upsert DB rows from real image files."""
    root = cls.ensure_root()
    created = 0
    updated = 0
    skipped = 0
    missing_deactivated = 0

    try:
      seen_rel: set[str] = set()
      for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
          ext = os.path.splitext(name)[1].lower()
          if ext not in IMAGE_EXTENSIONS:
            continue
          abs_path = os.path.join(dirpath, name)
          rel = os.path.relpath(abs_path, root).replace("\\", "/")
          parts = rel.split("/")
          if len(parts) < 5:
            skipped += 1
            logger.info("Skip non-taxonomy reference path: %s", rel)
            continue
          seen_rel.add(rel)
          body = ReferenceLibraryService.normalize_body_part(parts[0].replace("_", " "))
          projection = ReferenceLibraryService.normalize_projection(parts[1]) or "Other"
          age = ReferenceLibraryService.normalize_age_group(parts[2]) or "Adult"
          gender = ReferenceLibraryService.normalize_gender(parts[3]) or "Unisex"
          meta = cls._read_image_metadata(abs_path)
          public_id = cls._public_id_from_filename(parts[-1], rel)
          row = XrayReferenceImage.query.filter_by(relative_path=rel).first()
          if not row:
            row = XrayReferenceImage(
              public_id=public_id,
              relative_path=rel,
              uploaded_by=uploaded_by,
            )
            db.session.add(row)
            created += 1
          else:
            updated += 1

          row.body_part = body
          row.projection = projection
          row.age_group = age
          row.gender = gender
          row.original_filename = parts[-1]
          row.stored_filename = parts[-1]
          row.mime_type = meta.get("mime_type")
          row.file_size = meta.get("file_size")
          row.width = meta.get("width")
          row.height = meta.get("height")
          row.content_hash = meta.get("content_hash")
          row.gender_relevant = body in XRAY_GENDER_RELEVANT_BODY_PARTS
          if not row.label:
            row.label = f"Healthy {body} {projection} reference ({age}, {gender})"
          row.is_active = True
          row.updated_at = utc_now()

      # Soft-deactivate DB rows whose files disappeared
      for row in XrayReferenceImage.query.filter_by(is_active=True).all():
        if row.relative_path.replace("\\", "/") not in seen_rel:
          if not os.path.isfile(row.absolute_path(root)):
            row.is_active = False
            missing_deactivated += 1
            logger.warning("Deactivated missing reference id=%s path=%s", row.id, row.relative_path)

      db.session.commit()
      # Keep optional JSON catalog in sync for ops tooling
      try:
        ReferenceLibraryService.rebuild_catalog_from_disk()
      except Exception:
        logger.exception("Catalog rebuild after sync failed (non-fatal)")

      return LibraryManagerResult(
        success=True,
        message="Reference library synchronized from disk.",
        data={
          "created": created,
          "updated": updated,
          "skipped": skipped,
          "deactivated_missing": missing_deactivated,
          "total_active": cls.count_active(),
        },
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("sync_from_disk failed")
      return LibraryManagerResult(
        success=False,
        message="Could not synchronize the reference library.",
        error_code="sync_failed",
        data={"detail": str(exc)},
      )

  # ------------------------------------------------------------------ CRUD

  @classmethod
  def upload_reference(
    cls,
    file_storage: FileStorage,
    *,
    body_part: str,
    projection: str,
    age_group: str,
    gender: str,
    label: str | None = None,
    notes: str | None = None,
    license_text: str | None = None,
    source: str | None = None,
    uploaded_by: int | None = None,
  ) -> LibraryManagerResult:
    try:
      if not file_storage or not file_storage.filename:
        return LibraryManagerResult(
          success=False,
          message="No image file provided.",
          error_code="missing_file",
        )

      body = ReferenceLibraryService.normalize_body_part(body_part)
      proj = ReferenceLibraryService.normalize_projection(projection) or "Other"
      age = ReferenceLibraryService.normalize_age_group(age_group) or "Adult"
      gen = ReferenceLibraryService.normalize_gender(gender) or "Unisex"

      original = secure_filename(file_storage.filename)
      ext = os.path.splitext(original)[1].lower()
      if ext not in IMAGE_EXTENSIONS:
        return LibraryManagerResult(
          success=False,
          message=f"Unsupported image type. Use: {', '.join(IMAGE_EXTENSIONS)}",
          error_code="invalid_type",
        )

      root = cls.ensure_root()
      folder = os.path.join(root, body.lower(), proj.lower(), age.lower(), gen.lower())
      os.makedirs(folder, exist_ok=True)
      stem = os.path.splitext(original)[0] or "reference"
      stored = f"{stem}_{uuid.uuid4().hex[:8]}{ext}"
      abs_path = os.path.join(folder, stored)
      file_storage.save(abs_path)

      rel = os.path.relpath(abs_path, root).replace("\\", "/")
      meta = cls._read_image_metadata(abs_path)
      public_id = cls._public_id_from_filename(stored, rel)

      row = XrayReferenceImage(
        public_id=public_id,
        body_part=body,
        projection=proj,
        age_group=age,
        gender=gen,
        relative_path=rel,
        original_filename=original,
        stored_filename=stored,
        mime_type=meta.get("mime_type"),
        file_size=meta.get("file_size"),
        width=meta.get("width"),
        height=meta.get("height"),
        content_hash=meta.get("content_hash"),
        label=label or f"Healthy {body} {proj} reference ({age}, {gen})",
        notes=notes or "Real educational healthy radiograph for teaching comparison only.",
        license=license_text or "",
        source=source or "",
        gender_relevant=body in XRAY_GENDER_RELEVANT_BODY_PARTS,
        is_active=True,
        uploaded_by=uploaded_by,
      )
      db.session.add(row)
      db.session.commit()

      try:
        ReferenceLibraryService.rebuild_catalog_from_disk()
      except Exception:
        logger.exception("Catalog rebuild after upload failed (non-fatal)")

      return LibraryManagerResult(
        success=True,
        message="Healthy reference image uploaded.",
        data={"reference": row.to_dict(library_root=root)},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("upload_reference failed")
      return LibraryManagerResult(
        success=False,
        message="Upload failed.",
        error_code="upload_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def bulk_upload(
    cls,
    files: list[FileStorage],
    *,
    body_part: str,
    projection: str,
    age_group: str,
    gender: str,
    uploaded_by: int | None = None,
  ) -> LibraryManagerResult:
    results = []
    ok = 0
    for f in files or []:
      res = cls.upload_reference(
        f,
        body_part=body_part,
        projection=projection,
        age_group=age_group,
        gender=gender,
        uploaded_by=uploaded_by,
      )
      results.append(res.to_dict())
      if res.success:
        ok += 1
    return LibraryManagerResult(
      success=ok > 0,
      message=f"Uploaded {ok} of {len(files or [])} reference image(s).",
      data={"results": results, "uploaded": ok, "total": len(files or [])},
    )

  @classmethod
  def update_metadata(cls, ref_id: int, payload: dict[str, Any]) -> LibraryManagerResult:
    row = cls.get_by_id(ref_id)
    if not row:
      return LibraryManagerResult(success=False, message="Reference not found.", error_code="not_found")
    try:
      if "body_part" in payload and payload["body_part"]:
        row.body_part = ReferenceLibraryService.normalize_body_part(str(payload["body_part"]))
        row.gender_relevant = row.body_part in XRAY_GENDER_RELEVANT_BODY_PARTS
      if "projection" in payload and payload["projection"]:
        row.projection = (
          ReferenceLibraryService.normalize_projection(str(payload["projection"])) or row.projection
        )
      if "age_group" in payload and payload["age_group"]:
        row.age_group = (
          ReferenceLibraryService.normalize_age_group(str(payload["age_group"])) or row.age_group
        )
      if "gender" in payload and payload["gender"]:
        row.gender = ReferenceLibraryService.normalize_gender(str(payload["gender"])) or row.gender
      for key in ("label", "notes", "license", "source"):
        if key in payload and payload[key] is not None:
          setattr(row, key, str(payload[key]))
      if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
      row.updated_at = utc_now()
      db.session.commit()
      try:
        ReferenceLibraryService.rebuild_catalog_from_disk()
      except Exception:
        logger.exception("Catalog rebuild after metadata update failed (non-fatal)")
      return LibraryManagerResult(
        success=True,
        message="Reference metadata updated.",
        data={"reference": row.to_dict(library_root=cls.library_root())},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("update_metadata failed")
      return LibraryManagerResult(
        success=False,
        message="Could not update reference metadata.",
        error_code="update_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def delete_reference(cls, ref_id: int, *, delete_file: bool = True) -> LibraryManagerResult:
    row = cls.get_by_id(ref_id)
    if not row:
      return LibraryManagerResult(success=False, message="Reference not found.", error_code="not_found")
    try:
      root = cls.library_root()
      abs_path = row.absolute_path(root)
      rel = row.relative_path
      db.session.delete(row)
      db.session.commit()
      if delete_file and os.path.isfile(abs_path):
        try:
          os.remove(abs_path)
        except OSError:
          logger.warning("Could not delete reference file %s", abs_path)
      try:
        ReferenceLibraryService.rebuild_catalog_from_disk()
      except Exception:
        logger.exception("Catalog rebuild after delete failed (non-fatal)")
      return LibraryManagerResult(
        success=True,
        message="Reference deleted.",
        data={"relative_path": rel},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("delete_reference failed")
      return LibraryManagerResult(
        success=False,
        message="Could not delete reference.",
        error_code="delete_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def form_options(cls) -> dict[str, Any]:
    total = cls.count_active()
    if total == 0:
      try:
        ReferenceLibraryService.ensure_library()
        total = sum(
          1
          for r in ReferenceLibraryService._load_references()
          if os.path.isfile(r.absolute_path)
        )
      except Exception:
        logger.exception("Could not count disk references for form_options")
    return {
      "body_parts": list(XRAY_BODY_PARTS),
      "projections": list(XRAY_PROJECTIONS),
      "age_groups": list(XRAY_AGE_GROUPS),
      "genders": list(XRAY_REFERENCE_GENDERS),
      "gender_relevant_body_parts": list(XRAY_GENDER_RELEVANT_BODY_PARTS),
      "child_age_max": CHILD_AGE_MAX,
      "total_references": total,
      "library_ready": total > 0,
      "organization": ["body_part", "projection", "age_group", "gender"],
      "storage": "database",
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      "empty_message": EMPTY_LIBRARY_MESSAGE,
    }

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _public_id_from_filename(filename: str, rel: str) -> str:
    stem = os.path.splitext(filename)[0]
    cleaned = re.sub(r"[^a-zA-Z0-9_\-]+", "_", stem).strip("_").lower()
    if cleaned:
      # Ensure uniqueness suffix from path hash when collision
      existing = XrayReferenceImage.query.filter_by(public_id=cleaned).first()
      if not existing:
        return cleaned
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]
    return f"{cleaned or 'ref'}_{digest}"

  @staticmethod
  def _read_image_metadata(path: str) -> dict[str, Any]:
    meta: dict[str, Any] = {
      "file_size": os.path.getsize(path) if os.path.isfile(path) else None,
      "mime_type": {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
      }.get(os.path.splitext(path)[1].lower(), "application/octet-stream"),
      "width": None,
      "height": None,
      "content_hash": None,
    }
    try:
      with open(path, "rb") as f:
        meta["content_hash"] = hashlib.sha256(f.read()).hexdigest()
    except OSError:
      pass
    try:
      with Image.open(path) as img:
        meta["width"], meta["height"] = img.size
    except Exception:
      logger.info("Could not read image dimensions for %s", path)
    return meta
