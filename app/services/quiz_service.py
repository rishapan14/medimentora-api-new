"""Quiz scoring and leaderboard logic."""

from sqlalchemy import func, or_

from app.extensions import db
from app.models.quiz_model import Question, Quiz, Result
from app.models.user_model import User


class QuizService:
  @staticmethod
  def calculate_result(quiz_id, answers):
    """
    Validate answers and calculate score.
    answers: dict {question_id (str|int): selected_answer}
    """
    questions = Question.query.filter_by(quiz_id=quiz_id).all()
    if not questions:
      raise ValueError("Quiz has no questions.")

    total_points = sum(q.points for q in questions)
    earned = 0
    correct_count = 0
    validated = {}

    for question in questions:
      key = str(question.id)
      selected = answers.get(key) or answers.get(question.id)
      qtype = (question.question_type or "multiple_choice").lower()
      if selected is None:
        is_correct = False
      elif qtype == "fill_in_blank":
        is_correct = str(selected).strip().casefold() == str(question.correct_answer).strip().casefold()
      else:
        is_correct = str(selected).strip() == str(question.correct_answer).strip()
      validated[key] = {
        "selected": selected,
        "correct": question.correct_answer,
        "is_correct": is_correct,
        "explanation": question.explanation,
      }
      if is_correct:
        earned += question.points
        correct_count += 1

    score = round((earned / total_points) * 100, 2) if total_points else 0
    return {
      "score": score,
      "total_questions": len(questions),
      "correct_answers": correct_count,
      "validated_answers": validated,
    }

  @staticmethod
  def get_leaderboard(quiz_id=None, limit=10):
    query = (
      db.session.query(
        User.id,
        User.full_name,
        User.email,
        func.max(Result.score).label("best_score"),
        func.count(Result.id).label("attempts"),
      )
      .join(Result, Result.user_id == User.id)
      .join(Quiz, Quiz.id == Result.quiz_id)
      .filter(or_(Quiz.quiz_type.is_(None), Quiz.quiz_type != "generated_learning"))
      .group_by(User.id, User.full_name, User.email)
      .order_by(func.max(Result.score).desc())
    )
    if quiz_id:
      query = query.filter(Result.quiz_id == quiz_id)

    rows = query.limit(limit).all()
    return [
      {
        "user_id": row.id,
        "full_name": row.full_name,
        "email": row.email,
        "best_score": float(row.best_score),
        "attempts": row.attempts,
      }
      for row in rows
    ]
