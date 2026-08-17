from app.extensions import db
from app.utils import utc_now


class Progress(db.Model):
  """Aggregated learning, quiz, and simulation progress per user."""

  __tablename__ = "progress"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  learning_progress = db.Column(db.Float, default=0.0)  # percentage 0-100
  quiz_scores = db.Column(db.JSON, nullable=True)  # {quiz_id: score}
  simulation_scores = db.Column(db.JSON, nullable=True)  # {simulation_id: score}
  achievements = db.Column(db.JSON, nullable=True)  # list of achievement badges
  weak_topics = db.Column(db.JSON, nullable=True)
  total_study_minutes = db.Column(db.Integer, default=0)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  user = db.relationship("User", back_populates="progress_records")

  __table_args__ = (db.UniqueConstraint("user_id", name="uq_progress_user"),)

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "learning_progress": self.learning_progress,
      "quiz_scores": self.quiz_scores or {},
      "simulation_scores": self.simulation_scores or {},
      "achievements": self.achievements or [],
      "weak_topics": self.weak_topics or [],
      "total_study_minutes": self.total_study_minutes,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
