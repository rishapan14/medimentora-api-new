"""Platform settings model for Admin Panel preferences (Module 11)."""

from __future__ import annotations

from app.extensions import db
from app.utils import utc_now


class PlatformSetting(db.Model):
  """Key/value platform configuration row."""

  __tablename__ = "platform_settings"

  key = db.Column(db.String(100), primary_key=True)
  value = db.Column(db.JSON, nullable=True)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)
  updated_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

  def to_dict(self):
    return {
      "key": self.key,
      "value": self.value,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
      "updated_by": self.updated_by,
    }
