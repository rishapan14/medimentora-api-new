from app.extensions import db
from app.utils import utc_now


class ClinicalCase(db.Model):
  """Clinical case study for learning and practice."""

  __tablename__ = "clinical_cases"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  created_by = db.Column(
    db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
  )
  title = db.Column(db.String(200), nullable=False)
  disease = db.Column(db.String(200), nullable=False)
  symptoms = db.Column(db.JSON, nullable=True)
  diagnosis = db.Column(db.Text, nullable=True)
  treatment = db.Column(db.Text, nullable=True)
  difficulty = db.Column(db.String(20), default="medium")
  speciality = db.Column(db.String(100), nullable=True)
  description = db.Column(db.Text, nullable=True)
  # Phase 9 — structured educational case walkthrough (patient → learning points)
  content_json = db.Column(db.JSON, nullable=True)
  is_published = db.Column(db.Boolean, default=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  creator = db.relationship("User", back_populates="clinical_cases")
  favorites = db.relationship("CaseFavorite", back_populates="case", lazy="dynamic", cascade="all, delete-orphan")

  def to_dict(self):
    content = self.content_json if isinstance(self.content_json, dict) else {}
    return {
      "id": self.id,
      "created_by": self.created_by,
      "title": self.title,
      "disease": self.disease,
      "symptoms": self.symptoms or [],
      "diagnosis": self.diagnosis,
      "treatment": self.treatment,
      "difficulty": self.difficulty,
      "speciality": self.speciality,
      "description": self.description,
      "content_json": content,
      "sections": {
        "patient": content.get("patient"),
        "history": content.get("history"),
        "symptoms": content.get("symptoms") or self.symptoms or [],
        "vitals": content.get("vitals") or {},
        "lab_reports": content.get("lab_reports") or [],
        "xray": content.get("xray"),
        "questions": content.get("questions") or [],
        "ai_explanation": content.get("ai_explanation"),
        "correct_answer": content.get("correct_answer") or self.diagnosis,
        "learning_points": content.get("learning_points") or [],
      },
      "is_published": self.is_published,
      "favorite_count": self.favorites.count(),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Clinical cases are educational simulations only.",
      },
    }


class CaseFavorite(db.Model):
  """User favorites for clinical cases."""

  __tablename__ = "case_favorites"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  case_id = db.Column(db.Integer, db.ForeignKey("clinical_cases.id"), nullable=False, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="case_favorites")
  case = db.relationship("ClinicalCase", back_populates="favorites")

  __table_args__ = (db.UniqueConstraint("user_id", "case_id", name="uq_user_case_favorite"),)

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "case_id": self.case_id,
      "case": self.case.to_dict() if self.case else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
