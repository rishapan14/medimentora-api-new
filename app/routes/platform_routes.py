"""Public platform status (no auth) — used by client for feature banners."""

from flask import Blueprint

from app.helpers.response import success_response
from app.services.admin.settings_admin_service import AdminSettingsService

platform_bp = Blueprint("platform", __name__, url_prefix="/api/platform")


def platform_status():
  """GET /api/platform/status"""
  return success_response("Platform status retrieved.", AdminSettingsService.public_status())


platform_bp.add_url_rule("/status", view_func=platform_status, methods=["GET"])
