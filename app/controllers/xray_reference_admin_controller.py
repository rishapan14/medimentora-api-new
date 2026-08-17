"""Admin API for the production Reference X-Ray Library (Module 2 backend).

Thin controllers — all business logic lives in ReferenceXrayLibraryService.
"""

from __future__ import annotations

import os

from flask import request, send_file
from flask_jwt_extended import current_user

from app.helpers.response import error_response, success_response
from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER
from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService


def _collect_files():
  files = []
  if "files" in request.files:
    files.extend([f for f in request.files.getlist("files") if f and f.filename])
  if "file" in request.files:
    f = request.files.get("file")
    if f and f.filename:
      files.append(f)
  for key in request.files:
    if key in ("file", "files"):
      continue
    for f in request.files.getlist(key):
      if f and f.filename:
        files.append(f)
  return files


def _metadata_from_form_or_json() -> dict:
  if request.is_json:
    payload = request.get_json(silent=True) or {}
    return dict(payload)
  form = request.form
  return {
    "title": form.get("title"),
    "body_part": form.get("body_part") or form.get("bodyPart"),
    "projection": form.get("projection"),
    "orientation": form.get("orientation"),
    "age_group": form.get("age_group") or form.get("ageGroup"),
    "gender": form.get("gender"),
    "source": form.get("source"),
    "license": form.get("license"),
    "description": form.get("description"),
    "anatomical_notes": form.get("anatomical_notes") or form.get("anatomicalNotes"),
    "difficulty": form.get("difficulty"),
  }


def _parse_bool(raw, default: bool | None = None) -> bool | None:
  if raw is None:
    return default
  return str(raw).lower() in ("1", "true", "yes")


def admin_options():
  """GET /api/xray/admin/references/options"""
  return success_response(
    "Reference library options retrieved.",
    ReferenceXrayLibraryService.form_options(),
  )


