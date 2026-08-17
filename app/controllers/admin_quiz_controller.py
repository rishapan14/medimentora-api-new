"""Admin APIs for Quiz Management (Module 8)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.quiz_admin_service import AdminQuizService


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


def admin_list_quizzes():
  """GET /api/admin/quizzes"""
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
  if published_param is not None and str(published_param).lower() in ("0", "false", "no", "draft"):
    published = False

  payload = AdminQuizService.list_quizzes(
    q=request.args.get("q") or request.args.get("search"),
    difficulty=request.args.get("difficulty"),
    speciality=request.args.get("speciality"),
    published=published,
    limit=limit,
    offset=offset,
  )
  return success_response("Quizzes retrieved.", payload)


def admin_get_quiz(quiz_id: int):
  """GET /api/admin/quizzes/<id>"""
  quiz = AdminQuizService.get_quiz(quiz_id)
  if not quiz:
    return error_response("Quiz not found.", 404)
  return success_response("Quiz retrieved.", {"quiz": quiz})


def admin_create_quiz():
  """POST /api/admin/quizzes"""
  result = AdminQuizService.create_quiz(request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Create failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {}, 201)


def admin_update_quiz(quiz_id: int):
  """PUT/PATCH /api/admin/quizzes/<id>"""
  result = AdminQuizService.update_quiz(quiz_id, request.get_json(silent=True) or {})
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_set_quiz_published(quiz_id: int):
  """POST /api/admin/quizzes/<id>/publish"""
  body = request.get_json(silent=True) or {}
  if "is_published" not in body and "published" not in body:
    return error_response("is_published is required.", 400)
  published = bool(body.get("is_published") if "is_published" in body else body.get("published"))
  result = AdminQuizService.set_published(quiz_id, published=published)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_delete_quiz(quiz_id: int):
  """DELETE /api/admin/quizzes/<id>"""
  result = AdminQuizService.delete_quiz(quiz_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Delete failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"])


def admin_list_questions(quiz_id: int):
  """GET /api/admin/quizzes/<id>/questions"""
  result = AdminQuizService.list_questions(quiz_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Not found.",
      _status_for(result.get("error_code")),
    )
  return success_response("Questions retrieved.", result.get("data") or {})


def admin_create_question(quiz_id: int):
  """POST /api/admin/quizzes/<id>/questions"""
  result = AdminQuizService.create_question(quiz_id, request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Create failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {}, 201)


def admin_update_question(question_id: int):
  """PUT/PATCH /api/admin/quizzes/questions/<id>"""
  result = AdminQuizService.update_question(question_id, request.get_json(silent=True) or {})
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_delete_question(question_id: int):
  """DELETE /api/admin/quizzes/questions/<id>"""
  result = AdminQuizService.delete_question(question_id)
  if not result.get("success"):
    return error_response(
      result.get("message") or "Delete failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"])
