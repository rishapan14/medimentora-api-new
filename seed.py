"""Create the initial administrator account."""

import os

from app import create_app
from app.constants import ROLE_ADMIN
from app.db_bootstrap import ensure_database
from app.extensions import db
from app.models.user_model import User


def seed_admin() -> None:
  email = os.getenv("ADMIN_EMAIL", "admin@clinical.com").strip().lower()
  password = os.getenv("ADMIN_PASSWORD", "admin123")
  full_name = os.getenv("ADMIN_FULL_NAME", "System Admin").strip()

  if not email or not password:
    raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must not be empty")

  existing = User.query.filter_by(email=email).first()
  if existing:
    print(f"Admin account already exists: {email}")
    return

  admin = User(
    email=email,
    full_name=full_name or "System Admin",
    role=ROLE_ADMIN,
    is_active=True,
  )
  admin.set_password(password)
  db.session.add(admin)
  db.session.commit()
  print(f"Admin account created: {email}")


if __name__ == "__main__":
  ensure_database()
  app = create_app()
  with app.app_context():
    db.create_all()
    seed_admin()
