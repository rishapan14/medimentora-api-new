"""Database-backed healthy X-ray reference images (educational comparison)."""

from __future__ import annotations

import os

from app.extensions import db
from app.utils import utc_now


class XrayReferenceImage(db.Model):
  """One healthy educational reference radiograph stored on disk + metadata in DB."""

  __tablename__ = "xray_reference_images"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  public_id = db.Column(db.String(120), nullable=False, unique=True, index=True)

  body_part = db.Column(db.String(50), nullable=False, index=True)
  projection = db.Column(db.String(30), nullable=False, default="Other", index=True)
  age_group = db.Column(db.String(20), nullable=False, default="Adult", index=True)
  gender = db.Column(db.String(20), nullable=False, default="Unisex", index=True)

  # Relative to XRAY_REFERENCE_LIBRARY_FOLDER — never hardcode absolute paths in callers
  relative_path = db.Column(db.String(500), nullable=False, unique=True)
  original_filename = db.Column(db.String(255), nullable=True)
  stored_filename = db.Column(db.String(255), nullable=True)
  mime_type = db.Column(db.String(80), nullable=True)
  file_size = db.Column(db.Integer, nullable=True)
  width = db.Column(db.Integer, nullable=True)
  height = db.Column(db.Integer, nullable=True)
  content_hash = db.Column(db.String(64), nullable=True, index=True)

  label = db.Column(db.String(255), nullable=True)
  notes = db.Column(db.Text, nullable=True)
  license = db.Column(db.String(255), nullable=True)
  source = db.Column(db.String(255), nullable=True)
  gender_relevant = db.Column(db.Boolean, default=False)

  is_active = db.Column(db.Boolean, default=True, index=True)
  uploaded_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)

  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  uploader = db.relationship("User", backref=db.backref("uploaded_xray_references", lazy="dynamic"))

  def absolute_path(self, library_root: str) -> str:
    return os.path.normpath(os.path.join(library_root, self.relative_path.replace("\\", "/")))

  def to_dict(self, *, library_root: str | None = None, include_path: bool = False) -> dict:
    exists = False
    abs_path = None
    if library_root:
      abs_path = self.absolute_path(library_root)
      exists = os.path.isfile(abs_path)

    payload = {
      "id": self.id,
      "public_id": self.public_id,
      "body_part": self.body_part,
      "projection": self.projection,
      "age_group": self.age_group,
      "gender": self.gender,
      "relative_path": self.relative_path,
      "original_filename": self.original_filename,
      "stored_filename": self.stored_filename,
      "mime_type": self.mime_type,
      "file_size": self.file_size,
      "width": self.width,
      "height": self.height,
      "content_hash": self.content_hash,
      "label": self.label or f"Healthy {self.body_part} {self.projection} reference",
      "notes": self.notes or "",
      "license": self.license or "",
      "source": self.source or "",
      "gender_relevant": bool(self.gender_relevant),
      "is_active": bool(self.is_active),
      "uploaded_by": self.uploaded_by,
      "exists": exists,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "healthy_reference": True,
      },
    }
    if include_path and abs_path:
      payload["path"] = abs_path
    return payload
