"""Admin user management service (Module 4).

Binary Admin Panel roles:
- Admin → role = \"admin\"
- User  → role = \"user\" (non-admin)

Existing clinical roles (doctor/nurse/medical_student) are treated as User
for panel access until an admin promotes them.
"""

from __future__ import annotations

import logging
from typing import Any

from app.constants import ROLE_ADMIN, ROLE_MEDICAL_STUDENT, ROLE_USER, is_admin_role
from app.extensions import db
from app.models.user_model import User
from app.utils import utc_now

logger = logging.getLogger(__name__)


class AdminUserService:
  """CRUD helpers for Admin Panel user management."""

  @classmethod
  def list_users(
    cls,
    *,
    q: str | None = None,
    panel_role: str | None = None,
    is_active: bool | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = User.query

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        db.or_(
          User.email.ilike(like),
          User.full_name.ilike(like),
          User.speciality.ilike(like),
        )
      )

    role_filter = (panel_role or "").strip().lower()
    if role_filter in ("admin", "admins"):
      query = query.filter(User.role == ROLE_ADMIN)
    elif role_filter in ("user", "users"):
      query = query.filter(User.role != ROLE_ADMIN)

    if is_active is not None:
      query = query.filter(User.is_active == bool(is_active))

    total = query.count()
    rows = (
      query.order_by(User.created_at.desc(), User.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 200))
      .all()
    )

    admin_count = User.query.filter(User.role == ROLE_ADMIN).count()
    active_count = User.query.filter_by(is_active=True).count()
    all_count = User.query.count()

    return {
      "users": [u.to_dict() for u in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "stats": {
        "total": all_count,
        "admins": admin_count,
        "users": max(0, all_count - admin_count),
        "active": active_count,
        "inactive": max(0, all_count - active_count),
      },
    }

  @classmethod
  def get_user(cls, user_id: int) -> User | None:
    return db.session.get(User, user_id)

  @classmethod
  def set_panel_role(
    cls,
    user_id: int,
    panel_role: str,
    *,
    actor_id: int | None,
  ) -> dict[str, Any]:
    """Set Admin Panel role to Admin or User."""
    raw = (panel_role or "").strip().lower()
    if raw in ("admin", "admins"):
      next_role = ROLE_ADMIN
    elif raw in ("user", "users"):
      next_role = ROLE_USER
    else:
      return {
        "success": False,
        "message": "Invalid role. Allowed: Admin, User.",
        "error_code": "validation_error",
      }

    user = cls.get_user(user_id)
    if not user:
      return {"success": False, "message": "User not found.", "error_code": "not_found"}

    if actor_id is not None and user.id == actor_id and next_role != ROLE_ADMIN:
      return {
        "success": False,
        "message": "You cannot remove your own Admin role.",
        "error_code": "forbidden_self",
      }

    # Prevent demoting the last remaining admin
    if is_admin_role(user.role) and next_role != ROLE_ADMIN:
      admin_count = User.query.filter(User.role == ROLE_ADMIN).count()
      if admin_count <= 1:
        return {
          "success": False,
          "message": "Cannot demote the last Admin account.",
          "error_code": "last_admin",
        }

    try:
      if next_role == ROLE_ADMIN:
        # Preserve clinical/system role so demotion can restore it
        if not is_admin_role(user.role):
          user.previous_role = user.role
        user.role = ROLE_ADMIN
      else:
        # Demote: restore previous clinical role when available
        restored = (user.previous_role or "").strip().lower()
        if restored and restored != ROLE_ADMIN:
          user.role = restored
        else:
          user.role = ROLE_MEDICAL_STUDENT
        user.previous_role = None
      user.updated_at = utc_now()
      db.session.commit()
      logger.info("Admin set user id=%s role=%s by actor=%s", user_id, user.role, actor_id)
      return {
        "success": True,
        "message": f"User role updated to {'Admin' if next_role == ROLE_ADMIN else 'User'}.",
        "data": {"user": user.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("set_panel_role failed id=%s", user_id)
      return {
        "success": False,
        "message": "Could not update user role.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def set_active(
    cls,
    user_id: int,
    *,
    active: bool,
    actor_id: int | None,
  ) -> dict[str, Any]:
    user = cls.get_user(user_id)
    if not user:
      return {"success": False, "message": "User not found.", "error_code": "not_found"}

    if actor_id is not None and user.id == actor_id and not active:
      return {
        "success": False,
        "message": "You cannot deactivate your own account.",
        "error_code": "forbidden_self",
      }

    if is_admin_role(user.role) and not active:
      admin_count = User.query.filter(User.role == ROLE_ADMIN, User.is_active.is_(True)).count()
      if admin_count <= 1:
        return {
          "success": False,
          "message": "Cannot deactivate the last active Admin account.",
          "error_code": "last_admin",
        }

    try:
      user.is_active = bool(active)
      user.updated_at = utc_now()
      db.session.commit()
      state = "activated" if active else "deactivated"
      return {
        "success": True,
        "message": f"User {state}.",
        "data": {"user": user.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("set_active failed id=%s", user_id)
      return {
        "success": False,
        "message": "Could not update account status.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }
