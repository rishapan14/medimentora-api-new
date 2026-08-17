"""Admin platform Settings management (Module 11)."""

from __future__ import annotations

import logging
import os
from typing import Any

from flask import current_app
from flask_jwt_extended import current_user

from app.extensions import db
from app.models.platform_setting_model import PlatformSetting
from app.utils import utc_now

logger = logging.getLogger(__name__)

# Editable Admin Panel preferences (stored in MySQL).
DEFAULT_SETTINGS: dict[str, Any] = {
  "platform_name": "MediMentora",
  "support_email": "support@medimentora.local",
  "maintenance_mode": False,
  "allow_registrations": True,
  "ai_report_analysis_enabled": True,
  "ai_xray_analysis_enabled": True,
  "default_quiz_time_limit_minutes": 30,
  "default_quiz_passing_score": 70,
  "educational_disclaimer": (
    "MediMentora provides educational and decision-support tools only. "
    "Outputs are not medical diagnoses and must not replace clinical judgment."
  ),
}

ALLOWED_KEYS = set(DEFAULT_SETTINGS.keys())

BOOL_KEYS = {
  "maintenance_mode",
  "allow_registrations",
  "ai_report_analysis_enabled",
  "ai_xray_analysis_enabled",
}

INT_KEYS = {
  "default_quiz_time_limit_minutes",
  "default_quiz_passing_score",
}


