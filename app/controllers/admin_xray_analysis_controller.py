"""Admin APIs for AI X-Ray Analysis monitoring (Module 6 / Phase 16)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.xray_analysis_admin_service import AdminXrayAnalysisService


def _parse_bool_flag(raw: str | None) -> bool | None:
  if raw in (None, ""):
    return None
  value = str(raw).strip().lower()
  if value in ("1", "true", "yes", "y"):
    return True
  if value in ("0", "false", "no", "n"):
    return False
  return None


def admin_list_xray_analyses():
  """GET /api/admin/xray-analyses"""
  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  try:
    offset = int(request.args.get("offset") or 0)
  except (TypeError, ValueError):
    offset = 0

  user_id_raw = request.args.get("user_id")
  user_id = None
  if user_id_raw not in (None, ""):
    try:
      user_id = int(user_id_raw)
    except (TypeError, ValueError):
      return error_response("user_id must be an integer.", 400)

  has_heatmap = _parse_bool_flag(request.args.get("has_heatmap"))
  if request.args.get("has_heatmap") not in (None, "") and has_heatmap is None:
    return error_response("has_heatmap must be true/false.", 400)

  has_comparison = _parse_bool_flag(request.args.get("has_comparison"))
  if request.args.get("has_comparison") not in (None, "") and has_comparison is None:
    return error_response("has_comparison must be true/false.", 400)

  payload = AdminXrayAnalysisService.list_analyses(
    q=request.args.get("q") or request.args.get("search"),
    body_part=request.args.get("body_part"),
    status=request.args.get("status"),
    user_id=user_id,
    has_heatmap=has_heatmap,
    has_comparison=has_comparison,
    limit=limit,
    offset=offset,
  )
  return success_response("X-ray analyses retrieved.", payload)


def admin_get_xray_analysis(xray_id: int):
  """GET /api/admin/xray-analyses/<id>"""
  payload = AdminXrayAnalysisService.get_analysis_payload(xray_id)
  if not payload:
    return error_response("X-ray analysis not found.", 404)
  return success_response("X-ray analysis retrieved.", {"analysis": payload})


def admin_delete_xray_analysis(xray_id: int):
  """DELETE /api/admin/xray-analyses/<id>"""
  result = AdminXrayAnalysisService.delete_analysis(xray_id)
  if not result.get("success"):
    code = result.get("error_code")
    status = 404 if code == "not_found" else 422
    return error_response(result.get("message") or "Delete failed.", status, result)
  return success_response(result["message"])


def admin_xray_evaluation_metrics():
  """GET /api/admin/xray-analyses/evaluation-metrics — Phase 17 educational model metrics."""
  from app.services.xray.evaluation import XrayModelEvaluationService

  limit_raw = request.args.get("limit_rows") or request.args.get("limit")
  try:
    limit_rows = int(limit_raw) if limit_raw not in (None, "") else 2000
  except (TypeError, ValueError):
    return error_response("limit_rows must be an integer.", 400)

  report = XrayModelEvaluationService.build_report(
    body_part=request.args.get("body_part"),
    model_name=request.args.get("model_name"),
    analysis_version=request.args.get("analysis_version"),
    specialist_key=request.args.get("specialist_key"),
    status=request.args.get("status") or "completed",
    limit_rows=limit_rows,
  )
  return success_response(
    "Educational model-evaluation metrics retrieved.",
    {"evaluation": report},
  )
