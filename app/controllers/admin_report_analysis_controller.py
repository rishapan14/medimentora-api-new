"""Admin APIs for AI Report Analysis monitoring (Module 5)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.report_analysis_admin_service import AdminReportAnalysisService


def admin_list_report_analyses():
  """GET /api/admin/report-analyses"""
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

  payload = AdminReportAnalysisService.list_analyses(
    q=request.args.get("q") or request.args.get("search"),
    report_type=request.args.get("report_type"),
    analysis_mode=request.args.get("analysis_mode") or request.args.get("mode"),
    user_id=user_id,
    limit=limit,
    offset=offset,
  )
  return success_response("Report analyses retrieved.", payload)


def admin_get_report_analysis(analysis_id: int):
  """GET /api/admin/report-analyses/<id>"""
  payload = AdminReportAnalysisService.get_analysis_payload(analysis_id)
  if not payload:
    return error_response("Analysis not found.", 404)
  return success_response("Analysis retrieved.", {"analysis": payload})


def admin_delete_report_analysis(analysis_id: int):
  """DELETE /api/admin/report-analyses/<id>"""
  result = AdminReportAnalysisService.delete_analysis(analysis_id)
  if not result.get("success"):
    code = result.get("error_code")
    status = 404 if code == "not_found" else 422
    return error_response(result.get("message") or "Delete failed.", status, result)
  return success_response(result["message"])
