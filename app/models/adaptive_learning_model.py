"""Course-topic mastery snapshots built from multiple learning signals."""

from app.extensions import db
from app.utils import utc_now


class LearningTopicMastery(db.Model):
  __tablename__ = "learning_topic_mastery"
  __table_args__ = (
    db.UniqueConstraint("user_id", "course_id", "topic_id", name="uq_learning_topic_mastery_owner_topic"),
    db.Index("ix_learning_topic_mastery_owner_level", "user_id", "course_id", "level"),
  )

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
  module_id = db.Column(db.Integer, db.ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True)
  topic_id = db.Column(db.Integer, db.ForeignKey("course_topics.id", ondelete="CASCADE"), nullable=False, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  level = db.Column(db.String(30), nullable=False, default="needs_practice", index=True)
  mastery_score = db.Column(db.Float, nullable=False, default=0)
  confidence = db.Column(db.String(20), nullable=False, default="low")
  evidence_count = db.Column(db.Integer, nullable=False, default=0)
  quiz_attempts = db.Column(db.Integer, nullable=False, default=0)
  quiz_questions = db.Column(db.Integer, nullable=False, default=0)
  quiz_correct = db.Column(db.Integer, nullable=False, default=0)
  flashcard_reviews = db.Column(db.Integer, nullable=False, default=0)
  flashcard_correct = db.Column(db.Integer, nullable=False, default=0)
  flashcard_incorrect = db.Column(db.Integer, nullable=False, default=0)
  flashcards_mastered = db.Column(db.Integer, nullable=False, default=0)
  teach_me_answers = db.Column(db.Integer, nullable=False, default=0)
  teach_me_correct = db.Column(db.Integer, nullable=False, default=0)
  teach_me_incorrect = db.Column(db.Integer, nullable=False, default=0)
  lesson_completed = db.Column(db.Boolean, nullable=False, default=False)
  signals_json = db.Column(db.JSON, nullable=True)
  recommendation_json = db.Column(db.JSON, nullable=True)
  last_activity_at = db.Column(db.DateTime, nullable=True, index=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  topic = db.relationship("CourseTopic")
  lesson = db.relationship("Lesson")

  def to_dict(self):
    return {
      "id": self.id,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "module_id": self.module_id,
      "topic_id": self.topic_id,
      "topic_title": self.topic.title if self.topic else "Course topic",
      "lesson_id": self.lesson_id,
      "level": self.level or "needs_practice",
      "mastery_score": round(float(self.mastery_score or 0), 2),
      "confidence": self.confidence or "low",
      "evidence_count": int(self.evidence_count or 0),
      "quiz_attempts": int(self.quiz_attempts or 0),
      "quiz_questions": int(self.quiz_questions or 0),
      "quiz_correct": int(self.quiz_correct or 0),
      "flashcard_reviews": int(self.flashcard_reviews or 0),
      "flashcard_correct": int(self.flashcard_correct or 0),
      "flashcard_incorrect": int(self.flashcard_incorrect or 0),
      "flashcards_mastered": int(self.flashcards_mastered or 0),
      "teach_me_answers": int(self.teach_me_answers or 0),
      "teach_me_correct": int(self.teach_me_correct or 0),
      "teach_me_incorrect": int(self.teach_me_incorrect or 0),
      "lesson_completed": bool(self.lesson_completed),
      "signals": self.signals_json or {},
      "recommendation": self.recommendation_json or {},
      "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
