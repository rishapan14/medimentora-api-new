"""Persisted, owner-scoped AI Tutor conversations for uploaded courses."""

from __future__ import annotations

import uuid

from app.extensions import db
from app.utils import utc_now


class TutorSession(db.Model):
  __tablename__ = "tutor_sessions"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  public_id = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
  user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  title = db.Column(db.String(200), nullable=False)
  mode = db.Column(db.String(40), nullable=False, default="beginner")
  language = db.Column(db.String(10), nullable=False, default="en")
  session_type = db.Column(db.String(30), nullable=False, default="tutor", index=True)
  topic_id = db.Column(db.Integer, db.ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True)
  difficulty = db.Column(db.String(20), nullable=True)
  current_step = db.Column(db.Integer, nullable=False, default=0)
  total_steps = db.Column(db.Integer, nullable=False, default=0)
  correct_answers = db.Column(db.Integer, nullable=False, default=0)
  incorrect_answers = db.Column(db.Integer, nullable=False, default=0)
  plan_json = db.Column(db.JSON, nullable=True)
  state_json = db.Column(db.JSON, nullable=True)
  status = db.Column(db.String(20), nullable=False, default="active", index=True)
  completed_at = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now, index=True)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, index=True)

  book = db.relationship("Book", back_populates="tutor_sessions")
  course = db.relationship("Course")
  lesson = db.relationship("Lesson")
  topic = db.relationship("CourseTopic")
  user = db.relationship("User")
  messages = db.relationship(
    "TutorMessage",
    back_populates="session",
    lazy="dynamic",
    cascade="all, delete-orphan",
    order_by="TutorMessage.created_at",
  )

  __table_args__ = (
    db.Index("ix_tutor_sessions_owner_book_updated", "user_id", "book_id", "updated_at"),
  )

  def to_dict(self, include_messages: bool = False):
    data = {
      "id": self.public_id,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "lesson_id": self.lesson_id,
      "title": self.title,
      "mode": self.mode,
      "language": self.language,
      "session_type": self.session_type or "tutor",
      "topic_id": self.topic_id,
      "difficulty": self.difficulty,
      "current_step": self.current_step or 0,
      "total_steps": self.total_steps or 0,
      "correct_answers": self.correct_answers or 0,
      "incorrect_answers": self.incorrect_answers or 0,
      "status": self.status,
      "completed_at": self.completed_at.isoformat() if self.completed_at else None,
      "message_count": self.messages.count(),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_messages:
      data["messages"] = [message.to_dict() for message in self.messages.order_by(TutorMessage.created_at, TutorMessage.id)]
    return data


class TutorMessage(db.Model):
  __tablename__ = "tutor_messages"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  public_id = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
  session_id = db.Column(
    db.Integer,
    db.ForeignKey("tutor_sessions.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  role = db.Column(db.String(20), nullable=False, index=True)
  content = db.Column(db.Text, nullable=False)
  mode = db.Column(db.String(40), nullable=True)
  language = db.Column(db.String(10), nullable=True)
  provider = db.Column(db.String(40), nullable=True)
  source_json = db.Column(db.JSON, nullable=True)
  metadata_json = db.Column(db.JSON, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now, index=True)

  session = db.relationship("TutorSession", back_populates="messages")

  __table_args__ = (
    db.CheckConstraint("role IN ('user', 'assistant')", name="ck_tutor_message_role"),
    db.Index("ix_tutor_messages_session_created", "session_id", "created_at"),
  )

  def to_dict(self):
    metadata = self.metadata_json or {}
    return {
      "id": self.public_id,
      "role": self.role,
      "content": self.content,
      "mode": self.mode,
      "language": self.language,
      "provider": self.provider,
      "sources": self.source_json or [],
      "supported": bool(metadata.get("supported", True)),
      "used_fallback": bool(metadata.get("used_fallback", False)),
      "follow_up_question": metadata.get("follow_up_question"),
      "safety": metadata.get("safety"),
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
