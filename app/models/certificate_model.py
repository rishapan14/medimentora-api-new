from app.extensions import db
from app.utils import utc_now


class Certificate(db.Model):
  """Course completion certificate."""

  __tablename__ = "certificates"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
  certificate_number = db.Column(db.String(100), nullable=False, unique=True)
  file_path = db.Column(db.String(500), nullable=True)
  issued_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="certificates")
  course = db.relationship("Course", back_populates="certificates")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "course_id": self.course_id,
      "certificate_number": self.certificate_number,
      "file_path": self.file_path,
      "course": self.course.to_dict() if self.course else None,
      "issued_at": self.issued_at.isoformat() if self.issued_at else None,
    }
