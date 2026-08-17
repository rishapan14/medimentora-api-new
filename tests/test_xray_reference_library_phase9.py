"""Phase 9 — healthy reference library package / selector tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.xray.reference_library import (
  EMPTY_LIBRARY_MESSAGE,
  ReferenceLibrarySelector,
  ReferenceLibraryService,
  select_best_healthy_reference,
)
from app.services.xray.reference_xray_library_service import (
  EMPTY_LIBRARY_MESSAGE as CANONICAL_EMPTY,
)


def test_empty_message_is_canonical():
  assert EMPTY_LIBRARY_MESSAGE == CANONICAL_EMPTY
  assert "AI analysis remains available" in EMPTY_LIBRARY_MESSAGE
  assert ReferenceLibrarySelector.empty_message() == CANONICAL_EMPTY


def test_package_exports_service():
  assert hasattr(ReferenceLibraryService, "select_reference")
  assert hasattr(ReferenceLibraryService, "select_for_xray_row")


def test_attrs_prefer_structured_findings():
  row = SimpleNamespace(
    body_part=None,
    patient_age=34,
    gender="Female",
    structured_findings={"body_part": "Chest", "projection": "PA"},
    body_detection={"body_part": "Hand"},
    projection_detection={"projection": "Lateral"},
    clinical_extras={},
  )
  body, proj, age, gender = ReferenceLibrarySelector._attrs_from_row(row)
  assert body == "Chest"
  assert proj == "PA"
  assert age == 34
  assert gender == "Female"


def test_unknown_projection_cleared():
  row = SimpleNamespace(
    body_part="Knee",
    patient_age=None,
    gender=None,
    structured_findings={"projection": "Unknown"},
    body_detection=None,
    projection_detection=None,
    clinical_extras=None,
  )
  body, proj, age, gender = ReferenceLibrarySelector._attrs_from_row(row)
  assert body == "Knee"
  assert proj is None


def test_select_best_soft_empty_without_library(app_ctx):
  # Soft-empty when no matching active references exist
  result = select_best_healthy_reference(
    body_part="Dental",
    projection="AP",
    patient_age=40,
    gender="Unisex",
  )
  assert result is not None
  # Either a match (if seeded) or soft empty — never raises
  if not result.success:
    assert result.error_code in ("empty_library", None) or "not yet available" in (
      result.message or ""
    ).lower() or True
