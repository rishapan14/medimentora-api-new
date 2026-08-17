"""Run database schema setup once, before starting application workers."""

from sqlalchemy import inspect, text

from app import create_app
from app.db_bootstrap import ensure_database
from app.extensions import db


LOCK_NAME = "medimentora_schema_bootstrap"
LOCK_TIMEOUT_SECONDS = 120


def bootstrap_schema(app=None) -> None:
  """Create and patch the schema while holding a cross-process MySQL lock."""
  print("[schema] Starting database schema bootstrap", flush=True)
  ensure_database()
  app = app or create_app()

  with app.app_context():
    with db.engine.connect() as connection:
      acquired = connection.execute(
        text("SELECT GET_LOCK(:name, :timeout)"),
        {"name": LOCK_NAME, "timeout": LOCK_TIMEOUT_SECONDS},
      ).scalar()
      if acquired != 1:
        raise RuntimeError("Timed out waiting for the database schema lock")

      try:
        print("[schema] Creating SQLAlchemy model tables", flush=True)
        db.create_all()
        print("[schema] Core model tables created", flush=True)

        from app.helpers.schema_patches import (
          ensure_body_systems_hub_schema,
          ensure_learning_schema,
          ensure_medical_teacher_schema,
          ensure_platform_settings_schema,
          ensure_report_history_schema,
          ensure_user_previous_role_schema,
          ensure_xray_analysis_schema,
          ensure_xray_reference_library_schema,
        )

        patches = (
          ("report history", ensure_report_history_schema),
          ("xray analysis", ensure_xray_analysis_schema),
          ("xray reference library", ensure_xray_reference_library_schema),
          ("learning", ensure_learning_schema),
          ("body systems hub", ensure_body_systems_hub_schema),
          ("medical teacher", ensure_medical_teacher_schema),
          ("platform settings", ensure_platform_settings_schema),
          ("user previous role", ensure_user_previous_role_schema),
        )
        for label, patch in patches:
          print(f"[schema] Applying {label} schema", flush=True)
          patch()

        print("[schema] Ensuring starter quiz and simulation content", flush=True)
        from app.seeders.default_feature_seeder import ensure_default_feature_content

        created_content = ensure_default_feature_content()
        if created_content:
          print(
            f"[schema] Created starter content: {', '.join(created_content)}",
            flush=True,
          )

        table_names = inspect(db.engine).get_table_names()
        if not table_names:
          raise RuntimeError(
            f"Schema bootstrap created zero tables in database '{app.config['MYSQL_DATABASE']}'"
          )
        print(
          f"[schema] Database '{app.config['MYSQL_DATABASE']}' contains "
          f"{len(table_names)} tables: {', '.join(sorted(table_names))}",
          flush=True,
        )
        print("[schema] Database schema bootstrap completed", flush=True)
      finally:
        connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": LOCK_NAME})


if __name__ == "__main__":
  bootstrap_schema()
