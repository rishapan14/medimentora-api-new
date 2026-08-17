"""HTTP controllers for AI-Assisted X-Ray Analysis."""

import os

from flask import current_app, request, send_file
from flask_jwt_extended import current_user

from app.helpers.response import error_response, success_response
from app.models.xray_analysis_model import XRAY_BODY_PARTS, XRAY_MEDICAL_DISCLAIMER
from app.services.xray.patient_info import PatientInfoService
from app.services.xray.preprocess_service import XrayPreprocessService
from app.services.xray.upload_service import XrayUploadService


def _collect_upload_files():
  """Collect files from multipart fields: files, files[], file."""
  files = []
  files.extend(request.files.getlist("files"))
  files.extend(request.files.getlist("files[]"))
  single = request.files.get("file")
  if single and single.filename:
    files.append(single)
  seen = set()
  unique = []
  for f in files:
    if f is None or id(f) in seen:
      continue
    seen.add(id(f))
    unique.append(f)
  return unique


def _clinical_payload_from_request(*, require_clinical: bool) -> tuple[dict | None, object | None]:
  """
  Extract patient clinical fields from multipart form or JSON.

  Returns (error_response_or_None, PatientClinicalInfo_or_None).
  When require_clinical is True, missing/invalid fields return a 400 response.
  When False, incomplete clinical data is ignored (upload-only path).
  """
  if request.files or request.form:
    raw = {k: v for k, v in request.form.items()}
  else:
    raw = dict(request.get_json(silent=True) or {})

  # Intentional clinical payload (body_part alone is legacy upload metadata, not clinical).
  clinical_intent_keys = {
    "patient_age",
    "age",
    "patientAge",
    "gender",
    "sex",
    "symptoms",
    "reason_for_exam",
    "reason",
    "reasonForExam",
    "smoking_history",
    "smokingHistory",
    "projection",
    "view",
    "viewPosition",
    "clinical_extras",
    "clinicalExtras",
  }
  submitted = any(k in raw and raw.get(k) not in (None, "") for k in clinical_intent_keys)

  if not require_clinical and not submitted:
    return None, None

  result = PatientInfoService.validate(raw)
  if not result.ok:
    return (
      error_response(
        "Patient clinical information validation failed.",
        400,
        {
          "errors": result.error_messages(),
          "field_errors": [e.to_dict() for e in result.errors],
          "form_options": PatientInfoService.form_options(),
          "disclaimer": XRAY_MEDICAL_DISCLAIMER,
        },
      ),
      None,
    )
  return None, result.data


