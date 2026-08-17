"""Verify xray_analysis table exists with required Module 1 columns."""

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_xray_analysis_schema
from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER, XrayAnalysis
from app.utils import utc_now

REQUIRED = {
  "id",
  "user_id",
  "filename",
  "file_path",
  "body_part",
  "possible_findings",
  "confidence",
  "ai_summary",
  "heatmap_path",
  "model_name",
  "analysis_version",
  "status",
  "processing_time",
  "created_at",
  "updated_at",
}

app = create_app()
with app.app_context():
  ensure_xray_analysis_schema()
  # Re-run to apply optional column patches on existing tables
  ensure_xray_analysis_schema()

  tables = inspect(db.engine).get_table_names()
  assert "xray_analysis" in tables, "xray_analysis table missing"
  cols = {c["name"] for c in inspect(db.engine).get_columns("xray_analysis")}
  missing = sorted(REQUIRED - cols)
  print("=== xray_analysis columns ===")
  for name in sorted(cols):
    mark = "OK" if name in REQUIRED else "  "
    print(f"  [{mark}] {name}")
  print()
  if missing:
    print("MISSING:", missing)
    raise SystemExit(1)

  from app.models.user_model import User

  user = User.query.first()
  if not user:
    print("No user found — skipping insert smoke test.")
  else:
    row = XrayAnalysis(
      user_id=user.id,
      filename="smoke_test.png",
      stored_filename="smoke_test.png",
      file_path="uploads/xrays/smoke_test.png",
      file_type="png",
      file_size=123,
      body_part="Chest",
      model_name="pending",
      analysis_version="1.0.0",
      status="uploaded",
      disclaimer=XRAY_MEDICAL_DISCLAIMER,
      upload_date=utc_now(),
      created_at=utc_now(),
      updated_at=utc_now(),
    )
    db.session.add(row)
    db.session.commit()
    rid = row.id
    card = row.to_history_card()
    full = row.to_dict(include_explanation=True)
    assert card["id"] == rid
    assert card["body_part"] == "Chest"
    assert "educational" in (full["disclaimer"] or "").lower()
    assert full["model_name"] == "pending"
    db.session.delete(row)
    db.session.commit()
    print(f"Smoke insert/delete OK (id={rid})")

  print("X-ray Database module (Module 1) verified.")