class AdminSettingsService:
  """Get / update Admin Panel platform settings."""

  @classmethod
  def get_settings(cls) -> dict[str, Any]:
    stored = {row.key: row.value for row in PlatformSetting.query.all()}
    settings = dict(DEFAULT_SETTINGS)
    for key in ALLOWED_KEYS:
      if key in stored:
        settings[key] = stored[key]

    meta_rows = {
      row.key: {
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "updated_by": row.updated_by,
      }
      for row in PlatformSetting.query.filter(PlatformSetting.key.in_(list(ALLOWED_KEYS))).all()
    }

    return {
      "settings": settings,
      "defaults": dict(DEFAULT_SETTINGS),
      "meta": meta_rows,
      "system": cls.system_info(),
    }

  @classmethod
  def system_info(cls) -> dict[str, Any]:
    cfg = current_app.config
    return {
      "flask_debug": bool(cfg.get("FLASK_DEBUG")),
      "openai_configured": bool(cfg.get("OPENAI_API_KEY")),
      "gemini_configured": bool(cfg.get("GEMINI_API_KEY")),
      "openai_model": cfg.get("OPENAI_MODEL"),
      "gemini_model": cfg.get("GEMINI_MODEL"),
      "ocr_engine": os.getenv("OCR_ENGINE", "auto"),
      "xray_vision_model": cfg.get("XRAY_VISION_MODEL"),
      "db_name": cfg.get("MYSQL_DATABASE"),
    }

  @classmethod
  def get_value(cls, key: str, default: Any = None) -> Any:
    """Return one setting value (DB override or default)."""
    if key not in ALLOWED_KEYS:
      return default if default is not None else DEFAULT_SETTINGS.get(key)
    row = db.session.get(PlatformSetting, key)
    if row is not None and row.value is not None:
      return row.value
    if default is not None:
      return default
    return DEFAULT_SETTINGS.get(key)

  @classmethod
  def get_bool(cls, key: str, default: bool = False) -> bool:
    value = cls.get_value(key, default)
    if isinstance(value, bool):
      return value
    if isinstance(value, str):
      return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)

  @classmethod
  def get_int(cls, key: str, default: int = 0) -> int:
    value = cls.get_value(key, default)
    try:
      return int(value)
    except (TypeError, ValueError):
      return int(default)

  @classmethod
  def public_status(cls) -> dict[str, Any]:
    """Unauthenticated-safe status for frontend gating / banners."""
    settings = cls.get_settings()["settings"]
    return {
      "platform_name": settings.get("platform_name") or DEFAULT_SETTINGS["platform_name"],
      "support_email": settings.get("support_email") or DEFAULT_SETTINGS["support_email"],
      "maintenance_mode": bool(settings.get("maintenance_mode")),
      "allow_registrations": bool(settings.get("allow_registrations")),
      "ai_report_analysis_enabled": bool(settings.get("ai_report_analysis_enabled")),
      "ai_xray_analysis_enabled": bool(settings.get("ai_xray_analysis_enabled")),
      "educational_disclaimer": settings.get("educational_disclaimer")
      or DEFAULT_SETTINGS["educational_disclaimer"],
    }

  @classmethod
  def deny_if_registrations_closed(cls):
    """Return an error response if registrations are disabled, else None."""
    from app.helpers.response import error_response

    if not cls.get_bool("allow_registrations", True):
      return error_response(
        "New registrations are currently disabled by the administrator.",
        403,
        {"error_code": "registrations_closed"},
      )
    if cls.get_bool("maintenance_mode", False):
      return error_response(
        "MediMentora is in maintenance mode. Registration is temporarily unavailable.",
        503,
        {"error_code": "maintenance_mode"},
      )
    return None

  @classmethod
  def deny_if_maintenance(cls, *, allow_admin: bool = True):
    """Block non-admin requests while maintenance mode is on."""
    from flask_jwt_extended import current_user

    from app.constants import is_admin_role
    from app.helpers.response import error_response

    if not cls.get_bool("maintenance_mode", False):
      return None
    if allow_admin and current_user is not None and is_admin_role(
      getattr(current_user, "role", None)
    ):
      return None
    return error_response(
      "MediMentora is temporarily in maintenance mode. Please try again later.",
      503,
      {"error_code": "maintenance_mode"},
    )

  @classmethod
  def deny_if_feature_disabled(cls, key: str, *, message: str):
    """Block when a boolean feature flag is off (admins still allowed)."""
    from flask_jwt_extended import current_user

    from app.constants import is_admin_role
    from app.helpers.response import error_response

    if cls.get_bool(key, True):
      return None
    if current_user is not None and is_admin_role(getattr(current_user, "role", None)):
      return None
    return error_response(
      message,
      403,
      {"error_code": "feature_disabled", "feature": key},
    )

  @classmethod
  def _coerce(cls, key: str, value: Any) -> Any:
    if key in BOOL_KEYS:
      if isinstance(value, bool):
        return value
      if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
      return bool(value)

    if key in INT_KEYS:
      try:
        number = int(value)
      except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer.") from exc
      if key == "default_quiz_time_limit_minutes" and not (1 <= number <= 300):
        raise ValueError("default_quiz_time_limit_minutes must be between 1 and 300.")
      if key == "default_quiz_passing_score" and not (0 <= number <= 100):
        raise ValueError("default_quiz_passing_score must be between 0 and 100.")
      return number

    if value is None:
      return ""
    text = str(value).strip()
    if key in ("platform_name", "support_email") and not text:
      raise ValueError(f"{key} cannot be empty.")
    if key == "support_email" and "@" not in text:
      raise ValueError("support_email must be a valid email address.")
    if key == "educational_disclaimer" and len(text) > 2000:
      raise ValueError("educational_disclaimer is too long (max 2000 characters).")
    if key == "platform_name" and len(text) > 120:
      raise ValueError("platform_name is too long (max 120 characters).")
    return text

  @classmethod
  def update_settings(cls, payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload or not isinstance(payload, dict):
      return {
        "success": False,
        "message": "Request body is required.",
        "error_code": "validation_error",
        "data": {"errors": ["Request body is required."]},
      }

    # Accept either flat settings or { settings: {...} }
    incoming = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    unknown = [k for k in incoming.keys() if k not in ALLOWED_KEYS]
    if unknown:
      return {
        "success": False,
        "message": f"Unknown setting keys: {', '.join(sorted(unknown))}.",
        "error_code": "validation_error",
        "data": {"errors": [f"Unknown keys: {', '.join(sorted(unknown))}"]},
      }

    if not incoming:
      return {
        "success": False,
        "message": "No settings provided.",
        "error_code": "validation_error",
        "data": {"errors": ["No settings provided."]},
      }

    coerced: dict[str, Any] = {}
    errors: list[str] = []
    for key, value in incoming.items():
      try:
        coerced[key] = cls._coerce(key, value)
      except ValueError as exc:
        errors.append(str(exc))
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    actor_id = getattr(current_user, "id", None)
    try:
      for key, value in coerced.items():
        row = db.session.get(PlatformSetting, key)
        if row is None:
          row = PlatformSetting(key=key, value=value)
          db.session.add(row)
        else:
          row.value = value
        row.updated_at = utc_now()
        row.updated_by = actor_id
      db.session.commit()
      logger.info("Admin updated platform settings keys=%s by=%s", list(coerced.keys()), actor_id)
      return {
        "success": True,
        "message": "Settings saved.",
        "data": cls.get_settings(),
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update settings failed")
      return {
        "success": False,
        "message": "Could not save settings.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def reset_defaults(cls) -> dict[str, Any]:
    """Reset all editable settings to defaults."""
    return cls.update_settings(dict(DEFAULT_SETTINGS))
