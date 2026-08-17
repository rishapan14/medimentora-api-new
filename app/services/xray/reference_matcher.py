"""Image Matching Engine (Module 6).

Detect patient X-ray attributes → rank active references by weighted scoring →
return the highest-scoring educational match.  Never returns random images.

If no exact match: returns the closest educational reference with a message.
If no reference at all: returns a professional empty state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any

from app.extensions import db
from app.models.reference_xray_library_model import (
  REFERENCE_GENDER_RELEVANT_BODY_PARTS,
  ReferenceXrayLibrary,
)
from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER
from app.services.xray.reference_library import ReferenceLibraryService, PLACEHOLDER_MARKERS
from app.services.xray.reference_xray_library_service import (
  EMPTY_LIBRARY_MESSAGE,
  ReferenceXrayLibraryService,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ weights
W_BODY_PART = 200
W_PROJECTION = 150
W_AGE_GROUP = 100
W_GENDER_EXACT = 40
W_GENDER_UNISEX = 15
W_ORIENTATION = 30
W_DIFFICULTY_MATCH = 10
PENALTY_CROSS_BODY = -195
PENALTY_PROJECTION_MISMATCH = -40
PENALTY_AGE_MISMATCH = -20


@dataclass
class MatchResult:
  """Returned by ``ReferenceMatcher.match()``."""

  success: bool
  primary: dict[str, Any] | None = None
  alternatives: list[dict[str, Any]] = field(default_factory=list)
  matched_body_part: str | None = None
  matched_projection: str | None = None
  matched_age_group: str | None = None
  matched_orientation: str | None = None
  gender_used: bool = False
  score: int = 0
  cross_body: bool = False
  message: str = ""
  error_code: str | None = None

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "primary": self.primary,
      "alternatives": self.alternatives,
      "matched_body_part": self.matched_body_part,
      "matched_projection": self.matched_projection,
      "matched_age_group": self.matched_age_group,
      "matched_orientation": self.matched_orientation,
      "gender_used": self.gender_used,
      "score": self.score,
      "cross_body": self.cross_body,
      "message": self.message,
      "error_code": self.error_code,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    }


class ReferenceMatcher:
  """Weighted scoring matcher over ``reference_xray_library``."""

  @classmethod
  def match(
    cls,
    *,
    body_part: str | None,
    projection: str | None = None,
    patient_age: int | None = None,
    gender: str | None = None,
    orientation: str | None = None,
    difficulty: str | None = None,
    limit_alternatives: int = 3,
  ) -> MatchResult:
    """Find the best active reference for the given patient attributes.

    Scoring guarantees deterministic, reproducible results — never random.
    """
    wanted_part = ReferenceLibraryService.normalize_body_part(body_part)
    wanted_proj = ReferenceLibraryService.normalize_projection(projection)
    wanted_age = ReferenceLibraryService.age_group_from_age(patient_age)
    wanted_gender = ReferenceLibraryService.normalize_gender(gender)
    wanted_orient = ReferenceLibraryService.normalize_orientation(orientation)
    use_gender = (
      wanted_part in REFERENCE_GENDER_RELEVANT_BODY_PARTS and wanted_gender is not None
    )

    try:
      candidates = cls._load_candidates()
    except Exception:
      logger.exception("Failed loading reference candidates")
      candidates = []

    if not candidates:
      return MatchResult(
        success=False,
        matched_body_part=wanted_part,
        matched_projection=wanted_proj,
        matched_age_group=wanted_age,
        matched_orientation=wanted_orient,
        gender_used=use_gender,
        message=EMPTY_LIBRARY_MESSAGE,
        error_code="empty_library",
      )

    root = ReferenceXrayLibraryService.library_root()

    scored: list[tuple[int, ReferenceXrayLibrary]] = []
    for row in candidates:
      score = cls._score(
        row,
        wanted_part=wanted_part,
        wanted_proj=wanted_proj,
        wanted_age=wanted_age,
        wanted_gender=wanted_gender,
        wanted_orient=wanted_orient,
        difficulty=difficulty,
        use_gender=use_gender,
      )
      scored.append((score, row))

    scored.sort(key=lambda x: (-x[0], x[1].id))

    best_score, best_row = scored[0]
    cross_body = best_row.body_part.lower() != wanted_part.lower()

    # Treat "exact match" as equality on the requested attributes.
    # If an attribute wasn't provided (e.g., projection/orientation/gender), we don't require exact equality.
    exact_body = best_row.body_part.lower() == wanted_part.lower()
    exact_projection = (
      True
      if wanted_proj is None
      else (best_row.projection or "").lower() == wanted_proj.lower()
    )
    exact_age = (
      True
      if patient_age is None
      else (best_row.age_group or "").lower() == wanted_age.lower()
    )
    exact_orientation = (
      True
      if wanted_orient is None
      else (best_row.orientation or "").lower() == wanted_orient.lower()
    )
    exact_gender = (
      True
      if (not use_gender) or (wanted_gender is None)
      else (best_row.gender or "").lower() == wanted_gender.lower()
    )
    exact_match = (
      exact_body and exact_projection and exact_age and exact_orientation and exact_gender
    )

    primary_dict = best_row.to_dict(library_root=root)
    alts = [r.to_dict(library_root=root) for _, r in scored[1 : 1 + limit_alternatives]]

    if exact_match:
      message = (
        f"Selected healthy {best_row.body_part} {best_row.projection} reference "
        f"({best_row.age_group}, {best_row.gender}). Educational only — not a diagnosis."
      )
    else:
      if cross_body:
        message = (
          f"No exact {wanted_part} healthy reference was found. "
          f"Showing the closest educational reference "
          f"({best_row.body_part} {best_row.projection}). "
          "Educational only — not a diagnosis."
        )
      else:
        message = (
          "No exact healthy reference match was found for the provided attributes. "
          f"Showing the closest educational reference "
          f"({best_row.body_part} {best_row.projection}). "
          "Educational only — not a diagnosis."
        )

    return MatchResult(
      success=True,
      primary=primary_dict,
      alternatives=alts,
      matched_body_part=wanted_part,
      matched_projection=wanted_proj,
      matched_age_group=wanted_age,
      matched_orientation=wanted_orient,
      gender_used=use_gender,
      score=best_score,
      cross_body=cross_body,
      message=message,
    )

  # ------------------------------------------------------------------ scoring

  @classmethod
  def _score(
    cls,
    row: ReferenceXrayLibrary,
    *,
    wanted_part: str,
    wanted_proj: str | None,
    wanted_age: str,
    wanted_gender: str | None,
    wanted_orient: str | None,
    difficulty: str | None,
    use_gender: bool,
  ) -> int:
    score = 0

    # Body part (most important)
    if row.body_part.lower() == wanted_part.lower():
      score += W_BODY_PART
    else:
      score += W_BODY_PART + PENALTY_CROSS_BODY  # small baseline for cross-body

    # Projection
    if wanted_proj:
      if row.projection.lower() == wanted_proj.lower():
        score += W_PROJECTION
      elif row.projection.lower() == "other":
        score += 20
      else:
        score += PENALTY_PROJECTION_MISMATCH
    else:
      if row.projection.upper() in ("PA", "AP"):
        score += 10

    # Age group
    if row.age_group.lower() == wanted_age.lower():
      score += W_AGE_GROUP
    else:
      score += PENALTY_AGE_MISMATCH

    # Gender
    if use_gender:
      if wanted_gender and row.gender.lower() == wanted_gender.lower():
        score += W_GENDER_EXACT
      elif row.gender.lower() == "unisex":
        score += W_GENDER_UNISEX
    else:
      if row.gender.lower() == "unisex":
        score += W_GENDER_UNISEX + 10
      elif wanted_gender and row.gender.lower() == wanted_gender.lower():
        score += 5

    # Orientation
    if wanted_orient:
      if row.orientation and row.orientation.lower() == wanted_orient.lower():
        score += W_ORIENTATION
      elif row.orientation and row.orientation.lower() == "unknown":
        score += 5

    # Difficulty preference (minor tiebreaker)
    if difficulty and row.difficulty and row.difficulty.lower() == difficulty.lower():
      score += W_DIFFICULTY_MATCH

    return score

  # ------------------------------------------------------------------ data

  @classmethod
  def _load_candidates(cls) -> list[ReferenceXrayLibrary]:
    """Load all active references whose image file exists on disk."""
    root = ReferenceXrayLibraryService.library_root()
    rows = ReferenceXrayLibrary.query.filter_by(is_active=True).all()
    valid = []
    for r in rows:
      abs_path = r.absolute_image_path(root)
      if not os.path.isfile(abs_path):
        logger.debug("Skipping missing-on-disk reference id=%s path=%s", r.id, r.image_path)
        continue

      # Extra safety: exclude known placeholder/synthetic entries even if they exist in DB.
      blob = " ".join(
        str(x or "")
        for x in (
          getattr(r, "title", None),
          getattr(r, "anatomical_notes", None),
          getattr(r, "description", None),
          getattr(r, "source", None),
          getattr(r, "license", None),
          getattr(r, "public_id", None),
          getattr(r, "image_path", None),
        )
      ).lower()
      if any(m in blob for m in PLACEHOLDER_MARKERS):
        continue

      valid.append(r)
    return valid
