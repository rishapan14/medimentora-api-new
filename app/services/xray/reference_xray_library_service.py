"""Production Reference X-Ray Library backend (Module 2).

Database-driven CRUD for healthy educational radiographs.
Business logic lives here — Flask controllers stay thin.
"""

from __future__ import annotations

import hashlib
import io
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
from app.models.reference_xray_library_model import (
  REFERENCE_AGE_GROUPS,
  REFERENCE_BODY_PARTS,
  REFERENCE_DIFFICULTIES,
  REFERENCE_GENDERS,
  REFERENCE_GENDER_RELEVANT_BODY_PARTS,
  REFERENCE_ORIENTATIONS,
  REFERENCE_PROJECTIONS,
  ReferenceXrayLibrary,
  reference_library_taxonomy,
)
from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER
from app.services.xray.reference_metadata_service import ReferenceMetadataService
from app.utils import utc_now

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff")
THUMBNAIL_MAX_EDGE = 320

EMPTY_LIBRARY_MESSAGE = (
  "Healthy educational reference is not yet available for this body part. "
  "AI analysis remains available."
)

# Required metadata for a successful upload (Module 4 contract)
REQUIRED_UPLOAD_FIELDS = (
  "body_part",
  "projection",
  "orientation",
  "age_group",
  "gender",
  "difficulty",
  "source",
  "license",
  "description",
  "anatomical_notes",
)


@dataclass
class ServiceResult:
  success: bool
  message: str = ""
  error_code: str | None = None
  data: dict[str, Any] = field(default_factory=dict)
  field_errors: list[dict[str, str]] = field(default_factory=list)

  def to_dict(self) -> dict[str, Any]:
    payload: dict[str, Any] = {
      "success": self.success,
      "message": self.message,
      "error_code": self.error_code,
      "data": self.data,
    }
    if self.field_errors:
      payload["field_errors"] = self.field_errors
    return payload


