"""Module 2 — Patient Clinical Information validation tests."""

from app.services.xray.patient_info import PatientInfoService


def _valid(**overrides):
  base = {
    "patient_age": 58,
    "gender": "Male",
    "body_part": "Chest",
    "symptoms": "Persistent cough and fever",
    "reason_for_exam": "Chronic cough for two weeks",
    "smoking_history": "Former Smoker",
  }
  base.update(overrides)
  return base


def test_validate_accepts_complete_payload():
  result = PatientInfoService.validate(_valid())
  assert result.ok
  assert result.data is not None
  assert result.data.patient_age == 58
  assert result.data.gender == "Male"
  assert result.data.body_part == "Chest"
  assert result.data.smoking_history == "Former Smoker"
  assert result.data.to_ai_context()["patient_age"] == 58


def test_age_required():
  result = PatientInfoService.validate(_valid(patient_age=None))
  assert not result.ok
  assert any(e.code == "age_required" for e in result.errors)


def test_age_must_be_number():
  result = PatientInfoService.validate(_valid(patient_age="abc"))
  assert not result.ok
  assert any(e.code == "age_invalid" for e in result.errors)


def test_age_range():
  low = PatientInfoService.validate(_valid(patient_age=-1))
  high = PatientInfoService.validate(_valid(patient_age=121))
  ok = PatientInfoService.validate(_valid(patient_age=0))
  ok2 = PatientInfoService.validate(_valid(patient_age=120))
  assert not low.ok and any(e.code == "age_out_of_range" for e in low.errors)
  assert not high.ok and any(e.code == "age_out_of_range" for e in high.errors)
  assert ok.ok and ok2.ok


def test_gender_required_and_enum():
  missing = PatientInfoService.validate(_valid(gender=""))
  bad = PatientInfoService.validate(_valid(gender="Unknown-Gender"))
  assert not missing.ok
  assert not bad.ok
  assert any("gender" in e.field for e in bad.errors)


def test_gender_case_insensitive_canonical():
  result = PatientInfoService.validate(_valid(gender="female"))
  assert result.ok
  assert result.data.gender == "Female"


def test_body_part_required_and_expanded_list():
  missing = PatientInfoService.validate(_valid(body_part=None))
  wrist = PatientInfoService.validate(_valid(body_part="Wrist"))
  bad = PatientInfoService.validate(_valid(body_part="Toe"))
  assert not missing.ok
  assert wrist.ok and wrist.data.body_part == "Wrist"
  assert not bad.ok


def test_symptoms_max_length():
  result = PatientInfoService.validate(_valid(symptoms="x" * 1001))
  assert not result.ok
  assert any(e.code == "symptoms_too_long" for e in result.errors)


def test_reason_max_length():
  result = PatientInfoService.validate(_valid(reason_for_exam="y" * 1001))
  assert not result.ok
  assert any(e.code == "reason_for_exam_too_long" for e in result.errors)


def test_smoking_optional_but_must_match_enum():
  ok = PatientInfoService.validate(_valid(smoking_history=None))
  bad = PatientInfoService.validate(_valid(smoking_history="Heavy"))
  assert ok.ok
  assert ok.data.smoking_history is None
  assert not bad.ok


def test_aliases_from_form():
  result = PatientInfoService.validate(
    {
      "age": "42",
      "sex": "Other",
      "bodyPart": "Knee",
      "reason": "Pain after fall",
      "smokingHistory": "Never Smoked",
    }
  )
  assert result.ok
  assert result.data.patient_age == 42
  assert result.data.body_part == "Knee"
  assert result.data.reason_for_exam == "Pain after fall"
  assert result.data.smoking_history == "Never Smoked"


def test_clinical_extras_future_ready():
  result = PatientInfoService.validate(
    _valid(clinical_extras={"height": 170, "diabetes": "Type 2", "unknown_future": True})
  )
  assert result.ok
  assert result.data.clinical_extras["height"] == 170
  assert result.data.clinical_extras["diabetes"] == "Type 2"


def test_form_options_expose_enums():
  opts = PatientInfoService.form_options()
  assert "Male" in opts["genders"]
  assert "Chest" in opts["body_parts"] and "Ankle" in opts["body_parts"]
  assert "Former Smoker" in opts["smoking_history"]
  assert opts["limits"]["patient_age_max"] == 120
  assert "patient_age" in opts["required"]
