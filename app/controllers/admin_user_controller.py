"""Admin APIs for user management (Module 4)."""

from __future__ import annotations

from flask import request
from flask_jwt_extended import current_user

from app.helpers.response import error_response, success_response
from app.services.admin.user_admin_service import AdminUserService


def _parse_bool(raw, default=None):
  if raw is None:
    return default
  return str(raw).lower() in ("1", "true", "yes", "active")


def admin_list_users():
  """GET /api/admin/users"""
  try:
    limit = int(request.args.get("limit") or 50)
  except (TypeError, ValueError):
    limit = 50
  try:
    offset = int(request.args.get("offset") or 0)
  except (TypeError, ValueError):
    offset = 0

  is_active_param = request.args.get("is_active")
  is_active = _parse_bool(is_active_param) if is_active_param is not None else None

  payload = AdminUserService.list_users(
    q=request.args.get("q") or request.args.get("search"),
    panel_role=request.args.get("role") or request.args.get("panel_role"),
    is_active=is_active,
    limit=limit,
    offset=offset,
  )
  return success_response("Users retrieved.", payload)


def admin_get_user(user_id: int):
  """GET /api/admin/users/<id>"""
  user = AdminUserService.get_user(user_id)
  if not user:
    return error_response("User not found.", 404)
  return success_response("User retrieved.", {"user": user.to_dict()})


def admin_update_user_role(user_id: int):
  """PATCH /api/admin/users/<id>/role  body: { role: \"admin\" | \"user\" }"""
  body = request.get_json(silent=True) or {}
  role = body.get("role") or body.get("panel_role")
  result = AdminUserService.set_panel_role(
    user_id,
    str(role or ""),
    actor_id=getattr(current_user, "id", None),
  )
  if not result.get("success"):
    code = result.get("error_code")
    status = (
      404
      if code == "not_found"
      else 403
      if code in ("forbidden_self", "last_admin")
      else 400
      if code == "validation_error"
      else 422
    )
    return error_response(result.get("message") or "Update failed.", status, result)
  return success_response(result["message"], result.get("data") or {})


def admin_set_user_active(user_id: int):
  """POST /api/admin/users/<id>/activate|deactivate via body { is_active: bool }"""
  body = request.get_json(silent=True) or {}
  if "is_active" not in body and "active" not in body:
    return error_response("is_active is required.", 400)
  active = bool(body.get("is_active") if "is_active" in body else body.get("active"))
  result = AdminUserService.set_active(
    user_id,
    active=active,
    actor_id=getattr(current_user, "id", None),
  )
  if not result.get("success"):
    code = result.get("error_code")
    status = (
      404
      if code == "not_found"
      else 403
      if code in ("forbidden_self", "last_admin")
      else 422
    )
    return error_response(result.get("message") or "Update failed.", status, result)
  return success_response(result["message"], result.get("data") or {})
