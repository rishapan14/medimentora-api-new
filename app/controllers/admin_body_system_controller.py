"""Admin controllers for Body Systems Learning Hub (Phase 2)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.body_systems.admin_service import AdminBodySystemService


def _status_for(code: str | None) -> int:
  if code == "not_found":
    return 404
  if code == "conflict":
    return 409
  if code == "validation_error":
    return 400
  return 422


def admin_list_body_systems():
  """GET /api/admin/learning/body-systems"""
  include_inactive = str(request.args.get("include_inactive") or "true").lower() in (
    "1",
    "true",
    "yes",
  )
  payload = AdminBodySystemService.list_systems(
    q=request.args.get("q") or request.args.get("search"),
    include_inactive=include_inactive,
  )
  return success_response("Body systems retrieved.", payload)


def admin_get_body_system(slug: str):
  """GET /api/admin/learning/body-systems/<slug>"""
  payload = AdminBodySystemService.get_system(slug)
  if not payload:
    return error_response("Body system not found.", 404)
  return success_response("Body system retrieved.", payload)


def admin_create_body_system():
  """POST /api/admin/learning/body-systems"""
  body = request.get_json(silent=True) or {}
  payload, code, message = AdminBodySystemService.create_system(body)
  if code:
    return error_response(message or "Could not create body system.", _status_for(code), {"error_code": code})
  return success_response("Body system created.", payload, 201)


def admin_update_body_system(slug: str):
  """PUT/PATCH /api/admin/learning/body-systems/<slug>"""
  body = request.get_json(silent=True) or {}
  payload, code, message = AdminBodySystemService.update_system(slug, body)
  if code:
    return error_response(message or "Could not update body system.", _status_for(code), {"error_code": code})
  return success_response("Body system updated.", payload)


def admin_delete_body_system(slug: str):
  """DELETE /api/admin/learning/body-systems/<slug> (soft delete)"""
  ok, code, message = AdminBodySystemService.delete_system(slug)
  if not ok:
    return error_response(message or "Could not delete body system.", _status_for(code), {"error_code": code})
  return success_response("Body system deactivated.", {"slug": slug})


def admin_create_organ(slug: str):
  """POST /api/admin/learning/body-systems/<slug>/organs"""
  body = request.get_json(silent=True) or {}
  payload, code, message = AdminBodySystemService.create_organ(slug, body)
  if code:
    return error_response(message or "Could not create organ.", _status_for(code), {"error_code": code})
  return success_response("Organ created.", payload, 201)


def admin_update_organ(organ_slug: str):
  """PUT/PATCH /api/admin/learning/organs/<organ_slug>"""
  body = request.get_json(silent=True) or {}
  system_slug = request.args.get("system") or body.get("system_slug")
  payload, code, message = AdminBodySystemService.update_organ(
    organ_slug, body, system_slug=system_slug
  )
  if code:
    return error_response(message or "Could not update organ.", _status_for(code), {"error_code": code})
  return success_response("Organ updated.", payload)


def admin_create_disease(slug: str):
  """POST /api/admin/learning/body-systems/<slug>/diseases"""
  body = request.get_json(silent=True) or {}
  payload, code, message = AdminBodySystemService.create_disease(slug, body)
  if code:
    return error_response(message or "Could not create disease.", _status_for(code), {"error_code": code})
  return success_response("Disease created.", payload, 201)


def admin_link_course(slug: str):
  """POST /api/admin/learning/body-systems/<slug>/courses"""
  body = request.get_json(silent=True) or {}
  course_id = body.get("course_id")
  if course_id is None:
    return error_response("course_id is required.", 400, {"error_code": "validation_error"})
  try:
    course_id = int(course_id)
  except (TypeError, ValueError):
    return error_response("course_id must be an integer.", 400, {"error_code": "validation_error"})
  payload, code, message = AdminBodySystemService.link_course(
    slug,
    course_id,
    role=(body.get("role") or "related"),
    sort_order=int(body.get("sort_order") or 0),
  )
  if code:
    return error_response(message or "Could not link course.", _status_for(code), {"error_code": code})
  return success_response("Course linked to body system.", payload)


def admin_link_quiz(slug: str):
  """POST /api/admin/learning/body-systems/<slug>/quizzes"""
  body = request.get_json(silent=True) or {}
  quiz_id = body.get("quiz_id")
  if quiz_id is None:
    return error_response("quiz_id is required.", 400, {"error_code": "validation_error"})
  try:
    quiz_id = int(quiz_id)
  except (TypeError, ValueError):
    return error_response("quiz_id must be an integer.", 400, {"error_code": "validation_error"})
  payload, code, message = AdminBodySystemService.link_quiz(
    slug,
    quiz_id,
    is_required=bool(body.get("is_required", False)),
    sort_order=int(body.get("sort_order") or 0),
  )
  if code:
    return error_response(message or "Could not link quiz.", _status_for(code), {"error_code": code})
  return success_response("Quiz linked to body system.", payload)
