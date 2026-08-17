from app.extensions import db
from app.utils import utc_now


class Notification(db.Model):
  """User notification (reminders, certificates, etc.)."""

  __tablename__ = "notifications"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  notification_type = db.Column(db.String(50), nullable=False)
  title = db.Column(db.String(200), nullable=False)
  message = db.Column(db.Text, nullable=False)
  reference_id = db.Column(db.Integer, nullable=True)
  is_read = db.Column(db.Boolean, default=False)
  created_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="notifications")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "notification_type": self.notification_type,
      "title": self.title,
      "message": self.message,
      "reference_id": self.reference_id,
      "is_read": self.is_read,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
