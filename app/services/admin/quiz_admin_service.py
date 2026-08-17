"""Admin Quiz Management (Module 8)."""

from __future__ import annotations

import logging
from typing import Any

from flask_jwt_extended import current_user
from sqlalchemy import func, or_

from app.extensions import db
from app.models.quiz_model import Question, Quiz, Result
from app.utils import utc_now
from app.validations.quiz_validation import validate_question, validate_quiz

logger = logging.getLogger(__name__)


class AdminQuizService:
  """CRUD for quizzes and questions in the Admin Panel."""

  @classmethod
  def stats(cls) -> dict[str, Any]:
    total = Quiz.query.count()
    published = Quiz.query.filter(
      or_(Quiz.is_published.is_(True), Quiz.is_published.is_(None))
    ).count()
    draft = total - published
    questions = Question.query.count()
    attempts = Result.query.count()

    by_difficulty: dict[str, int] = {}
    for diff, count in (
      db.session.query(Quiz.difficulty, func.count(Quiz.id)).group_by(Quiz.difficulty).all()
    ):
      by_difficulty[str(diff or "medium")] = int(count)

    return {
      "quizzes": total,
      "published_quizzes": published,
      "draft_quizzes": draft,
      "questions": questions,
      "attempts": attempts,
      "by_difficulty": by_difficulty,
    }

  @classmethod
  def list_quizzes(
    cls,
    *,
    q: str | None = None,
    difficulty: str | None = None,
    speciality: str | None = None,
    published: bool | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = Quiz.query

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        or_(
          Quiz.title.ilike(like),
          Quiz.description.ilike(like),
          Quiz.speciality.ilike(like),
        )
      )

    if difficulty:
      query = query.filter(Quiz.difficulty == difficulty.strip().lower())

    if speciality:
      query = query.filter(Quiz.speciality.ilike(f"%{speciality.strip()}%"))

    if published is True:
      query = query.filter(or_(Quiz.is_published.is_(True), Quiz.is_published.is_(None)))
    elif published is False:
      query = query.filter(Quiz.is_published.is_(False))

    total = query.count()
    rows = (
      query.order_by(Quiz.updated_at.desc(), Quiz.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 200))
      .all()
    )

    return {
      "quizzes": [quiz.to_dict() for quiz in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "stats": cls.stats(),
    }

  @classmethod
  def get_quiz(cls, quiz_id: int) -> dict[str, Any] | None:
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
      return None
    payload = quiz.to_dict()
    payload["questions"] = [
      q.to_dict(include_answer=True) for q in quiz.questions.order_by(Question.order_index, Question.id)
    ]
    payload["attempt_count"] = quiz.results.count()
    return payload

  @classmethod
  def create_quiz(cls, data: dict[str, Any] | None) -> dict[str, Any]:
    errors = validate_quiz(data)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    try:
      from app.services.admin.settings_admin_service import AdminSettingsService

      creator_id = getattr(current_user, "id", None)
      quiz = Quiz(
        title=str(data["title"]).strip(),
        description=data.get("description"),
        difficulty=(data.get("difficulty") or "medium").lower(),
        speciality=data.get("speciality"),
        time_limit_minutes=int(
          data.get("time_limit_minutes")
          if data.get("time_limit_minutes") is not None
          else AdminSettingsService.get_int("default_quiz_time_limit_minutes", 30)
        ),
        is_published=bool(data.get("is_published", True)),
        quiz_type=data.get("quiz_type") or "general",
        course_id=data.get("course_id"),
        lesson_id=data.get("lesson_id"),
        passing_score=float(
          data.get("passing_score")
          if data.get("passing_score") is not None
          else AdminSettingsService.get_int("default_quiz_passing_score", 70)
        ),
        created_by=creator_id,
      )
      db.session.add(quiz)
      db.session.commit()
      return {
        "success": True,
        "message": "Quiz created.",
        "data": {"quiz": quiz.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin create quiz failed")
      return {
        "success": False,
        "message": "Could not create quiz.",
        "error_code": "create_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def update_quiz(cls, quiz_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
      return {"success": False, "message": "Quiz not found.", "error_code": "not_found"}

    errors = validate_quiz(data, partial=True)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    try:
      for field in (
        "title",
        "description",
        "difficulty",
        "speciality",
        "time_limit_minutes",
        "is_published",
        "quiz_type",
        "course_id",
        "lesson_id",
        "passing_score",
      ):
        if field in data:
          value = data[field]
          if field == "title" and isinstance(value, str):
            value = value.strip()
          if field == "difficulty" and value:
            value = str(value).lower()
          setattr(quiz, field, value)
      quiz.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Quiz updated.",
        "data": {"quiz": quiz.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update quiz failed id=%s", quiz_id)
      return {
        "success": False,
        "message": "Could not update quiz.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def set_published(cls, quiz_id: int, *, published: bool) -> dict[str, Any]:
    return cls.update_quiz(quiz_id, {"is_published": bool(published)})

  @classmethod
  def delete_quiz(cls, quiz_id: int) -> dict[str, Any]:
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
      return {"success": False, "message": "Quiz not found.", "error_code": "not_found"}
    try:
      db.session.delete(quiz)
      db.session.commit()
      logger.info("Admin deleted quiz id=%s", quiz_id)
      return {"success": True, "message": "Quiz deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete quiz failed id=%s", quiz_id)
      return {
        "success": False,
        "message": "Could not delete quiz.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def list_questions(cls, quiz_id: int) -> dict[str, Any]:
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
      return {"success": False, "message": "Quiz not found.", "error_code": "not_found"}
    questions = (
      Question.query.filter_by(quiz_id=quiz_id)
      .order_by(Question.order_index, Question.id)
      .all()
    )
    return {
      "success": True,
      "data": {
        "quiz_id": quiz_id,
        "questions": [q.to_dict(include_answer=True) for q in questions],
        "total": len(questions),
      },
    }

  @classmethod
  def create_question(cls, quiz_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    quiz = db.session.get(Quiz, quiz_id)
    if not quiz:
      return {"success": False, "message": "Quiz not found.", "error_code": "not_found"}

    payload = dict(data or {})
    payload["quiz_id"] = quiz_id
    errors = validate_question(payload)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    options = payload["options"]
    correct = str(payload["correct_answer"]).strip()
    if correct not in [str(o).strip() for o in options]:
      return {
        "success": False,
        "message": "correct_answer must match one of the options.",
        "error_code": "validation_error",
        "data": {"errors": ["correct_answer must match one of the options."]},
      }

    try:
      order_index = payload.get("order_index")
      if order_index is None:
        max_order = (
          db.session.query(func.max(Question.order_index)).filter_by(quiz_id=quiz_id).scalar()
        )
        order_index = int(max_order or 0) + 1

      question = Question(
        quiz_id=quiz_id,
        question_text=str(payload["question_text"]).strip(),
        question_type=payload.get("question_type") or "multiple_choice",
        options=options,
        correct_answer=correct,
        explanation=payload.get("explanation"),
        image_url=payload.get("image_url"),
        points=int(payload.get("points") or 1),
        order_index=int(order_index),
      )
      db.session.add(question)
      quiz.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Question created.",
        "data": {"question": question.to_dict(include_answer=True)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin create question failed quiz=%s", quiz_id)
      return {
        "success": False,
        "message": "Could not create question.",
        "error_code": "create_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def update_question(cls, question_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    question = db.session.get(Question, question_id)
    if not question:
      return {"success": False, "message": "Question not found.", "error_code": "not_found"}

    errors = validate_question(data, partial=True)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    options = data.get("options", question.options) or []
    correct = data.get("correct_answer", question.correct_answer)
    if correct is not None and options:
      if str(correct).strip() not in [str(o).strip() for o in options]:
        return {
          "success": False,
          "message": "correct_answer must match one of the options.",
          "error_code": "validation_error",
          "data": {"errors": ["correct_answer must match one of the options."]},
        }

    try:
      for field in (
        "question_text",
        "question_type",
        "options",
        "correct_answer",
        "explanation",
        "image_url",
        "points",
        "order_index",
      ):
        if field in data:
          value = data[field]
          if field == "question_text" and isinstance(value, str):
            value = value.strip()
          if field == "correct_answer" and value is not None:
            value = str(value).strip()
          setattr(question, field, value)
      if question.quiz:
        question.quiz.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Question updated.",
        "data": {"question": question.to_dict(include_answer=True)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update question failed id=%s", question_id)
      return {
        "success": False,
        "message": "Could not update question.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def delete_question(cls, question_id: int) -> dict[str, Any]:
    question = db.session.get(Question, question_id)
    if not question:
      return {"success": False, "message": "Question not found.", "error_code": "not_found"}
    try:
      quiz = question.quiz
      db.session.delete(question)
      if quiz:
        quiz.updated_at = utc_now()
      db.session.commit()
      return {"success": True, "message": "Question deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete question failed id=%s", question_id)
      return {
        "success": False,
        "message": "Could not delete question.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }
