"""Verify xray_analysis educational comparison columns (Healthy X-Ray Comparison Module 1)."""

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_xray_analysis_schema
from app.models.xray_analysis_model import (
  XRAY_AGE_GROUPS,
  XRAY_BODY_PARTS,
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_REFERENCE_GENDERS,
  XrayAnalysis,
)
from app.utils import utc_now

REQUIRED = {
  "id",
  "user_id",
  "filename",
  "file_path",
  "body_part",
  "patient_age",
  "gender",
  "reference_image_path",
  "comparison_summary",
  "comparison_generated_at",
  "heatmap_path",
  "possible_findings",
  "status",
  "created_at",
  "updated_at",
}

app = create_app()
with app.app_context():
  ensure_xray_analysis_schema()
  ensure_xray_analysis_schema()  # idempotent

  tables = inspect(db.engine).get_table_names()
  assert "xray_analysis" in tables, "xray_analysis table missing"
  cols = {c["name"] for c in inspect(db.engine).get_columns("xray_analysis")}
  missing = sorted(REQUIRED - cols)
  print("=== xray_analysis comparison columns ===")
  for name in ("reference_image_path", "comparison_summary", "comparison_generated_at"):
    print(f"  [{'OK' if name in cols else 'MISSING'}] {name}")
  print()
  if missing:
    print("MISSING:", missing)
    raise SystemExit(1)

  assert "Child" in XRAY_AGE_GROUPS and "Adult" in XRAY_AGE_GROUPS
  assert "Unisex" in XRAY_REFERENCE_GENDERS
  assert "Chest" in XRAY_BODY_PARTS

  from app.models.user_model import User

  user = User.query.first()
  if not user:
    print("No user found — skipping insert smoke test.")
  else:
    now = utc_now()
    row = XrayAnalysis(
      user_id=user.id,
      filename="smoke_comparison.png",
      stored_filename="smoke_comparison.png",
      file_path="uploads/xrays/smoke_comparison.png",
      file_type="png",
      file_size=123,
      patient_age=30,
      gender="Female",
      body_part="Chest",
      reference_image_path="reference_library/chest/adult/female/healthy_01.png",
      comparison_summary=(
        "Compared with the educational reference image, the uploaded radiograph shows "
        "differences that may warrant professional evaluation. This is not a diagnosis."
      ),
      comparison_generated_at=now,
      model_name="pending",
      analysis_version="1.0.0",
      status="uploaded",
      disclaimer=XRAY_MEDICAL_DISCLAIMER,
      upload_date=now,
      created_at=now,
      updated_at=now,
    )
    db.session.add(row)
    db.session.commit()
    rid = row.id
    card = row.to_history_card()
    full = row.to_dict()
    assert card["has_comparison"] is True
    assert card["reference_image_path"].endswith("healthy_01.png")
    assert full["comparison_summary"].startswith("Compared with")
    assert full["comparison_generated_at"]
    assert full["has_comparison"] is True
    db.session.delete(row)
    db.session.commit()
    print(f"Smoke insert/delete OK (id={rid})")

  print("Educational Healthy X-Ray Comparison — Database module verified.")
