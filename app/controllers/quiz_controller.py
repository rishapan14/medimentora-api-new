import logging

from flask import request
from flask_jwt_extended import current_user

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.quiz_model import Question, Quiz, Result
from app.services.learning_service import LearningService
from app.services.quiz_service import QuizService
from app.validations.quiz_validation import validate_question, validate_quiz, validate_quiz_submit


logger = logging.getLogger(__name__)


# --- Quiz CRUD ---

def list_quizzes():
  query = Quiz.query.filter_by(is_published=True)
  if request.args.get("speciality"):
    query = query.filter_by(speciality=request.args.get("speciality"))
  if request.args.get("difficulty"):
    query = query.filter_by(difficulty=request.args.get("difficulty"))
  quizzes = query.order_by(Quiz.created_at.desc()).all()
  return success_response("Quizzes retrieved.", {"quizzes": [q.to_dict() for q in quizzes]})


def get_quiz(quiz_id):
  quiz = Quiz.query.get(quiz_id)
  if not quiz or not quiz.is_published:
    return error_response("Quiz not found.", 404)
  return success_response("Quiz retrieved.", {"quiz": quiz.to_dict(include_questions=True)})


def create_quiz():
  from app.services.admin.settings_admin_service import AdminSettingsService

  data = request.get_json(silent=True)
  errors = validate_quiz(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  quiz = Quiz(
    title=data["title"],
    description=data.get("description"),
    difficulty=data.get("difficulty", "medium"),
    speciality=data.get("speciality"),
    time_limit_minutes=data.get(
      "time_limit_minutes",
      AdminSettingsService.get_int("default_quiz_time_limit_minutes", 30),
    ),
    passing_score=data.get(
      "passing_score",
      AdminSettingsService.get_int("default_quiz_passing_score", 70),
    ),
    created_by=current_user.id,
  )
  db.session.add(quiz)
  db.session.commit()
  return success_response("Quiz created.", {"quiz": quiz.to_dict()}, 201)


def update_quiz(quiz_id):
  quiz = Quiz.query.get(quiz_id)
  if not quiz:
    return error_response("Quiz not found.", 404)

  data = request.get_json(silent=True) or {}
  for field in ("title", "description", "difficulty", "speciality", "time_limit_minutes", "is_published"):
    if field in data:
      setattr(quiz, field, data[field])
  db.session.commit()
  return success_response("Quiz updated.", {"quiz": quiz.to_dict()})


def delete_quiz(quiz_id):
  quiz = Quiz.query.get(quiz_id)
  if not quiz:
    return error_response("Quiz not found.", 404)
  db.session.delete(quiz)
  db.session.commit()
  return success_response("Quiz deleted.")


# --- Question CRUD ---

def create_question(quiz_id):
  quiz = Quiz.query.get(quiz_id)
  if not quiz:
    return error_response("Quiz not found.", 404)

  data = request.get_json(silent=True) or {}
  data["quiz_id"] = quiz_id
  errors = validate_question(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  question = Question(
    quiz_id=quiz_id,
    question_text=data["question_text"],
    options=data["options"],
    correct_answer=data["correct_answer"],
    explanation=data.get("explanation"),
    points=data.get("points", 1),
  )
  db.session.add(question)
  db.session.commit()
  return success_response("Question created.", {"question": question.to_dict(include_answer=True)}, 201)


def update_question(question_id):
  question = Question.query.get(question_id)
  if not question:
    return error_response("Question not found.", 404)

  data = request.get_json(silent=True) or {}
  for field in ("question_text", "options", "correct_answer", "explanation", "points"):
    if field in data:
      setattr(question, field, data[field])
  db.session.commit()
  return success_response("Question updated.", {"question": question.to_dict(include_answer=True)})


def delete_question(question_id):
  question = Question.query.get(question_id)
  if not question:
    return error_response("Question not found.", 404)
  db.session.delete(question)
  db.session.commit()
  return success_response("Question deleted.")


# --- Submit & Results ---

def submit_quiz(quiz_id):
  quiz = Quiz.query.get(quiz_id)
  if not quiz or not quiz.is_published:
    return error_response("Quiz not found.", 404)

  data = request.get_json(silent=True)
  errors = validate_quiz_submit(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  try:
    calc = QuizService.calculate_result(quiz_id, data["answers"])
  except ValueError as exc:
    return error_response(str(exc), 400)

  passing = quiz.passing_score if quiz.passing_score is not None else 70
  attempt_number = Result.query.filter_by(user_id=current_user.id, quiz_id=quiz_id).count() + 1

  result = Result(
    user_id=current_user.id,
    quiz_id=quiz_id,
    score=calc["score"],
    total_questions=calc["total_questions"],
    correct_answers=calc["correct_answers"],
    answers=data["answers"],
    passed=calc["score"] >= passing,
    attempt_number=attempt_number,
    time_taken_seconds=data.get("time_taken_seconds"),
  )
  db.session.add(result)
  db.session.commit()
  result_payload = result.to_dict()

  try:
    LearningService.record_quiz_score(current_user.id, quiz_id, calc["score"])
  except Exception:
    db.session.rollback()
    logger.exception("Quiz progress tracking failed after result %s was saved", result.id)

  try:
    from app.services.body_systems.hub_quiz_service import HubQuizService

    HubQuizService.record_progress_for_quiz(current_user.id, int(quiz_id), float(calc["score"]))
  except Exception:
    db.session.rollback()
    pass

  return success_response("Quiz submitted.", {
    "result": result_payload,
    "validated_answers": calc["validated_answers"],
  }, 201)


def my_results():
  results = Result.query.filter_by(user_id=current_user.id).order_by(Result.completed_at.desc()).all()
  return success_response("Results retrieved.", {"results": [r.to_dict() for r in results]})


def leaderboard():
  quiz_id = request.args.get("quiz_id", type=int)
  limit = request.args.get("limit", 10, type=int)
  board = QuizService.get_leaderboard(quiz_id=quiz_id, limit=limit)
  return success_response("Leaderboard retrieved.", {"leaderboard": board})