def admin_stats():
  """GET /api/xray/admin/references/stats — upload + storage statistics."""
  return success_response(
    "Reference library statistics retrieved.",
    {
      "storage": ReferenceXrayLibraryService.storage_stats(),
      "options": ReferenceXrayLibraryService.form_options(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def admin_list_references():
  """GET /api/xray/admin/references — searchable, filterable, paginated catalog."""
  include_inactive = _parse_bool(request.args.get("include_inactive"), False)
  active_only = not include_inactive
  is_active_param = request.args.get("is_active")
  if is_active_param is not None:
    is_active = _parse_bool(is_active_param)
  else:
    is_active = True if active_only else None

  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  try:
    offset = int(request.args.get("offset") or 0)
  except (TypeError, ValueError):
    offset = 0

  rows, total = ReferenceXrayLibraryService.search(
    q=request.args.get("q") or request.args.get("search"),
    body_part=request.args.get("body_part") or request.args.get("bodyPart"),
    projection=request.args.get("projection"),
    orientation=request.args.get("orientation"),
    age_group=request.args.get("age_group") or request.args.get("ageGroup"),
    gender=request.args.get("gender"),
    source=request.args.get("source"),
    difficulty=request.args.get("difficulty"),
    is_active=is_active,
    limit=limit,
    offset=offset,
  )
  root = ReferenceXrayLibraryService.library_root()
  return success_response(
    "Reference library catalog retrieved.",
    {
      "references": [r.to_dict(library_root=root) for r in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "options": ReferenceXrayLibraryService.form_options(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def admin_get_reference(ref_id: int):
  """GET /api/xray/admin/references/<id>"""
  row = ReferenceXrayLibraryService.get_by_id(ref_id)
  if not row:
    return error_response("Reference not found.", 404)
  return success_response(
    "Reference retrieved.",
    {"reference": row.to_dict(library_root=ReferenceXrayLibraryService.library_root())},
  )


def admin_upload_reference():
  """POST /api/xray/admin/references — upload one healthy reference (+ required metadata)."""
  files = _collect_files()
  if not files:
    return error_response(
      "No image file provided.",
      400,
      {"field_errors": [{"field": "file", "message": "Image file is required."}]},
    )

  result = ReferenceXrayLibraryService.upload(
    files[0],
    _metadata_from_form_or_json(),
    uploaded_by=getattr(current_user, "id", None),
  )
  if not result.success:
    code = 400 if result.error_code == "validation_error" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data, 201)


def admin_bulk_upload():
  """POST /api/xray/admin/references/bulk — multi-file upload with shared metadata."""
  files = _collect_files()
  if not files:
    return error_response("No image files provided.", 400)

  result = ReferenceXrayLibraryService.bulk_upload(
    files,
    _metadata_from_form_or_json(),
    uploaded_by=getattr(current_user, "id", None),
  )
  if not result.success:
    code = 400 if result.error_code == "validation_error" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data, 201)


def admin_bulk_upload_zip():
  """POST /api/xray/admin/references/bulk-zip — ZIP of images + shared metadata."""
  zip_file = request.files.get("file") or request.files.get("zip")
  if not zip_file or not zip_file.filename:
    return error_response(
      "No ZIP file provided.",
      400,
      {"field_errors": [{"field": "file", "message": "ZIP file is required."}]},
    )

  result = ReferenceXrayLibraryService.bulk_upload_zip(
    zip_file,
    _metadata_from_form_or_json(),
    uploaded_by=getattr(current_user, "id", None),
  )
  if not result.success:
    code = 400 if result.error_code in ("validation_error", "invalid_type", "invalid_zip", "empty_zip") else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data, 201)


def admin_update_reference(ref_id: int):
  """PATCH /api/xray/admin/references/<id> — edit metadata."""
  payload = request.get_json(silent=True) or {}
  result = ReferenceXrayLibraryService.update_metadata(ref_id, payload)
  if not result.success:
    code = 404 if result.error_code == "not_found" else 400 if result.error_code == "validation_error" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data)


def admin_deactivate_reference(ref_id: int):
  """POST /api/xray/admin/references/<id>/deactivate"""
  result = ReferenceXrayLibraryService.set_active(ref_id, active=False)
  if not result.success:
    code = 404 if result.error_code == "not_found" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data)


def admin_reactivate_reference(ref_id: int):
  """POST /api/xray/admin/references/<id>/reactivate"""
  result = ReferenceXrayLibraryService.set_active(ref_id, active=True)
  if not result.success:
    code = 404 if result.error_code == "not_found" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data)


def admin_delete_reference(ref_id: int):
  """DELETE /api/xray/admin/references/<id>"""
  delete_files = _parse_bool(request.args.get("delete_file"), True)
  result = ReferenceXrayLibraryService.delete(ref_id, delete_files=bool(delete_files))
  if not result.success:
    code = 404 if result.error_code == "not_found" else 422
    return error_response(result.message, code, result.to_dict())
  return success_response(result.message, result.data)


def admin_preview_reference(ref_id: int):
  """GET /api/xray/admin/references/<id>/file — preview original image."""
  row = ReferenceXrayLibraryService.get_by_id(ref_id)
  if not row:
    return error_response("Reference not found.", 404)

  thumb = _parse_bool(request.args.get("thumbnail"), False)
  path = None
  if thumb and row.thumbnail_path:
    path = ReferenceXrayLibraryService.resolve_path(row.thumbnail_path)
  if not path:
    path = ReferenceXrayLibraryService.resolve_path(row.image_path)
  if not path:
    return error_response("Reference image file is missing on disk.", 404)

  mime = row.mime_type or "application/octet-stream"
  return send_file(
    path,
    mimetype=mime,
    as_attachment=False,
    download_name=os.path.basename(path),
  )


def admin_sync_from_disk():
  """
  POST /api/xray/admin/references/sync

  Scan the reference library folder tree, extract metadata from folder
  structure, generate thumbnails, and upsert DB rows automatically.
  """
  from app.services.xray.reference_catalog_service import ReferenceCatalogService

  result = ReferenceCatalogService.sync(
    uploaded_by=getattr(current_user, "id", None),
  )
  ok = bool(result.get("success"))
  if not ok:
    return error_response(
      "Catalog sync failed.",
      422,
      result,
    )
  return success_response(
    f"Catalog synced: {result.get('created', 0)} created, "
    f"{result.get('updated', 0)} updated, "
    f"{result.get('deactivated', 0)} deactivated.",
    result,
  )
