"""Production Reference X-Ray Library — database model (Module 1).

Table: reference_xray_library

Stores metadata for healthy educational radiographs. Image bytes live on disk
under the configured library root; only relative paths are persisted here.
Never hardcode absolute paths in application code.
"""

from __future__ import annotations

import os

from app.extensions import db
from app.utils import utc_now


# ---------------------------------------------------------------------------
# Taxonomy (expandable without code changes to matching logic later)
# ---------------------------------------------------------------------------

REFERENCE_BODY_PARTS = (
  "Chest",
  "Hand",
  "Finger",
  "Wrist",
  "Elbow",
  "Shoulder",
  "Clavicle",
  "Spine",
  "Pelvis",
  "Hip",
  "Femur",
  "Knee",
  "Leg",
  "Ankle",
  "Foot",
  "Dental",
  "Skull",
  "Other",
)

REFERENCE_PROJECTIONS = (
  "AP",
  "PA",
  "Lateral",
  "Oblique",
  "Axial",
  "Skyline",
  "Other",
)

REFERENCE_AGE_GROUPS = (
  "Infant",
  "Child",
  "Teen",
  "Adult",
  "Older Adult",
)

REFERENCE_GENDERS = (
  "Male",
  "Female",
  "Unisex",
  "Unknown",
)

REFERENCE_ORIENTATIONS = (
  "Left",
  "Right",
  "Bilateral",
  "Unknown",
)

REFERENCE_DIFFICULTIES = (
  "Beginner",
  "Intermediate",
  "Advanced",
)

# Gender matching is clinically more relevant for these teaching references
REFERENCE_GENDER_RELEVANT_BODY_PARTS = (
  "Chest",
  "Pelvis",
  "Hip",
  "Spine",
  "Skull",
)


class ReferenceXrayLibrary(db.Model):
  """One healthy educational reference radiograph (scalable library row)."""

  __tablename__ = "reference_xray_library"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)

  title = db.Column(db.String(255), nullable=False)

  body_part = db.Column(db.String(50), nullable=False, index=True)
  projection = db.Column(db.String(30), nullable=False, default="Other", index=True)
  orientation = db.Column(db.String(20), nullable=False, default="Unknown", index=True)
  age_group = db.Column(db.String(30), nullable=False, default="Adult", index=True)
  gender = db.Column(db.String(20), nullable=False, default="Unisex", index=True)

  # Relative to library root — never store absolute machine paths as the source of truth
  image_path = db.Column(db.String(500), nullable=False, unique=True)
  thumbnail_path = db.Column(db.String(500), nullable=True)

  source = db.Column(db.String(255), nullable=True)
  license = db.Column(db.String(255), nullable=True)
  description = db.Column(db.Text, nullable=True)
  anatomical_notes = db.Column(db.Text, nullable=True)
  difficulty = db.Column(db.String(30), nullable=False, default="Beginner", index=True)

  is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
  uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

  created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

  # Operational metadata (production scale — not required for clinical matching)
  mime_type = db.Column(db.String(80), nullable=True)
  file_size = db.Column(db.Integer, nullable=True)
  width = db.Column(db.Integer, nullable=True)
  height = db.Column(db.Integer, nullable=True)
  content_hash = db.Column(db.String(64), nullable=True, index=True)
  public_id = db.Column(db.String(120), nullable=True, unique=True, index=True)

  uploader = db.relationship(
    "User",
    backref=db.backref("reference_xray_library_uploads", lazy="dynamic"),
  )

  __table_args__ = (
    db.Index(
      "ix_ref_xray_match",
      "body_part",
      "projection",
      "age_group",
      "orientation",
      "is_active",
    ),
  )

  def absolute_image_path(self, library_root: str) -> str:
    return os.path.normpath(
      os.path.join(library_root, (self.image_path or "").replace("\\", "/"))
    )

  def absolute_thumbnail_path(self, library_root: str) -> str | None:
    if not self.thumbnail_path:
      return None
    return os.path.normpath(
      os.path.join(library_root, self.thumbnail_path.replace("\\", "/"))
    )

  def gender_is_relevant(self) -> bool:
    return self.body_part in REFERENCE_GENDER_RELEVANT_BODY_PARTS

  def to_dict(self, *, library_root: str | None = None, include_paths: bool = False) -> dict:
    image_exists = False
    thumb_exists = False
    abs_image = None
    abs_thumb = None
    if library_root:
      abs_image = self.absolute_image_path(library_root)
      image_exists = os.path.isfile(abs_image)
      abs_thumb = self.absolute_thumbnail_path(library_root)
      thumb_exists = bool(abs_thumb and os.path.isfile(abs_thumb))

    payload = {
      "id": self.id,
      "public_id": self.public_id,
      "title": self.title,
      "body_part": self.body_part,
      "projection": self.projection,
      "orientation": self.orientation,
      "age_group": self.age_group,
      "gender": self.gender,
      "image_path": self.image_path,
      "thumbnail_path": self.thumbnail_path,
      "source": self.source or "",
      "license": self.license or "",
      "description": self.description or "",
      "anatomical_notes": self.anatomical_notes or "",
      "difficulty": self.difficulty,
      "is_active": bool(self.is_active),
      "uploaded_by": self.uploaded_by,
      "mime_type": self.mime_type,
      "file_size": self.file_size,
      "width": self.width,
      "height": self.height,
      "content_hash": self.content_hash,
      "image_exists": image_exists,
      "thumbnail_exists": thumb_exists,
      "gender_relevant": self.gender_is_relevant(),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "healthy_reference": True,
        "no_placeholder_images": True,
      },
    }
    if include_paths and abs_image:
      payload["absolute_image_path"] = abs_image
      if abs_thumb:
        payload["absolute_thumbnail_path"] = abs_thumb
    return payload


def reference_library_taxonomy() -> dict:
  """Enums for admin forms, validators, and matching (no hardcoded paths)."""
  return {
    "body_parts": list(REFERENCE_BODY_PARTS),
    "projections": list(REFERENCE_PROJECTIONS),
    "orientations": list(REFERENCE_ORIENTATIONS),
    "age_groups": list(REFERENCE_AGE_GROUPS),
    "genders": list(REFERENCE_GENDERS),
    "difficulties": list(REFERENCE_DIFFICULTIES),
    "gender_relevant_body_parts": list(REFERENCE_GENDER_RELEVANT_BODY_PARTS),
    "table": "reference_xray_library",
  }
