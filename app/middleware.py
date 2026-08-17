from functools import wraps

from flask_jwt_extended import current_user, verify_jwt_in_request

from app.constants import ADMIN_PANEL_ROLES, is_admin_role
from app.helpers.response import error_response


def roles_required(*roles):
    """Decorator to restrict route access to specific user roles (JWT required)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            if not current_user:
                return error_response("User not found.", 404)
            if getattr(current_user, "is_active", True) is False:
                return error_response("Account is deactivated.", 403)
            if current_user.role not in roles:
                return error_response("Access forbidden: insufficient permissions.", 403)
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def admin_required(fn):
    """JWT + Admin role required (Admin Panel /admin APIs)."""
    return roles_required(*ADMIN_PANEL_ROLES)(fn)


def require_admin_user():
    """Raise-style helper for controllers that already verified JWT."""
    if not current_user:
        return error_response("User not found.", 404)
    if not is_admin_role(getattr(current_user, "role", None)):
        return error_response("Access forbidden: admin role required.", 403)
    return None
