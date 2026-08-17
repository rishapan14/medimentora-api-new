"""Authentication business logic."""

import secrets
from datetime import timedelta

from flask import current_app
from flask_jwt_extended import create_access_token, create_refresh_token

from app.constants import ROLE_MEDICAL_STUDENT, VALID_ROLES
from app.extensions import db
from app.models.user_model import User
from app.utils import utc_now


class AuthService:
  @staticmethod
  def register_user(email, password, full_name=None, role=None):
    if role and role not in VALID_ROLES:
      raise ValueError(f"Invalid role. Must be one of: {', '.join(VALID_ROLES)}")

    user = User(
      email=email.strip().lower(),
      full_name=(full_name or "").strip() or None,
      role=role or ROLE_MEDICAL_STUDENT,
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user

  @staticmethod
  def authenticate(email, password):
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user or not user.check_password(password):
      return None
    if not user.is_active:
      raise PermissionError("Account is deactivated.")
    return user

  @staticmethod
  def create_tokens(user):
    identity = str(user.id)
    return {
      "access_token": create_access_token(identity=identity),
      "refresh_token": create_refresh_token(identity=identity),
    }

  @staticmethod
  def request_password_reset(email):
    user = User.query.filter_by(email=email.strip().lower()).first()
    if not user:
      return None

    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_token_expires = utc_now() + timedelta(
      hours=current_app.config["RESET_TOKEN_EXPIRE_HOURS"]
    )
    db.session.commit()

    reset_link = f"{current_app.config['FRONTEND_URL']}/auth/reset-password?token={token}"
    return {"user": user, "reset_token": token, "reset_link": reset_link}

  @staticmethod
  def reset_password(token, new_password):
    user = User.query.filter_by(reset_token=token).first()
    if not user:
      raise ValueError("Invalid or expired reset token.")
    if user.reset_token_expires and user.reset_token_expires < utc_now():
      raise ValueError("Reset token has expired.")

    user.set_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    db.session.commit()
    return user

  @staticmethod
  def update_profile(user, data):
    if "full_name" in data:
      user.full_name = data["full_name"]
    if "role" in data and data["role"] in VALID_ROLES:
      user.role = data["role"]
    if "speciality" in data:
      user.speciality = data["speciality"]
    if "bio" in data:
      user.bio = data["bio"]
    if "email" in data and data["email"]:
      email = data["email"].strip().lower()
      existing = User.query.filter(User.email == email, User.id != user.id).first()
      if existing:
        raise ValueError("Email already in use.")
      user.email = email
    db.session.commit()
    return user
