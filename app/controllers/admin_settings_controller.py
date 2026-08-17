"""Admin APIs for platform Settings (Module 11)."""

from __future__ import annotations

from flask import request

from app.helpers.response import error_response, success_response
from app.services.admin.settings_admin_service import AdminSettingsService


def _status_for(code: str | None) -> int:
  if code == "validation_error":
    return 400
  return 422


def admin_get_settings():
  """GET /api/admin/settings"""
  payload = AdminSettingsService.get_settings()
  return success_response("Settings retrieved.", payload)


def admin_update_settings():
  """PUT/PATCH /api/admin/settings"""
  result = AdminSettingsService.update_settings(request.get_json(silent=True))
  if not result.get("success"):
    return error_response(
      result.get("message") or "Update failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})


def admin_reset_settings():
  """POST /api/admin/settings/reset"""
  result = AdminSettingsService.reset_defaults()
  if not result.get("success"):
    return error_response(
      result.get("message") or "Reset failed.",
      _status_for(result.get("error_code")),
      result.get("data"),
    )
  return success_response(result["message"], result.get("data") or {})
