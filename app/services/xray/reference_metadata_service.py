"""Reference X-ray metadata validation (Module 4).

This service enforces the dataset-ready metadata contract for healthy
educational reference radiographs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.reference_xray_library_model import (
  REFERENCE_AGE_GROUPS,
  REFERENCE_BODY_PARTS,
  REFERENCE_DIFFICULTIES,
  REFERENCE_GENDERS,
  REFERENCE_ORIENTATIONS,
  REFERENCE_PROJECTIONS,
)


REQUIRED_UPLOAD_STRING_FIELDS = (
  "source",
  "license",
  "description",
  "anatomical_notes",
)

REQUIRED_UPLOAD_ENUM_FIELDS = (
  "body_part",
  "projection",
  "orientation",
  "age_group",
  "gender",
  "difficulty",
)


@dataclass
class MetadataValidationPayload:
  body_part: str
  projection: str
  orientation: str
  age_group: str
  gender: str
  difficulty: str
  title: str | None
  source: str
  license: str
  description: str
  anatomical_notes: str


class ReferenceMetadataService:
  """Strict validation for dataset-ready reference uploads."""

  @classmethod
  def validate(
    cls, payload: dict[str, Any], *, for_upload: bool = True
  ) -> dict[str, Any]:
    errors: list[dict[str, str]] = []

    def require_enum(field: str, allowed: tuple[str, ...], *, required: bool) -> str | None:
      raw = payload.get(field)
      if raw in (None, ""):
        if required:
          errors.append({"field": field, "message": f"{field} is required."})
        return None
      value = str(raw).strip()
      lookup = {a.lower(): a for a in allowed}
      canonical = lookup.get(value.lower())
      if not canonical:
        errors.append(
          {
            "field": field,
            "message": f"Invalid {field}. Allowed: {', '.join(allowed)}",
          }
        )
        return None
      return canonical

    def require_string(field: str, *, required: bool) -> str | None:
      raw = payload.get(field)
      if raw in (None, ""):
        if required:
          errors.append({"field": field, "message": f"{field} is required."})
        return None
      value = str(raw).strip()
      if required and not value:
        errors.append({"field": field, "message": f"{field} is required."})
        return None
      return value

    def normalize_title(raw: Any) -> str | None:
      if raw in (None, ""):
        return None
      t = str(raw).strip()
      return t or None

    # Enums
    body_part = require_enum(
      "body_part",
      REFERENCE_BODY_PARTS,
      required=for_upload,
    )
    projection = require_enum(
      "projection",
      REFERENCE_PROJECTIONS,
      required=for_upload,
    )
    orientation = require_enum(
      "orientation",
      REFERENCE_ORIENTATIONS,
      required=for_upload,
    )
    age_group = require_enum(
      "age_group",
      REFERENCE_AGE_GROUPS,
      required=for_upload,
    )
    gender = require_enum(
      "gender",
      REFERENCE_GENDERS,
      required=for_upload,
    )
    difficulty = require_enum(
      "difficulty",
      REFERENCE_DIFFICULTIES,
      required=for_upload,
    )

    # Strings
    source = require_string("source", required=for_upload)
    license_text = require_string("license", required=for_upload)
    description = require_string("description", required=for_upload)
    anatomical_notes = require_string("anatomical_notes", required=for_upload)

    if errors:
      # Friendly summary for frontend toast (field_errors are also returned)
      first = errors[0]
      message = f"Metadata validation failed: {first['field']}."
      return {
        "success": False,
        "message": message,
        "error_code": "validation_error",
        "data": {},
        "field_errors": errors,
      }

    normalized = {
      "body_part": body_part,
      "projection": projection,
      "orientation": orientation,
      "age_group": age_group,
      "gender": gender,
      "difficulty": difficulty,
      "title": normalize_title(payload.get("title")),
      "source": source,
      "license": license_text,
      "description": description,
      "anatomical_notes": anatomical_notes,
    }
    return {
      "success": True,
      "message": "Metadata valid.",
      "error_code": None,
      "data": {"metadata": normalized},
      "field_errors": [],
    }

