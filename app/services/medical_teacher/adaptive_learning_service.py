"""Multi-signal topic mastery and personalized revision recommendations."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from app.extensions import db
from app.models.adaptive_learning_model import LearningTopicMastery
from app.models.body_system_model import HubFlashcard, HubFlashcardFavorite
from app.models.book_model import Book
from app.models.course_model import CompletedLesson, CourseTopic, Lesson
from app.models.quiz_model import Result
from app.models.tutor_model import TutorSession
from app.utils import utc_now

MASTERY_LEVELS = ("mastered", "strong", "needs_practice", "weak")
MIN_RELIABLE_EVIDENCE = 4


class AdaptiveLearningService:
  """Aggregates repeatable evidence without labeling one mistake as weakness."""

  @classmethod
  def refresh_book(cls, book_id: int, user_id: int) -> dict[str, Any]:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    course = book.generated_course
    if not course:
      raise ValueError("Course has not been generated yet.")

    topics = course.topics.order_by(CourseTopic.order_index, CourseTopic.id).all()
    lessons_by_topic = {
      lesson.topic_id: lesson
      for lesson in Lesson.query.filter_by(course_id=course.id).filter(Lesson.topic_id.isnot(None)).all()
    }
    existing_rows = {
      row.topic_id: row
      for row in LearningTopicMastery.query.filter_by(
        user_id=user_id,
        book_id=book.id,
        course_id=course.id,
      ).all()
    }
    signals: dict[int, dict[str, Any]] = {
      topic.id: cls._empty_signals(topic) for topic in topics
    }
    cls._collect_quiz_signals(signals, book.id, user_id)
    cls._collect_flashcard_signals(signals, book.id, user_id)
    cls._collect_teach_me_signals(signals, book.id, user_id)
    cls._collect_lesson_signals(signals, course.id, user_id)

    active_topic_ids = {topic.id for topic in topics}
    if active_topic_ids:
      LearningTopicMastery.query.filter_by(user_id=user_id, book_id=book.id).filter(
        ~LearningTopicMastery.topic_id.in_(active_topic_ids)
      ).delete(synchronize_session=False)

    rows = []
    for topic in topics:
      values = signals[topic.id]
      score, level, confidence = cls._score(values)
      lesson = lessons_by_topic.get(topic.id)
      recommendation = cls._recommendation(topic, lesson.id if lesson else None, values, level, score)
      row = existing_rows.get(topic.id)
      if not row:
        row = LearningTopicMastery(
          user_id=user_id,
          book_id=book.id,
          course_id=course.id,
          topic_id=topic.id,
        )
        db.session.add(row)
      row.module_id = topic.module_id
      row.lesson_id = lesson.id if lesson else None
      row.level = level
      row.mastery_score = score
      row.confidence = confidence
      row.evidence_count = values["evidence_count"]
      row.quiz_attempts = values["quiz_attempts"]
      row.quiz_questions = values["quiz_questions"]
      row.quiz_correct = values["quiz_correct"]
      row.flashcard_reviews = values["flashcard_reviews"]
      row.flashcard_correct = values["flashcard_correct"]
      row.flashcard_incorrect = values["flashcard_incorrect"]
      row.flashcards_mastered = values["flashcards_mastered"]
      row.teach_me_answers = values["teach_me_answers"]
      row.teach_me_correct = values["teach_me_correct"]
      row.teach_me_incorrect = values["teach_me_incorrect"]
      row.lesson_completed = values["lesson_completed"]
      row.signals_json = cls._public_signals(values)
      row.recommendation_json = recommendation
      row.last_activity_at = values["last_activity_at"]
      row.updated_at = utc_now()
      rows.append(row)
    db.session.commit()
    return cls._snapshot(book, rows)

  @classmethod
  def get_snapshot(cls, book_id: int, user_id: int, *, refresh: bool = True) -> dict[str, Any]:
    if refresh:
      return cls.refresh_book(book_id, user_id)
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    if not book.generated_course:
      raise ValueError("Course has not been generated yet.")
    rows = LearningTopicMastery.query.filter_by(
      user_id=user_id,
      book_id=book.id,
      course_id=book.generated_course.id,
    ).order_by(LearningTopicMastery.mastery_score, LearningTopicMastery.topic_id).all()
    if not rows:
      return cls.refresh_book(book_id, user_id)
    return cls._snapshot(book, rows)

  @classmethod
  def weak_topic_ids(cls, book_id: int, user_id: int, *, refresh: bool = True) -> set[int]:
    snapshot = cls.get_snapshot(book_id, user_id, refresh=refresh)
    return {
      int(item["topic_id"])
      for item in snapshot["topics"]
      if item["level"] == "weak"
      or (
        item["level"] == "needs_practice"
        and item["evidence_count"] >= MIN_RELIABLE_EVIDENCE
        and item["mastery_score"] < 70
      )
    }

  @staticmethod
  def _empty_signals(topic: CourseTopic) -> dict[str, Any]:
    return {
      "topic_id": topic.id,
      "quiz_attempt_ids": set(),
      "quiz_attempts": 0,
      "quiz_questions": 0,
      "quiz_correct": 0,
      "flashcard_reviews": 0,
      "flashcard_correct": 0,
      "flashcard_incorrect": 0,
      "flashcards_mastered": 0,
      "teach_me_answers": 0,
      "teach_me_correct": 0,
      "teach_me_incorrect": 0,
      "lesson_completed": False,
      "evidence_count": 0,
      "last_activity_at": None,
    }

  @classmethod
  def _collect_quiz_signals(cls, signals: dict[int, dict], book_id: int, user_id: int) -> None:
    results = Result.query.filter_by(book_id=book_id, user_id=user_id).order_by(Result.completed_at).all()
    for result in results:
      for item in result.topic_breakdown_json or []:
        topic_id = cls._topic_id(item.get("topic_id"))
        if topic_id not in signals:
          continue
        values = signals[topic_id]
        values["quiz_attempt_ids"].add(result.id)
        values["quiz_questions"] += int(item.get("answered") or 0)
        values["quiz_correct"] += int(item.get("correct") or 0)
        values["last_activity_at"] = cls._latest(values["last_activity_at"], result.completed_at)
    for values in signals.values():
      values["quiz_attempts"] = len(values.pop("quiz_attempt_ids"))

  @classmethod
  def _collect_flashcard_signals(cls, signals: dict[int, dict], book_id: int, user_id: int) -> None:
    reviews = (
      HubFlashcardFavorite.query.join(HubFlashcard, HubFlashcard.id == HubFlashcardFavorite.flashcard_id)
      .filter(HubFlashcardFavorite.user_id == user_id, HubFlashcard.book_id == book_id)
      .all()
    )
    for review in reviews:
      card = review.flashcard
      if not card or card.topic_id not in signals:
        continue
      values = signals[int(card.topic_id)]
      values["flashcard_reviews"] += int(review.review_count or 0)
      values["flashcard_correct"] += int(review.correct_count or 0)
      values["flashcard_incorrect"] += int(review.incorrect_count or 0)
      values["flashcards_mastered"] += int(review.status == "mastered")
      values["last_activity_at"] = cls._latest(values["last_activity_at"], review.last_reviewed_at)

  @classmethod
  def _collect_teach_me_signals(cls, signals: dict[int, dict], book_id: int, user_id: int) -> None:
    sessions = TutorSession.query.filter_by(
      book_id=book_id,
      user_id=user_id,
      session_type="teach_me",
    ).filter(TutorSession.topic_id.isnot(None)).all()
    for session in sessions:
      if session.topic_id not in signals:
        continue
      values = signals[int(session.topic_id)]
      correct = int(session.correct_answers or 0)
      incorrect = int(session.incorrect_answers or 0)
      values["teach_me_correct"] += correct
      values["teach_me_incorrect"] += incorrect
      values["teach_me_answers"] += correct + incorrect
      values["last_activity_at"] = cls._latest(values["last_activity_at"], session.updated_at)

  @classmethod
  def _collect_lesson_signals(cls, signals: dict[int, dict], course_id: int, user_id: int) -> None:
    completions = (
      CompletedLesson.query.join(Lesson, Lesson.id == CompletedLesson.lesson_id)
      .filter(CompletedLesson.user_id == user_id, Lesson.course_id == course_id, Lesson.topic_id.isnot(None))
      .all()
    )
    for completion in completions:
      lesson = completion.lesson
      if not lesson or lesson.topic_id not in signals:
        continue
      values = signals[int(lesson.topic_id)]
      values["lesson_completed"] = True
      values["last_activity_at"] = cls._latest(values["last_activity_at"], completion.completed_at)

  @staticmethod
  def _score(values: dict[str, Any]) -> tuple[float, str, str]:
    components: list[tuple[float, float]] = []
    if values["quiz_questions"]:
      components.append((values["quiz_correct"] / values["quiz_questions"] * 100, 0.55))
    flash_answers = values["flashcard_correct"] + values["flashcard_incorrect"]
    if values["flashcard_reviews"] or flash_answers:
      flash_accuracy = values["flashcard_correct"] / max(1, flash_answers) * 100
      components.append((min(100, flash_accuracy + min(10, values["flashcards_mastered"] * 2)), 0.25))
    if values["teach_me_answers"]:
      components.append((values["teach_me_correct"] / values["teach_me_answers"] * 100, 0.15))
    components.append((100.0 if values["lesson_completed"] else 0.0, 0.05))
    weight = sum(item[1] for item in components)
    score = round(sum(value * item_weight for value, item_weight in components) / weight, 2) if weight else 0.0
    evidence = values["quiz_questions"] + values["flashcard_reviews"] + values["teach_me_answers"]
    values["evidence_count"] = evidence
    incorrect = (
      values["quiz_questions"] - values["quiz_correct"]
      + values["flashcard_incorrect"]
      + values["teach_me_incorrect"]
    )
    if evidence >= 8 and score >= 90 and values["lesson_completed"]:
      level = "mastered"
    elif evidence >= MIN_RELIABLE_EVIDENCE and score >= 75:
      level = "strong"
    elif evidence >= MIN_RELIABLE_EVIDENCE and incorrect >= 2 and score < 55:
      level = "weak"
    else:
      level = "needs_practice"
    confidence = "high" if evidence >= 10 else "medium" if evidence >= MIN_RELIABLE_EVIDENCE else "low"
    return score, level, confidence

  @staticmethod
  def _recommendation(
    topic: CourseTopic,
    lesson_id: int | None,
    values: dict[str, Any],
    level: str,
    score: float,
  ) -> dict[str, Any]:
    if values["evidence_count"] < MIN_RELIABLE_EVIDENCE:
      action = "Complete the lesson and answer several questions before mastery is assessed."
      action_type = "build_evidence"
    elif level == "weak":
      action = "Review the lesson, study its flashcards, then take a targeted retry quiz."
      action_type = "targeted_revision"
    elif level == "needs_practice":
      action = "Use the 5-minute lesson review and complete focused practice questions."
      action_type = "guided_practice"
    elif level == "strong":
      action = "Maintain progress with harder questions and spaced flashcard review."
      action_type = "challenge"
    else:
      action = "Maintain mastery with occasional spaced review."
      action_type = "maintenance"
    return {
      "action_type": action_type,
      "title": topic.title,
      "message": action,
      "priority": 3 if level == "weak" else 2 if level == "needs_practice" else 1,
      "mastery_score": score,
      "lesson_id": lesson_id,
      "educational_only": True,
    }

  @classmethod
  def _snapshot(cls, book: Book, rows: list[LearningTopicMastery]) -> dict[str, Any]:
    order = {"weak": 0, "needs_practice": 1, "strong": 2, "mastered": 3}
    topic_data = [row.to_dict() for row in sorted(rows, key=lambda row: (order.get(row.level, 9), row.mastery_score, row.topic_id))]
    summary = {level: 0 for level in MASTERY_LEVELS}
    for item in topic_data:
      summary[item["level"]] = summary.get(item["level"], 0) + 1
    summary["total_topics"] = len(topic_data)
    summary["evidence_count"] = sum(item["evidence_count"] for item in topic_data)
    focus = [item for item in topic_data if item["level"] in {"weak", "needs_practice"}]
    study_plan = [{
      "topic_id": item["topic_id"],
      "topic_title": item["topic_title"],
      "lesson_id": item["lesson_id"],
      "level": item["level"],
      **item["recommendation"],
    } for item in focus[:5]]
    return {
      "book_id": book.id,
      "course_id": book.generated_course.id,
      "summary": summary,
      "topics": topic_data,
      "weak_topics": [item for item in topic_data if item["level"] == "weak"],
      "study_plan": study_plan,
      "scoring": {
        "minimum_reliable_evidence": MIN_RELIABLE_EVIDENCE,
        "single_error_creates_weak_topic": False,
        "signals": ["quiz_accuracy", "flashcard_reviews", "teach_me_answers", "lesson_completion"],
        "note": "Levels use repeated course activity; one incorrect answer is never enough to label a topic weak.",
      },
      "generated_at": utc_now().isoformat(),
    }

  @staticmethod
  def _public_signals(values: dict[str, Any]) -> dict[str, Any]:
    quiz_accuracy = round(values["quiz_correct"] / values["quiz_questions"] * 100, 2) if values["quiz_questions"] else None
    flash_answers = values["flashcard_correct"] + values["flashcard_incorrect"]
    flash_accuracy = round(values["flashcard_correct"] / flash_answers * 100, 2) if flash_answers else None
    teach_accuracy = round(values["teach_me_correct"] / values["teach_me_answers"] * 100, 2) if values["teach_me_answers"] else None
    return {
      "quiz_accuracy": quiz_accuracy,
      "flashcard_accuracy": flash_accuracy,
      "teach_me_accuracy": teach_accuracy,
      "lesson_completed": values["lesson_completed"],
    }

  @staticmethod
  def _topic_id(value: Any) -> int | None:
    try:
      return int(value) if value is not None else None
    except (TypeError, ValueError):
      return None

  @staticmethod
  def _latest(current: datetime | None, candidate: datetime | None) -> datetime | None:
    if candidate is None:
      return current
    if current is None or candidate > current:
      return candidate
    return current