class ReferenceXrayLibraryService:
  """Scalable backend for the production reference_xray_library table."""

  # ------------------------------------------------------------------ storage

  @classmethod
  def library_root(cls) -> str:
    if has_app_context():
      root = current_app.config.get("XRAY_REFERENCE_LIBRARY_FOLDER")
      if root:
        return os.path.abspath(str(root))
    return os.path.abspath("reference_library")

  @classmethod
  def ensure_root(cls) -> str:
    root = cls.library_root()
    os.makedirs(root, exist_ok=True)
    os.makedirs(os.path.join(root, "_thumbnails"), exist_ok=True)
    return root

  @classmethod
  def resolve_path(cls, relative_or_absolute: str | None) -> str | None:
    """Resolve a library-relative path safely (blocks path traversal)."""
    if not relative_or_absolute:
      return None
    root = os.path.abspath(cls.library_root())
    candidate = relative_or_absolute
    if not os.path.isabs(candidate):
      candidate = os.path.join(root, candidate.replace("\\", "/").lstrip("/"))
    candidate = os.path.abspath(candidate)
    if not candidate.startswith(root + os.sep) and candidate != root:
      logger.warning("Blocked path traversal attempt: %s", relative_or_absolute)
      return None
    if not os.path.isfile(candidate):
      return None
    return candidate

  # ------------------------------------------------------------------ options

  @classmethod
  def form_options(cls) -> dict[str, Any]:
    stats = cls.storage_stats()
    tax = reference_library_taxonomy()
    return {
      **tax,
      "total_references": stats.get("total", 0),
      "active_references": stats.get("active", 0),
      "inactive_references": stats.get("inactive", 0),
      "library_ready": (stats.get("active") or 0) > 0,
      "storage": stats,
      "required_upload_fields": list(REQUIRED_UPLOAD_FIELDS),
      "empty_message": EMPTY_LIBRARY_MESSAGE,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    }

  # ------------------------------------------------------------------ query

  @classmethod
  def get_by_id(cls, ref_id: int) -> ReferenceXrayLibrary | None:
    return db.session.get(ReferenceXrayLibrary, ref_id)

  @classmethod
  def get_by_public_id(cls, public_id: str) -> ReferenceXrayLibrary | None:
    if not public_id:
      return None
    return ReferenceXrayLibrary.query.filter_by(public_id=public_id).first()

  @classmethod
  def count(cls, *, active_only: bool = False) -> int:
    try:
      query = ReferenceXrayLibrary.query
      if active_only:
        query = query.filter_by(is_active=True)
      return query.count()
    except Exception:
      logger.exception("Failed counting reference_xray_library rows")
      return 0

  @classmethod
  def search(
    cls,
    *,
    q: str | None = None,
    body_part: str | None = None,
    projection: str | None = None,
    orientation: str | None = None,
    age_group: str | None = None,
    gender: str | None = None,
    source: str | None = None,
    difficulty: str | None = None,
    is_active: bool | None = True,
    limit: int = 50,
    offset: int = 0,
  ) -> tuple[list[ReferenceXrayLibrary], int]:
    """Filter + paginate. Returns (rows, total_matching)."""
    query = ReferenceXrayLibrary.query
    if is_active is not None:
      query = query.filter_by(is_active=is_active)
    if body_part:
      query = query.filter(ReferenceXrayLibrary.body_part.ilike(body_part.strip()))
    if projection:
      query = query.filter(ReferenceXrayLibrary.projection.ilike(projection.strip()))
    if orientation:
      query = query.filter(ReferenceXrayLibrary.orientation.ilike(orientation.strip()))
    if age_group:
      query = query.filter(ReferenceXrayLibrary.age_group.ilike(age_group.strip()))
    if gender:
      query = query.filter(ReferenceXrayLibrary.gender.ilike(gender.strip()))
    if difficulty:
      query = query.filter(ReferenceXrayLibrary.difficulty.ilike(difficulty.strip()))
    if source:
      query = query.filter(ReferenceXrayLibrary.source.ilike(f"%{source.strip()}%"))
    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        db.or_(
          ReferenceXrayLibrary.title.ilike(like),
          ReferenceXrayLibrary.description.ilike(like),
          ReferenceXrayLibrary.anatomical_notes.ilike(like),
          ReferenceXrayLibrary.source.ilike(like),
          ReferenceXrayLibrary.license.ilike(like),
          ReferenceXrayLibrary.body_part.ilike(like),
          ReferenceXrayLibrary.projection.ilike(like),
          ReferenceXrayLibrary.public_id.ilike(like),
        )
      )

    total = query.count()
    rows = (
      query.order_by(ReferenceXrayLibrary.updated_at.desc(), ReferenceXrayLibrary.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 500))
      .all()
    )
    return rows, total

  @classmethod
  def storage_stats(cls) -> dict[str, Any]:
    root = cls.library_root()
    try:
      total = ReferenceXrayLibrary.query.count()
      active = ReferenceXrayLibrary.query.filter_by(is_active=True).count()
      inactive = total - active
      size_row = (
        db.session.query(db.func.coalesce(db.func.sum(ReferenceXrayLibrary.file_size), 0)).scalar()
      )
      bytes_tracked = int(size_row or 0)
    except Exception:
      logger.exception("storage_stats DB query failed")
      total = active = inactive = bytes_tracked = 0

    disk_bytes = 0
    file_count = 0
    if os.path.isdir(root):
      for dirpath, _dirs, files in os.walk(root):
        for name in files:
          path = os.path.join(dirpath, name)
          try:
            disk_bytes += os.path.getsize(path)
            file_count += 1
          except OSError:
            continue

    by_body: dict[str, int] = {}
    try:
      for body, count in (
        db.session.query(ReferenceXrayLibrary.body_part, db.func.count(ReferenceXrayLibrary.id))
        .filter_by(is_active=True)
        .group_by(ReferenceXrayLibrary.body_part)
        .all()
      ):
        by_body[str(body)] = int(count)
    except Exception:
      logger.exception("storage_stats body_part breakdown failed")

    return {
      "total": total,
      "active": active,
      "inactive": inactive,
      "bytes_tracked": bytes_tracked,
      "bytes_on_disk": disk_bytes,
      "files_on_disk": file_count,
      "library_root": root,
      "by_body_part": by_body,
    }

  # ------------------------------------------------------------------ validate

  @classmethod
  def validate_metadata(cls, payload: dict[str, Any], *, for_upload: bool = True) -> ServiceResult:
    """Validate dataset-ready reference metadata (no DB writes)."""
    result = ReferenceMetadataService.validate(payload, for_upload=for_upload)
    return ServiceResult(
      success=bool(result.get("success")),
      message=str(result.get("message") or ""),
      error_code=result.get("error_code"),
      data=result.get("data") or {},
      field_errors=list(result.get("field_errors") or []),
    )

  # ------------------------------------------------------------------ write

  @classmethod
  def upload(
    cls,
    file_storage: FileStorage,
    metadata: dict[str, Any],
    *,
    uploaded_by: int | None = None,
  ) -> ServiceResult:
    if not file_storage or not file_storage.filename:
      return ServiceResult(
        success=False,
        message="No image file provided.",
        error_code="missing_file",
        field_errors=[{"field": "file", "message": "Image file is required."}],
      )

    validation = cls.validate_metadata(metadata, for_upload=True)
    if not validation.success:
      return validation
    meta = validation.data["metadata"]

    original = secure_filename(file_storage.filename)
    ext = os.path.splitext(original)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
      return ServiceResult(
        success=False,
        message=f"Unsupported image type. Use: {', '.join(IMAGE_EXTENSIONS)}",
        error_code="invalid_type",
        field_errors=[{"field": "file", "message": "Unsupported image type."}],
      )

    # Never allow placeholder/synthetic radiographs into the DB-backed library.
    placeholder_markers = (
      "placeholder",
      "synthetic",
      "not a real patient image",
      "_write_placeholder",
      "educational healthy reference placeholder",
    )
    blob = " ".join(
      str(x or "")
      for x in (
        original,
        meta.get("title"),
        meta.get("description"),
        meta.get("anatomical_notes"),
        meta.get("source"),
        meta.get("license"),
      )
    ).lower()
    if any(m in blob for m in placeholder_markers):
      return ServiceResult(
        success=False,
        message="Placeholder images are not allowed in the healthy reference library.",
        error_code="placeholder_rejected",
        field_errors=[{"field": "file", "message": "Placeholder images are not allowed."}],
      )

    try:
      root = cls.ensure_root()
      body = meta["body_part"]
      proj = meta["projection"]
      age = meta["age_group"]
      gender = meta["gender"]
      orientation = meta["orientation"]

      folder = os.path.join(
        root,
        cls._slug(body),
        cls._slug(proj),
        cls._slug(age),
        cls._slug(gender),
        cls._slug(orientation),
      )
      os.makedirs(folder, exist_ok=True)

      public_id = f"ref_{uuid.uuid4().hex[:16]}"
      stored = f"{public_id}{ext}"
      abs_path = os.path.join(folder, stored)
      file_storage.save(abs_path)

      image_meta = cls._read_image_metadata(abs_path)
      thumb_rel = cls._generate_thumbnail(abs_path, public_id, ext)
      rel = os.path.relpath(abs_path, root).replace("\\", "/")

      title = meta.get("title") or (
        f"Healthy {body} {proj} reference ({age}, {orientation}, {gender})"
      )

      row = ReferenceXrayLibrary(
        title=title,
        body_part=body,
        projection=proj,
        orientation=orientation,
        age_group=age,
        gender=gender,
        image_path=rel,
        thumbnail_path=thumb_rel,
        source=meta.get("source"),
        license=meta.get("license"),
        description=meta.get("description")
        or "Real educational healthy radiograph for teaching comparison only.",
        anatomical_notes=meta.get("anatomical_notes"),
        difficulty=meta.get("difficulty") or "Beginner",
        is_active=True,
        uploaded_by=uploaded_by,
        mime_type=image_meta.get("mime_type"),
        file_size=image_meta.get("file_size"),
        width=image_meta.get("width"),
        height=image_meta.get("height"),
        content_hash=image_meta.get("content_hash"),
        public_id=public_id,
      )
      db.session.add(row)
      db.session.commit()
      logger.info(
        "Reference uploaded id=%s body=%s projection=%s path=%s",
        row.id,
        body,
        proj,
        rel,
      )
      return ServiceResult(
        success=True,
        message="Healthy reference X-ray uploaded.",
        data={"reference": row.to_dict(library_root=root)},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("Reference upload failed")
      return ServiceResult(
        success=False,
        message="Upload failed.",
        error_code="upload_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def bulk_upload(
    cls,
    files: list[FileStorage],
    metadata: dict[str, Any],
    *,
    uploaded_by: int | None = None,
  ) -> ServiceResult:
    if not files:
      return ServiceResult(
        success=False,
        message="No image files provided.",
        error_code="missing_file",
      )
    # Shared taxonomy must be valid once for the batch
    validation = cls.validate_metadata(metadata, for_upload=True)
    if not validation.success:
      return validation

    results = []
    ok = 0
    for f in files:
      res = cls.upload(f, metadata, uploaded_by=uploaded_by)
      results.append(res.to_dict())
      if res.success:
        ok += 1
    return ServiceResult(
      success=ok > 0,
      message=f"Uploaded {ok} of {len(files)} reference image(s).",
      error_code=None if ok > 0 else "bulk_upload_failed",
      data={"results": results, "uploaded": ok, "total": len(files)},
    )

  @classmethod
  def bulk_upload_zip(
    cls,
    zip_storage: FileStorage,
    metadata: dict[str, Any],
    *,
    uploaded_by: int | None = None,
  ) -> ServiceResult:
    """Extract image files from a ZIP and upload with shared metadata."""
    import tempfile
    import zipfile

    if not zip_storage or not zip_storage.filename:
      return ServiceResult(
        success=False,
        message="No ZIP file provided.",
        error_code="missing_file",
        field_errors=[{"field": "file", "message": "ZIP file is required."}],
      )

    name = zip_storage.filename.lower()
    if not name.endswith(".zip"):
      return ServiceResult(
        success=False,
        message="Only .zip archives are supported for bulk ZIP upload.",
        error_code="invalid_type",
        field_errors=[{"field": "file", "message": "File must be a .zip archive."}],
      )

    validation = cls.validate_metadata(metadata, for_upload=True)
    if not validation.success:
      return validation

    extracted: list[FileStorage] = []
    try:
      raw = zip_storage.read()
      with tempfile.TemporaryDirectory(prefix="ref_zip_") as tmp:
        zip_path = os.path.join(tmp, "upload.zip")
        with open(zip_path, "wb") as fh:
          fh.write(raw)
        with zipfile.ZipFile(zip_path, "r") as zf:
          extract_root = os.path.abspath(os.path.join(tmp, "extract"))
          os.makedirs(extract_root, exist_ok=True)
          for info in zf.infolist():
            if info.is_dir():
              continue
            base = os.path.basename(info.filename)
            if not base or base.startswith(".") or base.startswith("__"):
              continue
            ext = os.path.splitext(base)[1].lower()
            if ext not in IMAGE_EXTENSIONS:
              continue
            safe_name = secure_filename(base) or f"reference{ext}"
            target = os.path.abspath(os.path.join(extract_root, f"{uuid.uuid4().hex[:8]}_{safe_name}"))
            if not target.startswith(extract_root + os.sep):
              logger.warning("Skipped unsafe zip entry: %s", info.filename)
              continue
            with zf.open(info) as src, open(target, "wb") as dst:
              dst.write(src.read())
            with open(target, "rb") as fh:
              data = fh.read()
            extracted.append(
              FileStorage(
                stream=io.BytesIO(data),
                filename=safe_name,
                content_type="application/octet-stream",
              )
            )
    except zipfile.BadZipFile:
      return ServiceResult(
        success=False,
        message="Invalid or corrupt ZIP archive.",
        error_code="invalid_zip",
      )
    except Exception as exc:
      logger.exception("ZIP extract failed")
      return ServiceResult(
        success=False,
        message="Could not read ZIP archive.",
        error_code="zip_failed",
        data={"detail": str(exc)},
      )

    if not extracted:
      return ServiceResult(
        success=False,
        message="ZIP contained no supported image files "
        f"({', '.join(IMAGE_EXTENSIONS)}).",
        error_code="empty_zip",
      )

    return cls.bulk_upload(extracted, metadata, uploaded_by=uploaded_by)

  @classmethod
  def update_metadata(cls, ref_id: int, payload: dict[str, Any]) -> ServiceResult:
    row = cls.get_by_id(ref_id)
    if not row:
      return ServiceResult(success=False, message="Reference not found.", error_code="not_found")

    # Partial update — only validate fields that are present
    partial = {k: v for k, v in payload.items() if v is not None}
    check_payload = {
      "body_part": partial.get("body_part", row.body_part),
      "projection": partial.get("projection", row.projection),
      "orientation": partial.get("orientation", row.orientation),
      "age_group": partial.get("age_group", row.age_group),
      "gender": partial.get("gender", row.gender),
      "difficulty": partial.get("difficulty", row.difficulty),
      "title": partial.get("title", row.title),
      "source": partial.get("source", row.source),
      "license": partial.get("license", row.license),
      "description": partial.get("description", row.description),
      "anatomical_notes": partial.get("anatomical_notes", row.anatomical_notes),
    }
    validation = cls.validate_metadata(check_payload, for_upload=True)
    if not validation.success:
      return validation
    meta = validation.data["metadata"]

    try:
      row.body_part = meta["body_part"]
      row.projection = meta["projection"]
      row.orientation = meta["orientation"]
      row.age_group = meta["age_group"]
      row.gender = meta["gender"]
      row.difficulty = meta["difficulty"]
      if "title" in payload and payload["title"] is not None:
        row.title = str(payload["title"]).strip() or row.title
      elif meta.get("title"):
        row.title = meta["title"]
      for key in ("source", "license", "description", "anatomical_notes"):
        if key in payload:
          setattr(row, key, str(payload[key]) if payload[key] is not None else None)
      if "is_active" in payload:
        row.is_active = bool(payload["is_active"])
      row.updated_at = utc_now()
      db.session.commit()
      return ServiceResult(
        success=True,
        message="Reference metadata updated.",
        data={"reference": row.to_dict(library_root=cls.library_root())},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("update_metadata failed id=%s", ref_id)
      return ServiceResult(
        success=False,
        message="Could not update reference metadata.",
        error_code="update_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def set_active(cls, ref_id: int, *, active: bool) -> ServiceResult:
    row = cls.get_by_id(ref_id)
    if not row:
      return ServiceResult(success=False, message="Reference not found.", error_code="not_found")
    try:
      row.is_active = bool(active)
      row.updated_at = utc_now()
      db.session.commit()
      state = "reactivated" if active else "deactivated"
      logger.info("Reference %s id=%s", state, ref_id)
      return ServiceResult(
        success=True,
        message=f"Reference {state}.",
        data={"reference": row.to_dict(library_root=cls.library_root())},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("set_active failed id=%s", ref_id)
      return ServiceResult(
        success=False,
        message="Could not update active state.",
        error_code="update_failed",
        data={"detail": str(exc)},
      )

  @classmethod
  def delete(cls, ref_id: int, *, delete_files: bool = True) -> ServiceResult:
    row = cls.get_by_id(ref_id)
    if not row:
      return ServiceResult(success=False, message="Reference not found.", error_code="not_found")
    try:
      root = cls.library_root()
      image_abs = row.absolute_image_path(root)
      thumb_abs = row.absolute_thumbnail_path(root)
      image_path = row.image_path
      db.session.delete(row)
      db.session.commit()
      if delete_files:
        for path in (image_abs, thumb_abs):
          if path and os.path.isfile(path):
            try:
              os.remove(path)
            except OSError:
              logger.warning("Could not delete file %s", path)
      logger.info("Reference deleted id=%s path=%s", ref_id, image_path)
      return ServiceResult(
        success=True,
        message="Reference deleted.",
        data={"image_path": image_path},
      )
    except Exception as exc:
      db.session.rollback()
      logger.exception("delete failed id=%s", ref_id)
      return ServiceResult(
        success=False,
        message="Could not delete reference.",
        error_code="delete_failed",
        data={"detail": str(exc)},
      )

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return cleaned or "other"

  @classmethod
  def _read_image_metadata(cls, abs_path: str) -> dict[str, Any]:
    meta: dict[str, Any] = {
      "file_size": os.path.getsize(abs_path) if os.path.isfile(abs_path) else None,
      "mime_type": None,
      "width": None,
      "height": None,
      "content_hash": None,
    }
    try:
      with open(abs_path, "rb") as fh:
        meta["content_hash"] = hashlib.sha256(fh.read()).hexdigest()
    except OSError:
      logger.warning("Could not hash %s", abs_path)

    try:
      with Image.open(abs_path) as img:
        meta["width"], meta["height"] = img.size
        fmt = (img.format or "").upper()
        meta["mime_type"] = {
          "JPEG": "image/jpeg",
          "PNG": "image/png",
          "WEBP": "image/webp",
          "TIFF": "image/tiff",
        }.get(fmt, "application/octet-stream")
    except Exception:
      logger.warning("Could not read image dimensions for %s", abs_path)
      ext = os.path.splitext(abs_path)[1].lower()
      meta["mime_type"] = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
      }.get(ext, "application/octet-stream")
    return meta

  @classmethod
  def _generate_thumbnail(cls, abs_path: str, public_id: str, ext: str) -> str | None:
    """Create a small JPEG/PNG thumbnail under _thumbnails/ (best-effort)."""
    try:
      root = cls.ensure_root()
      thumb_dir = os.path.join(root, "_thumbnails")
      os.makedirs(thumb_dir, exist_ok=True)
      out_name = f"{public_id}_thumb.jpg"
      out_abs = os.path.join(thumb_dir, out_name)
      with Image.open(abs_path) as img:
        img = img.convert("RGB")
        img.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE))
        img.save(out_abs, format="JPEG", quality=82, optimize=True)
      return os.path.relpath(out_abs, root).replace("\\", "/")
    except Exception:
      logger.exception("Thumbnail generation failed for %s", abs_path)
      return None
