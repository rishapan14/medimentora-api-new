"""Private quiz generation and scoring from source-grounded question banks."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from flask import current_app

from app.extensions import db
from app.models.book_model import Book
from app.models.course_model import CourseModule, CourseTopic
from app.models.quiz_model import Question, Quiz, Result
from app.services.learning_service import LearningService
from app.utils import utc_now

QUIZ_COUNTS = (5, 10, 20, 50)
QUIZ_DIFFICULTIES = ("easy", "medium", "hard", "mixed")
QUIZ_SCOPES = ("entire_course", "module", "topic", "weak_topics")
QUIZ_MODES = ("mcq", "mixed", "case_based", "exam_mode")


@dataclass(frozen=True)
class QuizGenerationResult:
  book: Book
  quiz: Quiz
  reused: bool
  requested_count: int
  available_count: int

  def to_dict(self):
    return {
      "book_id": self.book.id,
      "course_id": self.quiz.course_id,
      "quiz": self.quiz.to_dict(include_questions=True),
      "reused": self.reused,
      "requested_count": self.requested_count,
      "actual_count": self.quiz.questions.count(),
      "available_count": self.available_count,
      "limited_by_source": self.available_count < self.requested_count,
      "grounding": {
        "source_policy": "uploaded_document_only",
        "answers_hidden_until_submission": True,
        "note": "Every quiz item was selected from the private source-grounded question bank.",
      },
    }


class LearningQuizEngineService:
  @classmethod
  def generate_for_book(
    cls,
    book_id: int,
    user_id: int,
    *,
    question_count: int = 10,
    difficulty: str = "mixed",
    scope_type: str = "entire_course",
    scope_id: int | None = None,
    question_mode: str = "mixed",
    force: bool = False,
  ) -> QuizGenerationResult:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    course = book.generated_course
    if not course or course.question_generation_status != "ready":
      raise ValueError("Source-grounded questions must be ready before quiz generation.")

    requested = int(question_count)
    if requested not in QUIZ_COUNTS:
      raise ValueError("Question count must be 5, 10, 20, or 50.")
    difficulty_key = str(difficulty or "mixed").strip().lower()
    scope_key = str(scope_type or "entire_course").strip().lower()
    mode_key = str(question_mode or "mixed").strip().lower()
    if difficulty_key not in QUIZ_DIFFICULTIES:
      raise ValueError("Difficulty must be easy, medium, hard, or mixed.")
    if scope_key not in QUIZ_SCOPES:
      raise ValueError("Scope must be entire_course, module, topic, or weak_topics.")
    if mode_key not in QUIZ_MODES:
      raise ValueError("Question mode must be mcq, mixed, case_based, or exam_mode.")
    normalized_scope_id = cls._validate_scope(course.id, scope_key, scope_id)

    bank = Quiz.query.filter_by(source_book_id=book.id, quiz_type="question_bank").first()
    if not bank:
      raise ValueError("Source-grounded questions have not been generated yet.")
    candidates = cls._candidate_query(
      bank.id,
      user_id,
      book.id,
      difficulty_key,
      scope_key,
      normalized_scope_id,
      mode_key,
    ).all()
    if scope_key == "weak_topics":
      weak_ids = cls._weak_topic_ids(book.id, user_id)
      if not weak_ids:
        raise ValueError("Complete at least one quiz before using weak-topics scope.")
      candidates = [item for item in candidates if item.topic_id in weak_ids]
    if not candidates:
      raise ValueError("No source-grounded questions match these quiz settings.")

    signature = cls._signature(book, bank, requested, difficulty_key, scope_key, normalized_scope_id, mode_key)
    cached = Quiz.query.filter_by(
      source_book_id=book.id,
      owner_user_id=user_id,
      quiz_type="generated_learning",
      generation_hash=signature,
    ).order_by(Quiz.id.desc()).first()
    if cached and cached.questions.count() and not force:
      return QuizGenerationResult(book, cached, True, requested, len(candidates))

    selected = cls._balanced_selection(candidates, requested)
    course.quiz_generation_status = "generating"
    db.session.flush()
    try:
      scope_label = cls._scope_label(course, scope_key, normalized_scope_id)
      minutes_per_question = float(current_app.config.get("TEACHER_QUIZ_MINUTES_PER_QUESTION", 1.5))
      quiz = Quiz(
        title=f"{course.title} - {scope_label} Quiz"[:200],
        description="Private assessment generated only from your uploaded course material.",
        difficulty=difficulty_key,
        speciality=course.speciality,
        time_limit_minutes=max(5, int(math.ceil(len(selected) * minutes_per_question))),
        is_published=False,
        quiz_type="generated_learning",
        course_id=course.id,
        source_book_id=book.id,
        source_question_bank_id=bank.id,
        owner_user_id=user_id,
        scope_type=scope_key,
        scope_id=normalized_scope_id,
        question_mode=mode_key,
        requested_question_count=requested,
        generation_hash=signature,
        generated_at=utc_now(),
        passing_score=70,
        created_by=user_id,
      )
      db.session.add(quiz)
      db.session.flush()
      for index, source in enumerate(selected):
        db.session.add(
          Question(
            quiz_id=quiz.id,
            question_text=source.question_text,
            question_type=source.question_type,
            options=list(source.options or []),
            correct_answer=source.correct_answer,
            explanation=source.explanation,
            image_url=source.image_url,
            points=source.points,
            order_index=index,
            user_id=user_id,
            book_id=book.id,
            course_id=course.id,
            module_id=source.module_id,
            topic_id=source.topic_id,
            lesson_id=source.lesson_id,
            difficulty=source.difficulty,
            priority_level=source.priority_level,
            priority_score=source.priority_score,
            priority_reason=source.priority_reason,
            learning_objective=source.learning_objective,
            source_json=source.source_json,
            source_hash=source.source_hash,
            origin="uploaded_document",
            generation_method="question_bank_selection",
            generated_at=utc_now(),
          )
        )
      course.quiz_generation_status = "ready"
      db.session.commit()
      return QuizGenerationResult(book, quiz, False, requested, len(candidates))
    except Exception:
      db.session.rollback()
      failed = book.generated_course
      if failed:
        failed.quiz_generation_status = "failed"
        db.session.commit()
      raise

  @staticmethod
  def list_owned(book_id: int, user_id: int) -> list[Quiz]:
    if not Book.query.filter_by(id=book_id, user_id=user_id).first():
      raise LookupError("Book not found.")
    return (
      Quiz.query.filter_by(source_book_id=book_id, owner_user_id=user_id, quiz_type="generated_learning")
      .order_by(Quiz.created_at.desc(), Quiz.id.desc())
      .all()
    )

  @staticmethod
  def get_owned(book_id: int, user_id: int, quiz_id: int) -> Quiz:
    quiz = Quiz.query.filter_by(
      id=quiz_id,
      source_book_id=book_id,
      owner_user_id=user_id,
      quiz_type="generated_learning",
    ).first()
    if not quiz:
      raise LookupError("Generated quiz not found.")
    return quiz

  @classmethod
  def submit(cls, book_id: int, user_id: int, quiz_id: int, answers: dict, time_taken_seconds: int = 0) -> dict:
    quiz = cls.get_owned(book_id, user_id, quiz_id)
    if not isinstance(answers, dict):
      raise ValueError("answers must be an object keyed by question id.")
    questions = quiz.questions.order_by(Question.order_index, Question.id).all()
    if not questions:
      raise ValueError("Quiz has no questions.")
    earned = 0
    total_points = sum(int(item.points or 1) for item in questions)
    correct_count = 0
    review = []
    topic_totals: dict[int | None, dict] = {}
    for question in questions:
      selected = answers.get(str(question.id), answers.get(question.id))
      correct = cls._normalize(selected) == cls._normalize(question.correct_answer) if selected is not None else False
      if correct:
        earned += int(question.points or 1)
        correct_count += 1
      bucket = topic_totals.setdefault(question.topic_id, {"answered": 0, "correct": 0})
      bucket["answered"] += 1
      bucket["correct"] += int(correct)
      review.append({
        "question_id": question.id,
        "selected": selected,
        "correct_answer": question.correct_answer,
        "is_correct": correct,
        "explanation": question.explanation,
        "source": question.source_json,
        "topic_id": question.topic_id,
      })
    score = round((earned / total_points) * 100, 2) if total_points else 0
    topic_ids = [key for key in topic_totals if key is not None]
    topic_titles = {
      item.id: item.title for item in CourseTopic.query.filter(CourseTopic.id.in_(topic_ids)).all()
    } if topic_ids else {}
    breakdown = [
      {
        "topic_id": topic_id,
        "topic_title": topic_titles.get(topic_id, "Course overview"),
        "answered": values["answered"],
        "correct": values["correct"],
        "accuracy": round(values["correct"] / values["answered"] * 100, 2),
        "level": "strong" if values["correct"] / values["answered"] >= 0.8 else "needs_practice" if values["correct"] / values["answered"] >= 0.6 else "weak",
      }
      for topic_id, values in topic_totals.items()
    ]
    attempt_number = Result.query.filter_by(user_id=user_id, quiz_id=quiz.id).count() + 1
    result = Result(
      user_id=user_id,
      quiz_id=quiz.id,
      score=score,
      total_questions=len(questions),
      correct_answers=correct_count,
      answers={str(key): value for key, value in answers.items()},
      passed=score >= float(quiz.passing_score or 70),
      attempt_number=attempt_number,
      book_id=book_id,
      course_id=quiz.course_id,
      time_taken_seconds=max(0, min(int(time_taken_seconds or 0), 86400)),
      topic_breakdown_json=breakdown,
      review_json=review,
      quiz_mode=quiz.question_mode,
    )
    db.session.add(result)
    db.session.commit()
    LearningService.record_quiz_score(user_id, quiz.id, score)
    try:
      from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
      AdaptiveLearningService.refresh_book(book_id, user_id)
    except Exception:
      current_app.logger.exception("Adaptive topic mastery refresh failed after quiz submission.")
    try:
      from app.services.learning_dashboard_service import LearningDashboardService
      LearningDashboardService.record_activity(
        user_id,
        "quiz_attempt",
        str(result.id),
        f"Quiz: {quiz.title}",
        book_id=book_id,
        course_id=quiz.course_id,
        duration_minutes=math.ceil(result.time_taken_seconds / 60) if result.time_taken_seconds else 0,
        score=score,
        occurred_at=result.completed_at,
      )
    except Exception:
      current_app.logger.exception("Learning activity recording failed after quiz submission.")
    return {
      "result": result.to_dict(),
      "validated_answers": {
        str(item["question_id"]): {
          "selected": item["selected"],
          "correct": item["correct_answer"],
          "is_correct": item["is_correct"],
          "explanation": item["explanation"],
          "source": item["source"],
        }
        for item in review
      },
      "topic_breakdown": breakdown,
    }

  @staticmethod
  def list_attempts(book_id: int, user_id: int) -> list[Result]:
    if not Book.query.filter_by(id=book_id, user_id=user_id).first():
      raise LookupError("Book not found.")
    return Result.query.filter_by(book_id=book_id, user_id=user_id).order_by(Result.completed_at.desc()).all()

  @staticmethod
  def _candidate_query(bank_id, user_id, book_id, difficulty, scope, scope_id, mode):
    query = Question.query.filter_by(quiz_id=bank_id, user_id=user_id, book_id=book_id)
    if difficulty != "mixed":
      query = query.filter_by(difficulty=difficulty)
    if scope == "module":
      query = query.filter_by(module_id=scope_id)
    elif scope == "topic":
      query = query.filter_by(topic_id=scope_id)
    if mode == "mcq":
      query = query.filter_by(question_type="multiple_choice")
    elif mode == "case_based":
      query = query.filter_by(question_type="case_based")
    elif mode == "exam_mode":
      query = query.filter(Question.priority_level.in_(("high", "important")))
    return query.order_by(Question.priority_score.desc(), Question.order_index, Question.id)

  @staticmethod
  def _balanced_selection(candidates: list[Question], count: int) -> list[Question]:
    selected = []
    remaining = list(candidates)
    while remaining and len(selected) < count:
      seen_topics = set()
      next_remaining = []
      for question in remaining:
        key = question.topic_id or question.lesson_id or question.id
        if key not in seen_topics and len(selected) < count:
          selected.append(question)
          seen_topics.add(key)
        else:
          next_remaining.append(question)
      remaining = next_remaining
    return selected

  @staticmethod
  def _validate_scope(course_id: int, scope: str, scope_id: int | None) -> int | None:
    if scope in ("entire_course", "weak_topics"):
      return None
    if scope_id is None:
      raise ValueError(f"scope_id is required for {scope} scope.")
    model = CourseModule if scope == "module" else CourseTopic
    if not model.query.filter_by(id=int(scope_id), course_id=course_id).first():
      raise ValueError("The selected quiz scope does not belong to this course.")
    return int(scope_id)

  @staticmethod
  def _scope_label(course, scope: str, scope_id: int | None) -> str:
    if scope == "module":
      item = db.session.get(CourseModule, scope_id)
      return item.title if item else "Module"
    if scope == "topic":
      item = db.session.get(CourseTopic, scope_id)
      return item.title if item else "Topic"
    if scope == "weak_topics":
      return "Weak Topics"
    return "Entire Course"

  @staticmethod
  def _weak_topic_ids(book_id: int, user_id: int) -> set[int]:
    from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
    return AdaptiveLearningService.weak_topic_ids(book_id, user_id)

  @staticmethod
  def _normalize(value) -> str:
    return " ".join(str(value or "").strip().casefold().split())

  @staticmethod
  def _signature(book, bank, count, difficulty, scope, scope_id, mode) -> str:
    rows = bank.questions.with_entities(Question.id, Question.source_hash).order_by(Question.id).all()
    payload = {
      "book_hash": book.content_hash,
      "bank": [(row.id, row.source_hash) for row in rows],
      "count": count,
      "difficulty": difficulty,
      "scope": scope,
      "scope_id": scope_id,
      "mode": mode,
      "version": "phase9-v1",
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