def clinical_form_options():
  """GET /api/xray/clinical-options — enums/limits for the Patient Clinical Information form."""
  return success_response(
    "Patient clinical form options retrieved.",
    {
      **PatientInfoService.form_options(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def reference_library_options():
  """GET /api/xray/references/options — reference library enums + readiness."""
  from app.services.xray.reference_library import ReferenceLibraryService

  return success_response(
    "Educational reference library options retrieved.",
    ReferenceLibraryService.form_options(),
  )


def list_reference_images():
  """GET /api/xray/references — list healthy educational references (optional filters)."""
  from app.services.xray.reference_library import ReferenceLibraryService

  body_part = request.args.get("body_part") or request.args.get("bodyPart")
  projection = request.args.get("projection") or request.args.get("view")
  age_group = request.args.get("age_group") or request.args.get("ageGroup")
  gender = request.args.get("gender")
  refs = ReferenceLibraryService.list_references(
    body_part=body_part,
    projection=projection,
    age_group=age_group,
    gender=gender,
  )
  return success_response(
    "Educational reference images retrieved.",
    {
      "references": [r.to_dict() for r in refs],
      "total": len(refs),
      "filters": {
        "body_part": body_part,
        "projection": projection,
        "age_group": age_group,
        "gender": gender,
      },
      "options": ReferenceLibraryService.form_options(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def select_reference_image():
  """
  GET /api/xray/references/select

  Auto-select the best educational healthy reference for body_part / projection / age / gender.
  Query: body_part, projection|view, patient_age|age, gender, xray_id (optional — loads clinical from row)
  """
  from app.services.xray.reference_library import ReferenceLibraryService

  xray_id = request.args.get("xray_id") or request.args.get("xrayId")
  if xray_id:
    try:
      xid = int(xray_id)
    except (TypeError, ValueError):
      return error_response("xray_id must be an integer.", 400)
    row = XrayUploadService.get_for_user(xid, current_user.id)
    if not row:
      return error_response("X-ray analysis not found.", 404)
    result = ReferenceLibraryService.select_for_xray_row(row)
  else:
    age_raw = request.args.get("patient_age") or request.args.get("age")
    age = None
    if age_raw not in (None, ""):
      try:
        age = int(age_raw)
      except (TypeError, ValueError):
        return error_response("patient_age must be an integer.", 400)
    result = ReferenceLibraryService.select_reference(
      body_part=request.args.get("body_part") or request.args.get("bodyPart"),
      patient_age=age,
      gender=request.args.get("gender"),
      projection=request.args.get("projection") or request.args.get("view"),
    )

  # Soft empty is a successful educational response (no crash / no hard 404)
  if result.error_code == "empty_library":
    return success_response(
      result.message or "No healthy reference image is currently available.",
      {
        **result.to_dict(),
        "library_empty": True,
      },
    )
  if not result.success:
    return error_response(
      result.message or "Could not select a reference image.",
      422,
      result.to_dict(),
    )
  return success_response("Educational healthy reference selected.", result.to_dict())


def download_reference_image(reference_id: str):
  """GET /api/xray/references/<reference_id>/file — serve a library reference image."""
  from app.services.xray.reference_library import ReferenceLibraryService

  # Try legacy catalog first
  refs = {r.id: r for r in ReferenceLibraryService.list_references()}
  ref = refs.get(reference_id)
  if not ref:
    for candidate in ReferenceLibraryService.list_references():
      if candidate.relative_path.endswith(reference_id) or os.path.basename(
        candidate.absolute_path
      ) == reference_id:
        ref = candidate
        break

  if ref:
    path = ReferenceLibraryService.resolve_file(ref.absolute_path)
    if not path:
      return error_response("Reference image file is missing.", 404)
    return send_file(
      path,
      mimetype=ref.mime_type(),
      as_attachment=False,
      download_name=os.path.basename(path),
    )

  # Fall back to new reference_xray_library by public_id or numeric id
  from app.services.xray.reference_xray_library_service import ReferenceXrayLibraryService

  row = ReferenceXrayLibraryService.get_by_public_id(reference_id)
  if not row:
    try:
      row = ReferenceXrayLibraryService.get_by_id(int(reference_id))
    except (TypeError, ValueError):
      pass
  if not row:
    return error_response("Reference image not found.", 404)

  resolved = ReferenceXrayLibraryService.resolve_path(row.image_path)
  if not resolved:
    return error_response("Reference image file is missing.", 404)

  mime = row.mime_type or "application/octet-stream"
  return send_file(
    resolved,
    mimetype=mime,
    as_attachment=False,
    download_name=os.path.basename(resolved),
  )


def upload_xrays():
  """POST /api/xray/upload — accept one or more X-ray images (+ optional clinical info)."""
  from app.services.admin.settings_admin_service import AdminSettingsService

  blocked = AdminSettingsService.deny_if_maintenance()
  if blocked:
    return blocked
  blocked = AdminSettingsService.deny_if_feature_disabled(
    "ai_xray_analysis_enabled",
    message="AI X-Ray Analysis is currently disabled by the administrator.",
  )
  if blocked:
    return blocked

  files = _collect_upload_files()
  err, clinical = _clinical_payload_from_request(require_clinical=False)
  if err:
    return err

  body_part = None
  if clinical:
    body_part = clinical.body_part
  else:
    body_part = request.form.get("body_part") or request.form.get("bodyPart")

  auto_raw = request.form.get("auto_preprocess")
  if auto_raw is None:
    auto_preprocess = bool(current_app.config.get("XRAY_AUTO_PREPROCESS", True))
  else:
    auto_preprocess = str(auto_raw).lower() in ("1", "true", "yes")

  result = XrayUploadService.upload_batch(
    user_id=current_user.id,
    files=files,
    body_part=body_part,
    clinical=clinical,
  )

  if not result.success:
    return error_response(
      "X-ray upload validation failed.",
      400,
      {"errors": result.errors, **result.to_dict()},
    )

  payload = result.to_dict()
  if clinical:
    payload["patient_clinical"] = clinical.to_dict()
  if auto_preprocess and result.files:
    ids = [f.xray_id for f in result.files]
    payload["preprocess_results"] = XrayPreprocessService.preprocess_batch_for_user(
      current_user.id,
      ids,
      force=False,
    )

  return success_response(
    "X-ray image(s) uploaded successfully.",
    payload,
    201,
  )


def list_history():
  """GET /api/xray/history — list the current user's X-ray uploads (Phase 15 filters + pagination)."""
  body_part = request.args.get("body_part")
  status = request.args.get("status")
  gender = request.args.get("gender")
  smoking_history = request.args.get("smoking_history") or request.args.get("smokingHistory")
  date_from = request.args.get("date_from") or request.args.get("dateFrom")
  date_to = request.args.get("date_to") or request.args.get("dateTo")

  age_min = None
  age_max = None
  age_min_raw = request.args.get("age_min") or request.args.get("ageMin")
  age_max_raw = request.args.get("age_max") or request.args.get("ageMax")
  try:
    if age_min_raw not in (None, ""):
      age_min = int(age_min_raw)
    if age_max_raw not in (None, ""):
      age_max = int(age_max_raw)
  except (TypeError, ValueError):
    return error_response("age_min and age_max must be integers.", 400)

  limit = 24
  offset = 0
  limit_raw = request.args.get("limit") or request.args.get("page_size")
  offset_raw = request.args.get("offset")
  page_raw = request.args.get("page")
  try:
    if limit_raw not in (None, ""):
      limit = max(1, min(100, int(limit_raw)))
    if offset_raw not in (None, ""):
      offset = max(0, int(offset_raw))
    elif page_raw not in (None, ""):
      page = max(1, int(page_raw))
      offset = (page - 1) * limit
  except (TypeError, ValueError):
    return error_response("limit, offset, and page must be integers.", 400)

  try:
    rows, total = XrayUploadService.list_history(
      current_user.id,
      body_part=body_part,
      status=status,
      gender=gender,
      smoking_history=smoking_history,
      age_min=age_min,
      age_max=age_max,
      date_from=date_from or None,
      date_to=date_to or None,
      limit=limit,
      offset=offset,
    )
  except ValueError as exc:
    return error_response(f"Invalid date filter: {exc}", 400)

  return success_response(
    "X-ray history retrieved.",
    {
      "history": [r.to_history_card() for r in rows],
      "total": total,
      "limit": limit,
      "offset": offset,
      "has_more": (offset + len(rows)) < total,
      "body_parts": list(XRAY_BODY_PARTS),
      "form_options": PatientInfoService.form_options(),
      "filters_applied": {
        "body_part": body_part or None,
        "status": status or None,
        "gender": gender or None,
        "smoking_history": smoking_history or None,
        "age_min": age_min,
        "age_max": age_max,
        "date_from": date_from or None,
        "date_to": date_to or None,
        "limit": limit,
        "offset": offset,
      },
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def xray_dashboard():
  """GET /api/xray/dashboard — Module 10 dashboard widgets for the current user."""
  from app.services.xray.dashboard_service import XrayDashboardService

  payload = XrayDashboardService.build_for_user(current_user.id)
  return success_response(
    "X-ray dashboard retrieved.",
    {
      **payload,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def get_xray(xray_id: int):
  """GET /api/xray/<id> — get one owned X-ray record."""
  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)
  include_explanation = (request.args.get("include_explanation") or "").lower() in ("1", "true", "yes")
  return success_response(
    "X-ray retrieved.",
    {
      "xray": row.to_dict(include_explanation=include_explanation),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def delete_xray(xray_id: int):
  """DELETE /api/xray/<id> — delete an owned X-ray and its files."""
  deleted = XrayUploadService.delete_for_user(xray_id, current_user.id)
  if not deleted:
    return error_response("X-ray analysis not found.", 404)
  return success_response("X-ray deleted.")


def export_xray(xray_id: int):
  """
  GET /api/xray/<id>/export?format=json|txt

  Educational export including patient clinical information (supporting context only).
  Does not include raw image bytes.
  """
  from flask import Response

  from app.services.xray.export_service import XrayExportService

  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)

  fmt = request.args.get("format") or request.args.get("fmt") or "json"
  content, mimetype, filename = XrayExportService.export(row, fmt)
  return Response(
    content,
    mimetype=mimetype,
    headers={
      "Content-Disposition": f'attachment; filename="{filename}"',
      "X-MediMentora-Export": "educational-only",
    },
  )


def download_original(xray_id: int):
  """GET /api/xray/<id>/file — download/view the original uploaded image (owner only)."""
  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)
  path = row.file_path
  if path and not os.path.isabs(path):
    path = os.path.abspath(path)
  if not path or not os.path.isfile(path):
    return error_response("X-ray file is missing from storage.", 404)

  mime = "image/jpeg"
  if (row.file_type or "").lower() == "png":
    mime = "image/png"
  try:
    return send_file(
      path,
      mimetype=mime,
      as_attachment=False,
      download_name=row.filename or os.path.basename(path),
    )
  except FileNotFoundError:
    return error_response("X-ray file is missing from storage.", 404)


def preprocess_xray(xray_id: int):
  """POST /api/xray/<id>/preprocess — run OpenCV preprocessing (Module 3)."""
  force = (request.args.get("force") or "").lower() in ("1", "true", "yes")
  if request.is_json:
    force = force or bool((request.get_json(silent=True) or {}).get("force"))

  row, result = XrayPreprocessService.preprocess_for_user(
    xray_id,
    current_user.id,
    force=force,
  )
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Preprocessing failed.",
      422,
      {
        "xray": row.to_dict(),
        "preprocess": result.to_dict(),
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
    )

  return success_response(
    "X-ray preprocessing completed.",
    {
      "xray": row.to_dict(),
      "preprocess": result.to_dict(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def download_preprocessed(xray_id: int):
  """GET /api/xray/<id>/preprocessed — serve the preprocessed image (owner only)."""
  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)
  if not row.preprocessed_path or not os.path.isfile(row.preprocessed_path):
    return error_response(
      "Preprocessed image not found. Run POST /api/xray/<id>/preprocess first.",
      404,
    )
  return send_file(
    row.preprocessed_path,
    mimetype="image/png",
    as_attachment=False,
    download_name=f"xray_{xray_id}_preprocessed.png",
  )


def analyze_xrays():
  """
  POST /api/xray/analyze

  Modes:
  1) multipart upload + patient clinical fields → upload → preprocess → vision
  2) JSON {"xray_ids": [...], patient clinical fields...} → analyze existing uploads

  Multipart clinical fields:
    patient_age, gender, body_part, symptoms, reason_for_exam, smoking_history, files[]
  """
  from app.services.admin.settings_admin_service import AdminSettingsService
  from app.services.xray.vision_service import VisionModelService

  blocked = AdminSettingsService.deny_if_maintenance()
  if blocked:
    return blocked
  blocked = AdminSettingsService.deny_if_feature_disabled(
    "ai_xray_analysis_enabled",
    message="AI X-Ray Analysis is currently disabled by the administrator.",
  )
  if blocked:
    return blocked

  # Analyze with new uploads requires full clinical info
  require_clinical = bool(request.files)
  err, clinical = _clinical_payload_from_request(require_clinical=require_clinical)
  if err:
    return err

  # JSON path may omit clinical if rows already have it; still validate if any field sent
  if not require_clinical and clinical is None:
    # optional clinical on JSON — already handled; if user sent partial invalid, caught above
    pass

  body_part = clinical.body_part if clinical else None
  xray_ids: list[int] = []

  if request.files:
    files = _collect_upload_files()
    upload = XrayUploadService.upload_batch(
      current_user.id,
      files,
      body_part=body_part,
      clinical=clinical,
    )
    if not upload.success:
      return error_response(
        "X-ray upload validation failed.",
        400,
        {"errors": upload.errors, **upload.to_dict()},
      )
    xray_ids = [f.xray_id for f in upload.files]
    logger_msg_clinical = True
  else:
    data = request.get_json(silent=True) or {}
    if not body_part:
      body_part = data.get("body_part") or data.get("bodyPart")
    raw_ids = data.get("xray_ids") or data.get("ids") or []
    if data.get("xray_id") is not None:
      raw_ids = [data.get("xray_id")]
    try:
      xray_ids = [int(i) for i in raw_ids]
    except (TypeError, ValueError):
      return error_response("xray_ids must be a list of integers.", 400)
    logger_msg_clinical = bool(clinical)

  if not xray_ids:
    return error_response(
      "Provide multipart X-ray files or JSON body with xray_ids.",
      400,
    )

  if logger_msg_clinical and clinical:
    import logging

    logging.getLogger(__name__).info(
      "Patient clinical information received for analyze user=%s age=%s body_part=%s ids=%s",
      current_user.id,
      clinical.patient_age,
      clinical.body_part,
      xray_ids,
    )

  analyses = VisionModelService.analyze_batch_for_user(
    current_user.id,
    xray_ids,
    body_part=body_part,
    clinical=clinical,
  )
  any_ok = any(a.get("success") for a in analyses)
  payload = {
    "analyses": analyses,
    "total": len(analyses),
    "succeeded": sum(1 for a in analyses if a.get("success")),
    "patient_clinical": clinical.to_dict() if clinical else None,
    "disclaimer": XRAY_MEDICAL_DISCLAIMER,
  }
  if not any_ok:
    return error_response(
      "X-ray vision analysis failed.",
      422,
      payload,
    )
  return success_response(
    "X-ray vision analysis completed.",
    payload,
  )


def reanalyze_xray(xray_id: int):
  """POST /api/xray/<id>/reanalyze — re-run preprocess + vision (owner only)."""
  from app.services.xray.vision_service import VisionModelService

  row, result = VisionModelService.reanalyze_for_user(xray_id, current_user.id)
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Re-analysis failed.",
      422,
      {
        "xray": row.to_dict(),
        "vision": result.to_dict(),
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
    )
  return success_response(
    "X-ray re-analyzed successfully.",
    {
      "xray": row.to_dict(include_explanation=True),
      "vision": result.to_dict(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def explain_xray(xray_id: int):
  """
  POST /api/xray/<id>/explain

  Regenerate educational explanation from stored findings only.
  Never sends the X-ray image to Gemini.
  """
  from app.services.xray.vision_service import VisionModelService

  row, explanation = VisionModelService.explain_for_user(xray_id, current_user.id)
  if explanation.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not explanation.success:
    return error_response(
      explanation.message or "Explanation failed.",
      422,
      {
        "xray": row.to_dict(include_explanation=True),
        "explanation": explanation.to_dict(),
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
    )
  return success_response(
    "Educational explanation generated.",
    {
      "xray": row.to_dict(include_explanation=True),
      "explanation": explanation.to_dict(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def generate_heatmap(xray_id: int):
  """POST /api/xray/<id>/heatmap — (re)generate Grad-CAM / attention heatmap."""
  from app.services.xray.heatmap import HeatmapService

  row, result = HeatmapService.generate_for_user(
    xray_id,
    current_user.id,
    force=True,
    prefer_gradcam=True,
  )
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Heatmap generation failed.",
      422,
      {
        "xray": row.to_dict(include_explanation=True),
        "heatmap": result.to_dict(),
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
    )
  return success_response(
    "Educational attention heatmap generated.",
    {
      "xray": row.to_dict(include_explanation=True),
      "heatmap": result.to_dict(),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def download_heatmap(xray_id: int):
  """
  GET /api/xray/<id>/heatmap — serve heatmap PNG (owner only).

  Query:
    variant=heatmap (default) | overlay
  """
  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)

  variant = (request.args.get("variant") or "heatmap").lower()
  path = row.heatmap_path
  if variant == "overlay" and path:
    candidate = path.replace("_heatmap.png", "_overlay.png")
    if os.path.isfile(candidate):
      path = candidate

  if not path or not os.path.isfile(path):
    return error_response(
      "Heatmap not found. Run analysis or POST /api/xray/<id>/heatmap first.",
      404,
    )

  return send_file(
    path,
    mimetype="image/png",
    as_attachment=False,
    download_name=f"xray_{xray_id}_{variant}.png",
  )


def download_reference_for_xray(xray_id: int):
  """GET /api/xray/<id>/reference — serve the stored healthy reference for this analysis."""
  from app.services.xray.reference_library import ReferenceLibraryService

  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)
  if not row.reference_image_path:
    return error_response(
      "No reference image linked yet. POST /api/xray/<id>/compare first.",
      404,
    )

  path = ReferenceLibraryService.resolve_file(row.reference_image_path)
  if not path:
    return error_response("Stored reference image file is missing.", 404)

  ext = os.path.splitext(path)[1].lower()
  mime = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
  }.get(ext, "application/octet-stream")

  return send_file(
    path,
    mimetype=mime,
    as_attachment=False,
    download_name=os.path.basename(path),
  )


def get_comparison(xray_id: int):
  """GET /api/xray/<id>/compare — return stored educational healthy comparison."""
  from app.services.xray.comparison_service import XrayComparisonService

  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)

  stored = XrayComparisonService.get_stored_comparison(row)
  if not stored:
    return error_response(
      "No comparison yet. POST /api/xray/<id>/compare to generate one.",
      404,
      {"has_comparison": False, "disclaimer": XRAY_MEDICAL_DISCLAIMER},
    )
  return success_response(
    "Educational comparison retrieved.",
    {
      "xray_id": row.id,
      "comparison": stored.to_dict(),
      "xray": row.to_dict(include_explanation=True),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def generate_comparison(xray_id: int):
  """POST /api/xray/<id>/compare — select healthy reference + generate educational comparison."""
  from app.services.xray.comparison_service import XrayComparisonService

  force = request.args.get("force")
  if force is None and request.is_json:
    force = (request.get_json(silent=True) or {}).get("force")
  force_reselect = str(force or "").lower() in ("1", "true", "yes")

  row, result = XrayComparisonService.compare_for_user(
    xray_id,
    current_user.id,
    persist=True,
    force_reselect=force_reselect,
  )
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Could not generate educational comparison.",
      422,
      {"comparison": result.to_dict(), "disclaimer": XRAY_MEDICAL_DISCLAIMER},
    )
  return success_response(
    "Educational healthy comparison generated.",
    {
      "xray_id": row.id,
      "comparison": result.to_dict(),
      "xray": row.to_dict(include_explanation=True),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def get_recommendations(xray_id: int):
  """GET /api/xray/<id>/recommendations — return stored or freshly built learning recs."""
  from app.services.xray.recommendation_service import XrayRecommendationService

  force = (request.args.get("refresh") or "").lower() in ("1", "true", "yes")
  row = XrayUploadService.get_for_user(xray_id, current_user.id)
  if not row:
    return error_response("X-ray analysis not found.", 404)

  if row.learning_recommendations and not force:
    return success_response(
      "Learning recommendations retrieved.",
      {
        "xray_id": row.id,
        "recommendations": row.learning_recommendations,
        "xray": row.to_dict(include_explanation=True),
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
    )

  row, result = XrayRecommendationService.recommend_for_user(
    xray_id,
    current_user.id,
    persist=True,
    sync_user_recommendations=True,
  )
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Could not build recommendations.",
      422,
      {"recommendations": result.to_dict(), "disclaimer": XRAY_MEDICAL_DISCLAIMER},
    )
  return success_response(
    "Learning recommendations generated.",
    {
      "xray_id": row.id,
      "recommendations": result.recommendations,
      "topics": result.topics,
      "meta": result.to_dict(),
      "xray": row.to_dict(include_explanation=True),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )


def refresh_recommendations(xray_id: int):
  """POST /api/xray/<id>/recommendations — rebuild and persist learning recommendations."""
  from app.services.xray.recommendation_service import XrayRecommendationService

  row, result = XrayRecommendationService.recommend_for_user(
    xray_id,
    current_user.id,
    persist=True,
    sync_user_recommendations=True,
  )
  if result.error_code == "not_found" or row is None:
    return error_response("X-ray analysis not found.", 404)
  if not result.success:
    return error_response(
      result.message or "Could not build recommendations.",
      422,
      {"recommendations": result.to_dict(), "disclaimer": XRAY_MEDICAL_DISCLAIMER},
    )

  try:
    from app.services.body_systems.hub_xray_recommendation_service import (
      HubXrayRecommendationService,
    )

    HubXrayRecommendationService.recommend_for_analysis(row, user_id=current_user.id)
  except Exception:
    pass

  return success_response(
    "Learning recommendations refreshed.",
    {
      "xray_id": row.id,
      "recommendations": result.recommendations,
      "topics": result.topics,
      "meta": result.to_dict(),
      "xray": row.to_dict(include_explanation=True),
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    },
  )
