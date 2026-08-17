"""Phase 14 — patient clinical context persistence and safety."""

from __future__ import annotations

from app.models.xray_analysis_model import XRAY_BODY_PARTS, XRAY_PROJECTIONS
from app.services.xray.patient_info import PatientInfoService


def test_projection_persists_in_patient_clinical_dict():
  result = PatientInfoService.validate(
    {
      "patient_age": 42,
      "gender": "Female",
      "body_part": "Chest",
      "projection": "PA",
      "symptoms": "Cough",
      "smoking_history": "Never Smoked",
    }
  )
  assert result.ok
  assert result.data is not None
  payload = result.data.to_dict()
  assert payload["projection"] == "PA"
  assert payload["clinical_extras"]["projection"] == "PA"
  assert payload["safety"]["supporting_context_only"] is True
  assert payload["safety"]["not_a_diagnosis"] is True


def test_axial_and_skyline_projections_accepted():
  for view in ("Axial", "Skyline"):
    result = PatientInfoService.validate(
      {
        "patient_age": 30,
        "gender": "Male",
        "body_part": "Knee",
        "projection": view,
      }
    )
    assert result.ok, result.error_messages()
    assert result.data.projection == view


def test_finger_clavicle_femur_skull_body_parts_accepted():
  for part in ("Finger", "Clavicle", "Femur", "Skull"):
    result = PatientInfoService.validate(
      {
        "patient_age": 25,
        "gender": "Other",
        "body_part": part,
        "projection": "AP",
      }
    )
    assert result.ok, result.error_messages()
    assert result.data.body_part == part


def test_frontend_fallback_enums_align_with_backend():
  # Keep client offline fallbacks in sync with API enums used by Phase 14 form.
  assert "Finger" in XRAY_BODY_PARTS
  assert "Clavicle" in XRAY_BODY_PARTS
  assert "Femur" in XRAY_BODY_PARTS
  assert "Skull" in XRAY_BODY_PARTS
  assert "Axial" in XRAY_PROJECTIONS
  assert "Skyline" in XRAY_PROJECTIONS


def test_ai_context_includes_projection_and_safety():
  result = PatientInfoService.validate(
    {
      "patient_age": 58,
      "gender": "Male",
      "body_part": "Chest",
      "projection": "Lateral",
      "reason_for_exam": "Education demo",
    }
  )
  assert result.ok
  ai = result.data.to_ai_context()
  assert ai["projection"] == "Lateral"
  assert ai["safety"]["supporting_context_only"] is True
  assert "image" not in ai
  assert "file_path" not in ai
