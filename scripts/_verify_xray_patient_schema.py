"""Verify xray_analysis patient clinical columns (Patient Clinical Information Module 1)."""

from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_xray_analysis_schema
from app.models.xray_analysis_model import (
  XRAY_BODY_PARTS,
  XRAY_GENDERS,
  XRAY_MEDICAL_DISCLAIMER,
  XRAY_SMOKING_HISTORY,
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
  "symptoms",
  "reason_for_exam",
  "smoking_history",
  "clinical_extras",
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

  assert "Chest" in XRAY_BODY_PARTS and "Wrist" in XRAY_BODY_PARTS and "Ankle" in XRAY_BODY_PARTS
  assert "Male" in XRAY_GENDERS and "Prefer not to say" in XRAY_GENDERS
  assert "Former Smoker" in XRAY_SMOKING_HISTORY

  from app.models.user_model import User

  user = User.query.first()
  if not user:
    print("No user found — skipping insert smoke test.")
  else:
    row = XrayAnalysis(
      user_id=user.id,
      filename="smoke_patient.png",
      stored_filename="smoke_patient.png",
      file_path="uploads/xrays/smoke_patient.png",
      file_type="png",
      file_size=123,
      patient_age=58,
      gender="Male",
      body_part="Chest",
      symptoms="Persistent cough and fever",
      reason_for_exam="Chronic cough for two weeks",
      smoking_history="Former Smoker",
      clinical_extras={},
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
    clinical = row.patient_clinical_dict()
    assert card["patient_age"] == 58
    assert card["gender"] == "Male"
    assert card["body_part"] == "Chest"
    assert full["symptoms"].startswith("Persistent")
    assert full["reason_for_exam"].startswith("Chronic")
    assert full["smoking_history"] == "Former Smoker"
    assert clinical["safety"]["supporting_context_only"] is True
    assert "clinical_extras" in full
    db.session.delete(row)
    db.session.commit()
    print(f"Smoke insert/delete OK (id={rid})")

  print("Patient Clinical Information — Database module verified.")
