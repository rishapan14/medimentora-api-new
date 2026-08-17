from app.extensions import db
from app.utils import utc_now


class Quiz(db.Model):
  """Quiz for assessing medical knowledge (standalone or linked to course/lesson)."""

  __tablename__ = "quizzes"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  title = db.Column(db.String(200), nullable=False)
  description = db.Column(db.Text, nullable=True)
  difficulty = db.Column(db.String(20), default="medium")
  speciality = db.Column(db.String(100), nullable=True)
  time_limit_minutes = db.Column(db.Integer, default=30)
  is_published = db.Column(db.Boolean, default=True)
  quiz_type = db.Column(db.String(40), default="general")  # general | lesson | final_assessment
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="SET NULL"), nullable=True, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  source_book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
  source_question_bank_id = db.Column(db.Integer, db.ForeignKey("quizzes.id", ondelete="SET NULL"), nullable=True, index=True)
  owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
  scope_type = db.Column(db.String(30), nullable=True, index=True)
  scope_id = db.Column(db.Integer, nullable=True, index=True)
  question_mode = db.Column(db.String(30), nullable=True, index=True)
  requested_question_count = db.Column(db.Integer, nullable=True)
  generation_hash = db.Column(db.String(64), nullable=True, index=True)
  generated_at = db.Column(db.DateTime, nullable=True)
  passing_score = db.Column(db.Float, default=70)
  created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  creator = db.relationship("User", back_populates="quizzes_created", foreign_keys=[created_by])
  course = db.relationship("Course", back_populates="quizzes")
  lesson = db.relationship("Lesson", back_populates="quizzes")
  source_book = db.relationship("Book", back_populates="question_banks")
  questions = db.relationship("Question", back_populates="quiz", lazy="dynamic", cascade="all, delete-orphan")
  results = db.relationship("Result", back_populates="quiz", lazy="dynamic", cascade="all, delete-orphan")

  def to_dict(self, include_questions=False):
    data = {
      "id": self.id,
      "title": self.title,
      "description": self.description,
      "difficulty": self.difficulty,
      "speciality": self.speciality,
      "time_limit_minutes": self.time_limit_minutes,
      "is_published": self.is_published,
      "quiz_type": self.quiz_type or "general",
      "course_id": self.course_id,
      "lesson_id": self.lesson_id,
      "source_book_id": self.source_book_id,
      "source_question_bank_id": self.source_question_bank_id,
      "scope_type": self.scope_type,
      "scope_id": self.scope_id,
      "question_mode": self.question_mode,
      "requested_question_count": self.requested_question_count,
      "generated_at": self.generated_at.isoformat() if self.generated_at else None,
      "passing_score": self.passing_score if self.passing_score is not None else 70,
      "question_count": self.questions.count(),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_questions:
      data["questions"] = [q.to_dict(include_answer=False) for q in self.questions.order_by(Question.order_index)]
    return data


class Question(db.Model):
  """Individual quiz question."""

  __tablename__ = "questions"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False, index=True)
  question_text = db.Column(db.Text, nullable=False)
  question_type = db.Column(db.String(40), default="multiple_choice")
  # multiple_choice | true_false | image_based | case_based
  options = db.Column(db.JSON, nullable=False)  # list of option strings (legacy + primary)
  correct_answer = db.Column(db.String(500), nullable=False)
  explanation = db.Column(db.Text, nullable=True)
  image_url = db.Column(db.String(500), nullable=True)
  points = db.Column(db.Integer, default=1)
  order_index = db.Column(db.Integer, default=0)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
  module_id = db.Column(db.Integer, db.ForeignKey("course_modules.id", ondelete="SET NULL"), nullable=True, index=True)
  topic_id = db.Column(db.Integer, db.ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  difficulty = db.Column(db.String(20), nullable=True, index=True)
  priority_level = db.Column(db.String(20), nullable=True, index=True)
  priority_score = db.Column(db.Integer, nullable=True)
  priority_reason = db.Column(db.String(500), nullable=True)
  learning_objective = db.Column(db.String(500), nullable=True)
  source_json = db.Column(db.JSON, nullable=True)
  source_hash = db.Column(db.String(64), nullable=True, index=True)
  origin = db.Column(db.String(40), nullable=True, index=True)
  generation_method = db.Column(db.String(40), nullable=True)
  generated_at = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now)

  quiz = db.relationship("Quiz", back_populates="questions")
  answer_choices = db.relationship(
    "QuizAnswer",
    back_populates="question",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )

  def to_dict(self, include_answer=False):
    data = {
      "id": self.id,
      "quiz_id": self.quiz_id,
      "question_text": self.question_text,
      "question_type": self.question_type or "multiple_choice",
      "options": self.options or [],
      "image_url": self.image_url,
      "points": self.points,
      "order_index": self.order_index or 0,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "module_id": self.module_id,
      "topic_id": self.topic_id,
      "lesson_id": self.lesson_id,
      "difficulty": self.difficulty,
      "priority_level": self.priority_level,
      "priority_score": self.priority_score,
      "priority_reason": self.priority_reason,
      "learning_objective": self.learning_objective,
      "source": self.source_json,
      "origin": self.origin,
      "generation_method": self.generation_method,
      "answer_available": bool(self.correct_answer),
      "explanation": self.explanation if include_answer else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
    if include_answer:
      data["correct_answer"] = self.correct_answer
      data["answer_choices"] = [a.to_dict() for a in self.answer_choices.order_by(QuizAnswer.order_index)]
    return data


class QuizAnswer(db.Model):
  """Normalized answer choice for a quiz question (optional; options JSON still supported)."""

  __tablename__ = "quiz_answers"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False, index=True)
  answer_text = db.Column(db.String(500), nullable=False)
  is_correct = db.Column(db.Boolean, default=False)
  order_index = db.Column(db.Integer, default=0)
  created_at = db.Column(db.DateTime, default=utc_now)

  question = db.relationship("Question", back_populates="answer_choices")

  def to_dict(self):
    return {
      "id": self.id,
      "question_id": self.question_id,
      "answer_text": self.answer_text,
      "is_correct": self.is_correct,
      "order_index": self.order_index,
    }


