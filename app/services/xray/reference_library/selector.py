"""Phase 9 — auto-retrieve the best educational healthy reference."""

from __future__ import annotations

from typing import Any


class ReferenceLibrarySelector:
  """High-level selector for comparison / APIs."""

  @classmethod
  def select_for_analysis(cls, row) -> Any:
    from app.services.xray.reference_library.service import ReferenceLibraryService

    body_part, projection, age, gender = cls._attrs_from_row(row)
    return ReferenceLibraryService.select_reference(
      body_part=body_part,
      patient_age=age,
      gender=gender,
      projection=projection,
    )

  @classmethod
  def select(
    cls,
    *,
    body_part: str | None,
    projection: str | None = None,
    patient_age: int | None = None,
    gender: str | None = None,
    orientation: str | None = None,
  ) -> Any:
    from app.services.xray.reference_library.service import ReferenceLibraryService

    return ReferenceLibraryService.select_reference(
      body_part=body_part,
      patient_age=patient_age,
      gender=gender,
      projection=projection,
      orientation=orientation,
    )

  @staticmethod
  def empty_message() -> str:
    from app.services.xray.reference_xray_library_service import EMPTY_LIBRARY_MESSAGE

    return EMPTY_LIBRARY_MESSAGE

  @staticmethod
  def _attrs_from_row(row) -> tuple[str | None, str | None, int | None, str | None]:
    body_part = getattr(row, "body_part", None)
    projection = None
    age = getattr(row, "patient_age", None)
    gender = getattr(row, "gender", None)

    structured = getattr(row, "structured_findings", None)
    if isinstance(structured, dict):
      body_part = body_part or structured.get("body_part")
      projection = structured.get("projection") or projection

    body_det = getattr(row, "body_detection", None)
    if isinstance(body_det, dict):
      body_part = body_part or body_det.get("body_part")

    proj_det = getattr(row, "projection_detection", None)
    if isinstance(proj_det, dict):
      projection = projection or proj_det.get("projection")

    extras = getattr(row, "clinical_extras", None)
    if isinstance(extras, dict):
      projection = projection or extras.get("projection")

    if projection and str(projection).strip().lower() == "unknown":
      projection = None

    try:
      age_i = int(age) if age is not None else None
    except (TypeError, ValueError):
      age_i = None

    return body_part, projection, age_i, gender


def select_best_healthy_reference(row=None, **kwargs) -> Any:
  """Convenience entry for Phase 9 automatic retrieval."""
  if row is not None:
    return ReferenceLibrarySelector.select_for_analysis(row)
  return ReferenceLibrarySelector.select(**kwargs)
