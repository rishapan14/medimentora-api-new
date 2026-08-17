"""Admin APIs for Learning Content management (Module 7)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.learning_admin_service import AdminLearningService


def _status_for(code: str | None) -> int:
  if code == "not_found":
    return 404
  if code == "validation_error":
    return 400
  return 422


def _parse_bool(raw, default=None):
  if raw is None:
    return default
  return str(raw).lower() in ("1", "true", "yes", "published")


def admin_list_categories():
  """GET /api/admin/learning/categories"""
  include_inactive = _parse_bool(request.args.get("include_inactive"), True)
  payload = AdminLearningService.list_categories(include_inactive=bool(include_inactive))
  return success_response("Categories retrieved.", payload)


def admin_list_courses():
  """GET /api/admin/learning/courses"""
  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  try:
    offset = int(request.args.get("offset") or 0)
  except (TypeError, ValueError):
    offset = 0

  published_param = request.args.get("published") or request.args.get("is_published")
  published = _parse_bool(published_param) if published_param is not None else None
  # explicit draft filter
  if published_param is not None and str(published_param).lower() in ("0", "false", "no", "draft"):
    published = False

  category_raw = request.args.get("category_id")
  category_id = None
  if category_raw not in (None, ""):
    try:
      category_id = int(category_raw)
    except (TypeError, ValueError):
      return error_response("category_id must be an integer.", 400)

  payload = AdminLearningService.list_courses(
    q=request.args.get("q") or request.args.get("search"),
    difficulty=request.args.get("difficulty"),
    published=published,
    category_id=category_id,
    limit=limit,
    offset=offset,
  )
  return success_response("Courses retrieved.", payload)


def admin_get_course(course_id: int):
  """GET /api/admin/learning/courses/<id>"""
  course = AdminLearningService.get_course(course_id)
  if not course:
    return error_response("Course not found.", 404)
  return success_response("Course retrieved.", {"course": course})


def admin_create_course():
  """POST /api/admin/learning/courses"""
  result = AdminLearningService.create_course(request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Create failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {}, 201)


def admin_update_course(course_id: int):
  """PUT/PATCH /api/admin/learning/courses/<id>"""
  result = AdminLearningService.update_course(course_id, request.get_json(silent=True) or {})
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_set_course_published(course_id: int):
  """POST /api/admin/learning/courses/<id>/publish  body: { is_published: bool }"""
  body = request.get_json(silent=True) or {}
  if "is_published" not in body and "published" not in body:
    return error_response("is_published is required.", 400)
  published = bool(body.get("is_published") if "is_published" in body else body.get("published"))
  result = AdminLearningService.set_course_published(course_id, published=published)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_delete_course(course_id: int):
  """DELETE /api/admin/learning/courses/<id>"""
  result = AdminLearningService.delete_course(course_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Delete failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"])


def admin_list_lessons(course_id: int):
  """GET /api/admin/learning/courses/<id>/lessons"""
  result = AdminLearningService.list_lessons(course_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Not found.",
      _status_for(result.get("error_code")),
    )
  return success_response("Lessons retrieved.", result.get("data") or {})


def admin_create_lesson():
  """POST /api/admin/learning/lessons"""
  result = AdminLearningService.create_lesson(request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Create failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {}, 201)


def admin_update_lesson(lesson_id: int):
  """PUT/PATCH /api/admin/learning/lessons/<id>"""
  result = AdminLearningService.update_lesson(lesson_id, request.get_json(silent=True) or {})
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_delete_lesson(lesson_id: int):
  """DELETE /api/admin/learning/lessons/<id>"""
  result = AdminLearningService.delete_lesson(lesson_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Delete failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"])