class Result(db.Model):
  """Quiz attempt result for a user."""

  __tablename__ = "results"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  quiz_id = db.Column(db.Integer, db.ForeignKey("quizzes.id"), nullable=False, index=True)
  score = db.Column(db.Float, nullable=False, default=0)
  total_questions = db.Column(db.Integer, default=0)
  correct_answers = db.Column(db.Integer, default=0)
  answers = db.Column(db.JSON, nullable=True)  # {question_id: selected_answer}
  passed = db.Column(db.Boolean, nullable=True)
  attempt_number = db.Column(db.Integer, default=1)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
  time_taken_seconds = db.Column(db.Integer, nullable=True)
  topic_breakdown_json = db.Column(db.JSON, nullable=True)
  review_json = db.Column(db.JSON, nullable=True)
  quiz_mode = db.Column(db.String(30), nullable=True)
  completed_at = db.Column(db.DateTime, default=utc_now)

  user = db.relationship("User", back_populates="quiz_results")
  quiz = db.relationship("Quiz", back_populates="results")

  def to_dict(self):
    return {
      "id": self.id,
      "user_id": self.user_id,
      "quiz_id": self.quiz_id,
      "score": self.score,
      "total_questions": self.total_questions,
      "correct_answers": self.correct_answers,
      "answers": self.answers or {},
      "passed": self.passed,
      "attempt_number": self.attempt_number or 1,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "time_taken_seconds": self.time_taken_seconds or 0,
      "topic_breakdown": self.topic_breakdown_json or [],
      "review": self.review_json or [],
      "quiz_mode": self.quiz_mode,
      "quiz": self.quiz.to_dict() if self.quiz else None,
      "completed_at": self.completed_at.isoformat() if self.completed_at else None,
    }
