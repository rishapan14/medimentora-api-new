"""Evidence-backed personalized learning dashboard aggregation."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.extensions import db
from app.models.adaptive_learning_model import LearningTopicMastery
from app.models.body_system_model import HubFlashcardFavorite
from app.models.course_model import CompletedLesson, Course, CourseProgress, Lesson
from app.models.learning_activity_model import LearningActivity
from app.models.progress_model import Progress
from app.models.quiz_model import Result
from app.models.tutor_model import TutorMessage, TutorSession
from app.utils import utc_now


class LearningDashboardService:
  """Builds one dashboard snapshot from persisted, owner-scoped evidence."""

  @classmethod
  def record_activity(
    cls,
    user_id: int,
    activity_type: str,
    source_id: str,
    title: str,
    *,
    book_id: int | None = None,
    course_id: int | None = None,
    module_id: int | None = None,
    topic_id: int | None = None,
    lesson_id: int | None = None,
    duration_minutes: int = 0,
    score: float | None = None,
    metadata: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
  ) -> LearningActivity:
    kind = str(activity_type or "").strip().lower()[:40]
    source = str(source_id or "").strip()[:100]
    if not kind or not source:
      raise ValueError("Activity type and source id are required.")
    row = LearningActivity.query.filter_by(user_id=user_id, activity_type=kind, source_id=source).first()
    if row:
      return row
    row = LearningActivity(
      user_id=user_id,
      book_id=book_id,
      course_id=course_id,
      module_id=module_id,
      topic_id=topic_id,
      lesson_id=lesson_id,
      activity_type=kind,
      source_id=source,
      title=str(title or "Learning activity")[:240],
      duration_minutes=max(0, min(int(duration_minutes or 0), 1440)),
      score=score,
      metadata_json=metadata or {},
      occurred_at=occurred_at or utc_now(),
    )
    db.session.add(row)
    db.session.commit()
    return row

  @classmethod
  def dashboard(cls, user_id: int) -> dict[str, Any]:
    cls._sync_existing_activity(user_id)
    activities = LearningActivity.query.filter_by(user_id=user_id).order_by(
      LearningActivity.occurred_at.desc(), LearningActivity.id.desc()
    ).all()
    completed_rows = CompletedLesson.query.filter_by(user_id=user_id).order_by(
      CompletedLesson.completed_at.desc()
    ).all()
    completed_ids = {row.lesson_id for row in completed_rows}
    progress_rows = CourseProgress.query.filter_by(user_id=user_id).all()
    progress_by_course = {row.course_id: row for row in progress_rows}
    engaged_course_ids = set(progress_by_course)
    engaged_course_ids.update(
      row.lesson.course_id for row in completed_rows if row.lesson
    )
    owned_courses = Course.query.filter_by(owner_user_id=user_id).all()
    engaged_course_ids.update(course.id for course in owned_courses)
    courses = Course.query.filter(Course.id.in_(engaged_course_ids)).all() if engaged_course_ids else []
    course_rows = cls._course_rows(courses, progress_by_course, completed_ids, activities, user_id)
    current_course = course_rows[0] if course_rows else None

    results = Result.query.filter_by(user_id=user_id).order_by(Result.completed_at.desc()).all()
    quiz_performance = cls._quiz_performance(results)
    flashcards = cls._flashcard_progress(user_id)
    streak = cls._streak(activities)
    weekly = cls._weekly_activity(activities)
    mastery = LearningTopicMastery.query.filter_by(user_id=user_id).order_by(
      LearningTopicMastery.mastery_score, LearningTopicMastery.updated_at.desc()
    ).all()
    weak_topics = [
      row.to_dict() for row in mastery
      if row.level in {"weak", "needs_practice"} and row.evidence_count > 0
    ]
    today_plan = cls._today_plan(weak_topics, current_course, flashcards)
    recent_lessons = [
      {
        "lesson_id": row.lesson_id,
        "lesson_title": row.lesson.title if row.lesson else "Lesson",
        "course_id": row.lesson.course_id if row.lesson else None,
        "course_title": row.lesson.course.title if row.lesson and row.lesson.course else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
      }
      for row in completed_rows[:6]
    ]
    progress = Progress.query.filter_by(user_id=user_id).first()
    total_minutes = sum(int(row.duration_minutes or 0) for row in activities)
    completed_courses = sum(1 for row in course_rows if row["status"] == "completed")
    average_course_progress = round(
      sum(row["progress_percent"] for row in course_rows) / len(course_rows), 2
    ) if course_rows else 0

    return {
      "overview": {
        "courses": len(course_rows),
        "completed_courses": completed_courses,
        "average_course_progress": average_course_progress,
        "modules_completed": sum(row["modules_completed"] for row in course_rows),
        "topics_completed": sum(row["topics_completed"] for row in course_rows),
        "study_minutes": total_minutes,
        "study_hours": round(total_minutes / 60, 1),
        "current_streak": streak["current"],
        "best_streak": streak["best"],
        "last_studied_at": activities[0].occurred_at.isoformat() if activities else None,
      },
      "current_course": current_course,
      "courses": course_rows,
      "today_plan": today_plan,
      "quiz_performance": quiz_performance,
      "weak_topics": weak_topics[:8],
      "flashcards": flashcards,
      "weekly_activity": weekly,
      "recent_lessons": recent_lessons,
      "recent_activity": [row.to_dict() for row in activities[:10]],
      "achievements": cls._achievements(progress, quiz_performance, streak, completed_courses),
      "tracking": {
        "study_time_policy": "Recorded durations only; missing activity durations are not estimated.",
        "streak_policy": "A study day requires at least one persisted learning activity.",
        "sources": ["lesson_completion", "quiz_attempt", "flashcard_review", "teach_me", "ai_tutor"],
      },
      "generated_at": utc_now().isoformat(),
    }

  @staticmethod
  def _course_rows(
    courses: list[Course],
    progress_by_course: dict[int, CourseProgress],
    completed_ids: set[int],
    activities: list[LearningActivity],
    user_id: int,
  ) -> list[dict[str, Any]]:
    activity_by_course: dict[int, LearningActivity] = {}
    for activity in activities:
      if activity.course_id and activity.course_id not in activity_by_course:
        activity_by_course[activity.course_id] = activity
    rows = []
    for course in courses:
      lessons = course.lessons.order_by(Lesson.order_index, Lesson.id).all()
      course_completed = [lesson for lesson in lessons if lesson.id in completed_ids]
      total = len(lessons)
      percent = round(len(course_completed) / total * 100, 2) if total else 0
      progress = progress_by_course.get(course.id)
      modules = []
      modules_completed = 0
      for module in course.modules.all():
        module_lessons = module.lessons.all()
        completed_count = sum(1 for lesson in module_lessons if lesson.id in completed_ids)
        module_total = len(module_lessons)
        module_percent = round(completed_count / module_total * 100, 2) if module_total else 0
        if module_total and completed_count >= module_total:
          modules_completed += 1
        modules.append({
          "id": module.id,
          "title": module.title,
          "lessons_completed": completed_count,
          "lessons_total": module_total,
          "progress_percent": module_percent,
        })
      mastery_rows = LearningTopicMastery.query.filter_by(user_id=user_id, course_id=course.id).all()
      topics_completed = sum(1 for row in mastery_rows if row.level in {"strong", "mastered"})
      last_activity = activity_by_course.get(course.id)
      last_lesson_id = (
        last_activity.lesson_id if last_activity and last_activity.lesson_id
        else progress.last_lesson_id if progress else None
      )
      next_lesson = next((lesson for lesson in lessons if lesson.id not in completed_ids), None)
      status = "completed" if total and len(course_completed) >= total else "in_progress" if percent or last_activity else "enrolled"
      row = {
        "course_id": course.id,
        "book_id": course.source_book_id,
        "title": course.title,
        "category": course.category.name if course.category else course.speciality,
        "is_personal": course.owner_user_id is not None,
        "status": status,
        "progress_percent": percent,
        "lessons_completed": len(course_completed),
        "lessons_total": total,
        "modules_completed": modules_completed,
        "modules_total": len(modules),
        "topics_completed": topics_completed,
        "topics_total": len(mastery_rows),
        "study_minutes": sum(
          int(activity.duration_minutes or 0) for activity in activities if activity.course_id == course.id
        ),
        "last_lesson_id": last_lesson_id,
        "recommended_lesson_id": next_lesson.id if next_lesson else last_lesson_id,
        "recommended_lesson_title": next_lesson.title if next_lesson else None,
        "last_activity_at": last_activity.occurred_at.isoformat() if last_activity else (
          progress.updated_at.isoformat() if progress and progress.updated_at else None
        ),
        "module_progress": modules,
      }
      rows.append(row)
    return sorted(rows, key=lambda row: row["last_activity_at"] or "", reverse=True)

  @staticmethod
  def _quiz_performance(results: list[Result]) -> dict[str, Any]:
    attempts = len(results)
    answered = sum(int(row.total_questions or 0) for row in results)
    correct = sum(int(row.correct_answers or 0) for row in results)
    return {
      "attempts": attempts,
      "average_score": round(sum(float(row.score or 0) for row in results) / attempts, 2) if attempts else 0,
      "best_score": round(max((float(row.score or 0) for row in results), default=0), 2),
      "questions_answered": answered,
      "correct_answers": correct,
      "incorrect_answers": max(0, answered - correct),
      "recent": [{
        "id": row.id,
        "quiz_id": row.quiz_id,
        "quiz_title": row.quiz.title if row.quiz else "Quiz",
        "course_id": row.course_id,
        "score": round(float(row.score or 0), 2),
        "correct_answers": int(row.correct_answers or 0),
        "total_questions": int(row.total_questions or 0),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
      } for row in results[:6]],
    }

  @staticmethod
  def _flashcard_progress(user_id: int) -> dict[str, Any]:
    now = utc_now()
    reviews = HubFlashcardFavorite.query.filter_by(user_id=user_id).all()
    correct = sum(int(row.correct_count or 0) for row in reviews)
    incorrect = sum(int(row.incorrect_count or 0) for row in reviews)
    return {
      "cards_reviewed": len(reviews),
      "review_events": sum(int(row.review_count or 0) for row in reviews),
      "mastered": sum(1 for row in reviews if row.status == "mastered"),
      "due": sum(1 for row in reviews if row.status != "mastered" and (row.next_review_at is None or row.next_review_at <= now)),
      "correct": correct,
      "incorrect": incorrect,
      "accuracy": round(correct / (correct + incorrect) * 100, 2) if correct + incorrect else 0,
    }

  @staticmethod
  def _streak(activities: list[LearningActivity]) -> dict[str, int]:
    days = sorted({row.occurred_at.date() for row in activities if row.occurred_at}, reverse=True)
    if not days:
      return {"current": 0, "best": 0}
    today = utc_now().date()
    expected = today if today in days else today - timedelta(days=1)
    current = 0
    day_set = set(days)
    while expected in day_set:
      current += 1
      expected -= timedelta(days=1)
    best = 1
    running = 1
    ascending = sorted(days)
    for previous, current_day in zip(ascending, ascending[1:]):
      running = running + 1 if current_day == previous + timedelta(days=1) else 1
      best = max(best, running)
    return {"current": current, "best": best}

  @staticmethod
  def _weekly_activity(activities: list[LearningActivity]) -> list[dict[str, Any]]:
    today = utc_now().date()
    minutes: dict[date, int] = defaultdict(int)
    counts: dict[date, int] = defaultdict(int)
    for activity in activities:
      if activity.occurred_at:
        day = activity.occurred_at.date()
        minutes[day] += int(activity.duration_minutes or 0)
        counts[day] += 1
    return [{
      "date": (day := today - timedelta(days=offset)).isoformat(),
      "day": day.strftime("%a"),
      "minutes": minutes[day],
      "activities": counts[day],
    } for offset in range(6, -1, -1)]

  @staticmethod
  def _today_plan(
    weak_topics: list[dict[str, Any]],
    current_course: dict[str, Any] | None,
    flashcards: dict[str, Any],
  ) -> list[dict[str, Any]]:
    items = []
    for topic in weak_topics[:3]:
      recommendation = topic.get("recommendation") or {}
      items.append({
        "type": recommendation.get("action_type") or "guided_practice",
        "title": f"Review {topic['topic_title']}",
        "description": recommendation.get("message") or "Complete a focused review.",
        "course_id": topic["course_id"],
        "book_id": topic["book_id"],
        "lesson_id": topic.get("lesson_id"),
        "topic_id": topic["topic_id"],
        "priority": recommendation.get("priority", 2),
      })
    if current_course and len(items) < 4 and current_course.get("recommended_lesson_id"):
      items.append({
        "type": "continue_course",
        "title": current_course.get("recommended_lesson_title") or f"Continue {current_course['title']}",
        "description": f"Recommended next in {current_course['title']}.",
        "course_id": current_course["course_id"],
        "book_id": current_course.get("book_id"),
        "lesson_id": current_course["recommended_lesson_id"],
        "topic_id": None,
        "priority": 1,
      })
    if flashcards["due"] and len(items) < 5:
      items.append({
        "type": "flashcard_review",
        "title": f"Review {flashcards['due']} due flashcards",
        "description": "Keep spaced repetition on schedule.",
        "course_id": current_course["course_id"] if current_course else None,
        "book_id": current_course.get("book_id") if current_course else None,
        "lesson_id": None,
        "topic_id": None,
        "priority": 1,
      })
    return items[:5]

  @staticmethod
  def _achievements(
    progress: Progress | None,
    quiz: dict[str, Any],
    streak: dict[str, int],
    completed_courses: int,
  ) -> list[dict[str, Any]]:
    values = [{"id": str(item), "title": str(item).replace("_", " ").title()} for item in (progress.achievements or [])] if progress else []
    derived = []
    if streak["best"] >= 7:
      derived.append({"id": "seven_day_streak", "title": "7-day learning streak"})
    if quiz["best_score"] >= 90:
      derived.append({"id": "quiz_mastery", "title": "Quiz mastery"})
    if completed_courses:
      derived.append({"id": "course_finisher", "title": "Course finisher"})
    existing = {item["id"] for item in values}
    values.extend(item for item in derived if item["id"] not in existing)
    return values

  @classmethod
  def _sync_existing_activity(cls, user_id: int) -> None:
    existing = {
      (row.activity_type, row.source_id)
      for row in LearningActivity.query.filter_by(user_id=user_id).all()
    }
    pending: list[LearningActivity] = []

    for completion in CompletedLesson.query.filter_by(user_id=user_id).all():
      lesson = completion.lesson
      key = ("lesson_completed", str(completion.id))
      if not lesson or key in existing:
        continue
      pending.append(LearningActivity(
        user_id=user_id,
        book_id=lesson.course.source_book_id if lesson.course else None,
        course_id=lesson.course_id,
        module_id=lesson.module_id,
        topic_id=lesson.topic_id,
        lesson_id=lesson.id,
        activity_type=key[0],
        source_id=key[1],
        title=f"Completed {lesson.title}"[:240],
        duration_minutes=max(0, int(lesson.duration_minutes or 0)),
        occurred_at=completion.completed_at or utc_now(),
      ))
      existing.add(key)

    for result in Result.query.filter_by(user_id=user_id).all():
      key = ("quiz_attempt", str(result.id))
      if key in existing:
        continue
      duration = math.ceil(int(result.time_taken_seconds or 0) / 60) if result.time_taken_seconds else 0
      pending.append(LearningActivity(
        user_id=user_id,
        book_id=result.book_id,
        course_id=result.course_id,
        activity_type=key[0],
        source_id=key[1],
        title=f"Quiz: {result.quiz.title if result.quiz else 'Assessment'}"[:240],
        duration_minutes=duration,
        score=result.score,
        occurred_at=result.completed_at or utc_now(),
      ))
      existing.add(key)

    for favorite in HubFlashcardFavorite.query.filter_by(user_id=user_id).all():
      if not favorite.last_reviewed_at:
        continue
      key = ("flashcard_review", f"{favorite.id}:{favorite.review_count or 0}")
      if key in existing:
        continue
      card = favorite.flashcard
      pending.append(LearningActivity(
        user_id=user_id,
        book_id=card.book_id if card else None,
        course_id=card.course_id if card else None,
        module_id=card.module_id if card else None,
        topic_id=card.topic_id if card else None,
        lesson_id=card.lesson_id if card else None,
        activity_type=key[0],
        source_id=key[1],
        title=f"Reviewed flashcard: {card.front_text[:160] if card else 'Study card'}"[:240],
        duration_minutes=0,
        occurred_at=favorite.last_reviewed_at,
      ))
      existing.add(key)

    for message in TutorMessage.query.join(TutorSession).filter(
      TutorSession.user_id == user_id,
      TutorMessage.role == "assistant",
    ).all():
      session = message.session
      kind = "teach_me" if session.session_type == "teach_me" else "ai_tutor"
      key = (kind, str(message.id))
      if key in existing:
        continue
      pending.append(LearningActivity(
        user_id=user_id,
        book_id=session.book_id,
        course_id=session.course_id,
        topic_id=session.topic_id,
        lesson_id=session.lesson_id,
        activity_type=kind,
        source_id=key[1],
        title=(session.title or "Learning session")[:240],
        duration_minutes=0,
        occurred_at=message.created_at or utc_now(),
      ))
      existing.add(key)

    if pending:
      db.session.add_all(pending)
      db.session.commit()
