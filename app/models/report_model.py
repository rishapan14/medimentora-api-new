from app.extensions import db
from app.utils import utc_now


class Report(db.Model):
  """Uploaded medical report (PDF or image) with OCR/analysis metadata for history."""

  __tablename__ = "reports"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  title = db.Column(db.String(200), nullable=False)
  file_path = db.Column(db.String(500), nullable=True)
  file_type = db.Column(db.String(20), nullable=False)  # pdf | image
  extracted_text = db.Column(db.Text, nullable=True)  # OCR text (ocr_text)
  status = db.Column(db.String(30), default="uploaded", index=True)
  # uploaded | processed | analyzed | failed | deleted
  batch_id = db.Column(db.String(64), nullable=True, index=True)
  original_filename = db.Column(db.String(255), nullable=True)
  stored_filename = db.Column(db.String(255), nullable=True)
  file_size = db.Column(db.Integer, nullable=True)
  report_type = db.Column(db.String(50), nullable=True, index=True)  # cbc | lipid | general | ...
  page_count = db.Column(db.Integer, nullable=True)
  ocr_confidence = db.Column(db.Float, nullable=True)
  analysis_confidence = db.Column(db.String(20), nullable=True)  # High | Medium | Low
  structured_json = db.Column(db.JSON, nullable=True)
  analysis_date = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now)  # upload_date
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  user = db.relationship("User", back_populates="reports")
  analyses = db.relationship(
    "ReportAnalysis",
    back_populates="report",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )

  def to_dict(self, include_text=False, include_structured=False):
    """Serialize report for API responses.

    Args:
      include_text: Include full OCR text (can be large).
      include_structured: Include structured_json payload.
    """
    import os

    payload = {
      "id": self.id,
      "user_id": self.user_id,
      "title": self.title,
      "file_path": self.file_path,
      "file_type": self.file_type,
      "status": self.status,
      "batch_id": self.batch_id,
      "original_filename": self.original_filename,
      "stored_filename": self.stored_filename
        or (os.path.basename(self.file_path) if self.file_path else None),
      "file_size": self.file_size,
      "report_type": self.report_type or "general",
      "page_count": self.page_count,
      "ocr_confidence": self.ocr_confidence,
      "analysis_confidence": self.analysis_confidence,
      "upload_date": self.created_at.isoformat() if self.created_at else None,
      "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_text:
      payload["ocr_text"] = self.extracted_text
      payload["extracted_text"] = self.extracted_text
    if include_structured:
      payload["structured_json"] = self.structured_json
    return payload

  def to_history_card(self, has_analysis=False):
    """Compact payload for history list cards."""
    import os

    return {
      "id": self.id,
      "title": self.title,
      "original_filename": self.original_filename
        or (os.path.basename(self.file_path) if self.file_path else self.title),
      "file_type": self.file_type,
      "file_size": self.file_size,
      "report_type": self.report_type or "general",
      "page_count": self.page_count,
      "ocr_confidence": self.ocr_confidence,
      "analysis_confidence": self.analysis_confidence,
      "status": self.status,
      "has_analysis": has_analysis,
      "upload_date": self.created_at.isoformat() if self.created_at else None,
      "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
