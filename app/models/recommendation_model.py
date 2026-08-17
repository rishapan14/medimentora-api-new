from app.extensions import db
from app.utils import utc_now


class Recommendation(db.Model):
  """Personalized course/topic recommendations for a user."""

  __tablename__ = "recommendations"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=True, index=True)
  weak_topic = db.Column(db.String(200), nullable=True)
  reason = db.Column(db.Text, nullable=True)
  priority = db.Column(db.Integer, default=1)
  is_read = db.Column(db.Boolean, default=False)
  created_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="recommendations")
  course = db.relationship("Course", back_populates="recommendations")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "course_id": self.course_id,
      "course": self.course.to_dict() if self.course else None,
      "weak_topic": self.weak_topic,
      "reason": self.reason,
      "priority": self.priority,
      "is_read": self.is_read,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
