import re

from app.constants import VALID_ROLES

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")


def validate_register(data):
  from app.models.user_model import User

  errors = []
  if not data:
    return ["Request body is required."]

  email = str(data.get("email", "")).strip().lower()
  if not email:
    errors.append("email is required.")
  elif not EMAIL_REGEX.match(email):
    errors.append("Invalid email format.")
  elif User.query.filter_by(email=email).first():
    errors.append("Email address already exists.")

  password = data.get("password")
  if not password or str(password).strip() == "":
    errors.append("password is required.")
  elif len(str(password)) < 6:
    errors.append("password must be at least 6 characters.")

  full_name = str(data.get("full_name", "")).strip()
  if not full_name:
    errors.append("full_name is required.")
  elif len(full_name) < 2:
    errors.append("full_name must be at least 2 characters.")

  role = data.get("role")
  if role and role not in VALID_ROLES:
    errors.append(f"role must be one of: {', '.join(VALID_ROLES)}.")

  return errors


def validate_login(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("email"):
    errors.append("email is required.")
  if not data.get("password"):
    errors.append("password is required.")
  return errors


def validate_forgot_password(data):
  errors = []
  if not data or not data.get("email"):
    errors.append("email is required.")
  return errors


def validate_reset_password(data):
  errors = []
  if not data:
    return ["Request body is required."]
  if not data.get("token"):
    errors.append("token is required.")
  if not data.get("password"):
    errors.append("password is required.")
  elif len(str(data.get("password"))) < 6:
    errors.append("password must be at least 6 characters.")
  return errors
