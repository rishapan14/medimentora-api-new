"""Owner-scoped learning activity events used for study time and streaks."""

from app.extensions import db
from app.utils import utc_now


class LearningActivity(db.Model):
  __tablename__ = "learning_activities"
  __table_args__ = (
    db.UniqueConstraint("user_id", "activity_type", "source_id", name="uq_learning_activity_source"),
    db.Index("ix_learning_activity_user_occurred", "user_id", "occurred_at"),
    db.Index("ix_learning_activity_user_course_occurred", "user_id", "course_id", "occurred_at"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
  module_id = db.Column(db.Integer, db.ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True)
  topic_id = db.Column(db.Integer, db.ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  activity_type = db.Column(db.String(40), nullable=False, index=True)
  source_id = db.Column(db.String(100), nullable=False)
  title = db.Column(db.String(240), nullable=False)
  duration_minutes = db.Column(db.Integer, nullable=False, default=0)
  score = db.Column(db.Float, nullable=True)
  metadata_json = db.Column(db.JSON, nullable=True)
  occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  course = db.relationship("Course")
  lesson = db.relationship("Lesson")
  topic = db.relationship("CourseTopic")

  def to_dict(self):
    return {
      "id": self.id,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "course_title": self.course.title if self.course else None,
      "module_id": self.module_id,
      "topic_id": self.topic_id,
      "topic_title": self.topic.title if self.topic else None,
      "lesson_id": self.lesson_id,
      "lesson_title": self.lesson.title if self.lesson else None,
      "activity_type": self.activity_type,
      "title": self.title,
      "duration_minutes": int(self.duration_minutes or 0),
      "score": round(float(self.score), 2) if self.score is not None else None,
      "metadata": self.metadata_json or {},
      "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
    }
