"""Patient Clinical Information validation (Module 2 / Phase 14).

Validates supporting clinical context submitted with X-ray analysis.
These fields are NEVER a diagnosis — validation only enforces shape/enums/limits.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from app.models.xray_analysis_model import (
  XRAY_BODY_PARTS,
  XRAY_FUTURE_CLINICAL_EXTRA_KEYS,
  XRAY_GENDERS,
  XRAY_PROJECTIONS,
  XRAY_SMOKING_HISTORY,
)

logger = logging.getLogger(__name__)

MAX_SYMPTOMS_LEN = 1000
MAX_REASON_LEN = 1000
MIN_AGE = 0
MAX_AGE = 120


@dataclass
class PatientInfoIssue:
  """One friendly validation error for a clinical field."""

  field: str
  code: str
  message: str

  def to_dict(self) -> dict:
    return {"field": self.field, "code": self.code, "message": self.message}


@dataclass
class PatientClinicalInfo:
  """Normalized patient clinical context ready to persist / send to AI."""

  patient_age: int
  gender: str
  body_part: str
  symptoms: str | None = None
  reason_for_exam: str | None = None
  smoking_history: str | None = None
  projection: str | None = None
  clinical_extras: dict[str, Any] = field(default_factory=dict)

  def to_dict(self) -> dict:
    extras = dict(self.clinical_extras or {})
    if self.projection:
      extras["projection"] = self.projection
    return {
      "patient_age": self.patient_age,
      "gender": self.gender,
      "body_part": self.body_part,
      "projection": self.projection or extras.get("projection"),
      "symptoms": self.symptoms,
      "reason_for_exam": self.reason_for_exam,
      "smoking_history": self.smoking_history,
      "clinical_extras": extras,
      "safety": {
        "supporting_context_only": True,
        "not_a_diagnosis": True,
      },
    }

  def to_ai_context(self) -> dict:
    """Compact JSON for Gemini / explainer — findings are added by callers."""
    return {
      "patient_age": self.patient_age,
      "gender": self.gender,
      "body_part": self.body_part,
      "projection": self.projection or "",
      "symptoms": self.symptoms or "",
      "reason_for_exam": self.reason_for_exam or "",
      "smoking_history": self.smoking_history or "",
      "safety": {
        "supporting_context_only": True,
        "not_a_diagnosis": True,
      },
    }


@dataclass
class PatientInfoValidationResult:
  """Outcome of validating patient clinical information."""

  ok: bool
  data: PatientClinicalInfo | None = None
  errors: list[PatientInfoIssue] = field(default_factory=list)

  def error_messages(self) -> list[str]:
    return [e.message for e in self.errors]

  def to_dict(self) -> dict:
    return {
      "ok": self.ok,
      "data": self.data.to_dict() if self.data else None,
      "errors": [e.to_dict() for e in self.errors],
    }


class PatientInfoService:
  """Validate and normalize Patient Clinical Information form payloads."""

  GENDERS = XRAY_GENDERS
  BODY_PARTS = XRAY_BODY_PARTS
  SMOKING_HISTORY = XRAY_SMOKING_HISTORY
  PROJECTIONS = XRAY_PROJECTIONS
  FUTURE_EXTRA_KEYS = XRAY_FUTURE_CLINICAL_EXTRA_KEYS

  @classmethod
  def form_options(cls) -> dict:
    """Enums for frontend form dropdowns."""
    return {
      "genders": list(cls.GENDERS),
      "body_parts": list(cls.BODY_PARTS),
      "projections": list(cls.PROJECTIONS),
      "smoking_history": list(cls.SMOKING_HISTORY),
      "future_clinical_extra_keys": list(cls.FUTURE_EXTRA_KEYS),
      "limits": {
        "patient_age_min": MIN_AGE,
        "patient_age_max": MAX_AGE,
        "symptoms_max_length": MAX_SYMPTOMS_LEN,
        "reason_for_exam_max_length": MAX_REASON_LEN,
      },
      "required": ["patient_age", "gender", "body_part"],
      "optional": ["projection", "symptoms", "reason_for_exam", "smoking_history", "clinical_extras"],
    }

  @classmethod
  def validate(cls, payload: Mapping[str, Any] | None) -> PatientInfoValidationResult:
    """
    Validate a dict/form mapping of clinical fields.

    Accepts common aliases: age, patientAge, reason, smokingHistory, bodyPart.
    """
    raw = dict(payload or {})
    errors: list[PatientInfoIssue] = []

    age = cls._pick(raw, "patient_age", "age", "patientAge")
    gender = cls._pick(raw, "gender", "sex")
    body_part = cls._pick(raw, "body_part", "bodyPart")
    symptoms = cls._pick(raw, "symptoms")
    reason = cls._pick(raw, "reason_for_exam", "reason", "reasonForExam", "reason_for_examination")
    smoking = cls._pick(raw, "smoking_history", "smokingHistory", "smoking")
    projection = cls._pick(raw, "projection", "view", "view_position", "viewPosition")
    extras = cls._pick(raw, "clinical_extras", "clinicalExtras", "extras")

    patient_age = cls._validate_age(age, errors)
    gender_n = cls._validate_enum(
      gender,
      field="gender",
      allowed=cls.GENDERS,
      required=True,
      errors=errors,
      friendly_name="Gender",
    )
    body_n = cls._validate_enum(
      body_part,
      field="body_part",
      allowed=cls.BODY_PARTS,
      required=True,
      errors=errors,
      friendly_name="Body part",
    )
    symptoms_n = cls._validate_optional_text(
      symptoms,
      field="symptoms",
      max_len=MAX_SYMPTOMS_LEN,
      errors=errors,
      friendly_name="Symptoms",
    )
    reason_n = cls._validate_optional_text(
      reason,
      field="reason_for_exam",
      max_len=MAX_REASON_LEN,
      errors=errors,
      friendly_name="Reason for examination",
    )
    smoking_n = cls._validate_enum(
      smoking,
      field="smoking_history",
      allowed=cls.SMOKING_HISTORY,
      required=False,
      errors=errors,
      friendly_name="Smoking history",
    )
    projection_n = cls._validate_enum(
      projection,
      field="projection",
      allowed=cls.PROJECTIONS,
      required=False,
      errors=errors,
      friendly_name="Projection / view",
    )
    extras_n = cls._validate_clinical_extras(extras, errors)
    if projection_n:
      extras_n = dict(extras_n or {})
      extras_n["projection"] = projection_n

    if errors:
      logger.info(
        "Patient clinical validation failed: %s",
        [e.code for e in errors],
      )
      return PatientInfoValidationResult(ok=False, errors=errors)

    data = PatientClinicalInfo(
      patient_age=int(patient_age),  # type: ignore[arg-type]
      gender=str(gender_n),
      body_part=str(body_n),
      symptoms=symptoms_n,
      reason_for_exam=reason_n,
      smoking_history=smoking_n,
      projection=projection_n,
      clinical_extras=extras_n,
    )
    return PatientInfoValidationResult(ok=True, data=data)

  @classmethod
  def validate_from_request_values(cls, values: Mapping[str, Any]) -> PatientInfoValidationResult:
    """Validate Flask request.form / mixed JSON+form values."""
    return cls.validate(values)

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _pick(raw: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
      if key in raw and raw[key] is not None:
        return raw[key]
    return None

  @classmethod
  def _validate_age(cls, value: Any, errors: list[PatientInfoIssue]) -> int | None:
    if value is None or (isinstance(value, str) and not value.strip()):
      errors.append(
        PatientInfoIssue(
          field="patient_age",
          code="age_required",
          message="Patient age is required.",
        )
      )
      return None

    try:
      if isinstance(value, bool):
        raise ValueError("bool")
      age = int(str(value).strip())
    except (TypeError, ValueError):
      errors.append(
        PatientInfoIssue(
          field="patient_age",
          code="age_invalid",
          message="Patient age must be a whole number.",
        )
      )
      return None

    if age < MIN_AGE or age > MAX_AGE:
      errors.append(
        PatientInfoIssue(
          field="patient_age",
          code="age_out_of_range",
          message=f"Patient age must be between {MIN_AGE} and {MAX_AGE}.",
        )
      )
      return None
    return age

  @classmethod
  def _validate_enum(
    cls,
    value: Any,
    *,
    field: str,
    allowed: tuple[str, ...],
    required: bool,
    errors: list[PatientInfoIssue],
    friendly_name: str,
  ) -> str | None:
    if value is None or (isinstance(value, str) and not str(value).strip()):
      if required:
        errors.append(
          PatientInfoIssue(
            field=field,
            code=f"{field}_required",
            message=f"{friendly_name} is required.",
          )
        )
      return None

    text = str(value).strip()
    # Case-insensitive match → canonical enum value
    lookup = {a.lower(): a for a in allowed}
    canonical = lookup.get(text.lower())
    if not canonical:
      choices = ", ".join(allowed)
      errors.append(
        PatientInfoIssue(
          field=field,
          code=f"{field}_invalid",
          message=f"{friendly_name} must be one of: {choices}.",
        )
      )
      return None
    return canonical

  @classmethod
  def _validate_optional_text(
    cls,
    value: Any,
    *,
    field: str,
    max_len: int,
    errors: list[PatientInfoIssue],
    friendly_name: str,
  ) -> str | None:
    if value is None:
      return None
    text = str(value).strip()
    if not text:
      return None
    if len(text) > max_len:
      errors.append(
        PatientInfoIssue(
          field=field,
          code=f"{field}_too_long",
          message=f"{friendly_name} must be at most {max_len} characters.",
        )
      )
      return None
    return text

  @classmethod
  def _validate_clinical_extras(
    cls,
    value: Any,
    errors: list[PatientInfoIssue],
  ) -> dict[str, Any]:
    """Allow a dict of future fields; unknown keys kept, non-dicts rejected."""
    if value is None or value == "":
      return {}
    if isinstance(value, str):
      # Allow JSON string from multipart forms (Module 3 may pass this)
      import json

      try:
        value = json.loads(value)
      except json.JSONDecodeError:
        errors.append(
          PatientInfoIssue(
            field="clinical_extras",
            code="clinical_extras_invalid",
            message="Clinical extras must be a valid JSON object.",
          )
        )
        return {}
    if not isinstance(value, dict):
      errors.append(
        PatientInfoIssue(
          field="clinical_extras",
          code="clinical_extras_invalid",
          message="Clinical extras must be an object/dictionary.",
        )
      )
      return {}
    # Soft-normalize known future keys; keep others for forward compatibility
    cleaned: dict[str, Any] = {}
    for key, val in value.items():
      if val is None or val == "":
        continue
      cleaned[str(key)] = val
    return cleaned
