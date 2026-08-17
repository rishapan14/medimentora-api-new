"""Learning progress, weak topics, and recommendations."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from app.extensions import db
from app.models.course_model import CompletedLesson, Course, CourseProgress, Lesson
from app.models.progress_model import Progress
from app.models.quiz_model import Result
from app.models.recommendation_model import Recommendation
from app.utils import utc_now


class LearningService:
  @staticmethod
  def get_or_create_progress(user_id):
    progress = Progress.query.filter_by(user_id=user_id).first()
    if progress:
      return progress

    progress = Progress(user_id=user_id)
    db.session.add(progress)
    try:
      db.session.commit()
    except IntegrityError:
      db.session.rollback()
      progress = Progress.query.filter_by(user_id=user_id).first()
      if not progress:
        raise
    return progress

  @staticmethod
  def update_learning_progress(user_id, minutes_delta: int = 0):
    progress = LearningService.get_or_create_progress(user_id)
    total_lessons = Lesson.query.count()
    completed = CompletedLesson.query.filter_by(user_id=user_id).count()

    if total_lessons > 0:
      progress.learning_progress = round((completed / total_lessons) * 100, 2)
    else:
      progress.learning_progress = 0.0

    if minutes_delta and minutes_delta > 0:
      progress.total_study_minutes = (progress.total_study_minutes or 0) + int(minutes_delta)

    db.session.commit()
    return progress

  @staticmethod
  def enroll_course(user_id, course_id):
    """Create course enrollment/progress if missing."""
    course = Course.query.get(course_id)
    if not course:
      return None

    row = CourseProgress.query.filter_by(user_id=user_id, course_id=course_id).first()
    total = course.lessons.count()
    if row:
      row.lessons_total = total
      db.session.commit()
      return row

    row = CourseProgress(
      user_id=user_id,
      course_id=course_id,
      status="enrolled",
      progress_percent=0,
      lessons_completed=0,
      lessons_total=total,
      enrolled_at=utc_now(),
    )
    db.session.add(row)
    course.enrollment_count = (course.enrollment_count or 0) + 1
    db.session.commit()
    return row

  @staticmethod
  def update_course_progress(user_id, course_id, last_lesson_id=None, minutes_delta: int = 0):
    """Recalculate per-course progress after a lesson is completed."""
    course = Course.query.get(course_id)
    if not course:
      return None

    row = CourseProgress.query.filter_by(user_id=user_id, course_id=course_id).first()
    if not row:
      row = LearningService.enroll_course(user_id, course_id)

    lesson_ids = [lesson.id for lesson in course.lessons.all()]
    completed = (
      CompletedLesson.query.filter(
        CompletedLesson.user_id == user_id,
        CompletedLesson.lesson_id.in_(lesson_ids),
      ).count()
      if lesson_ids
      else 0
    )
    total = len(lesson_ids)
    percent = round((completed / total) * 100, 2) if total else 0.0

    row.lessons_completed = completed
    row.lessons_total = total
    row.progress_percent = percent
    row.status = "completed" if total and completed >= total else "in_progress"
    if last_lesson_id:
      row.last_lesson_id = last_lesson_id
    if minutes_delta and minutes_delta > 0:
      row.study_minutes = (row.study_minutes or 0) + int(minutes_delta)
    if row.status == "completed" and not row.completed_at:
      row.completed_at = utc_now()
    row.updated_at = utc_now()
    db.session.commit()
    return row

  @staticmethod
  def detect_weak_topics(user_id):
    """Identify weak topics from low quiz scores."""
    results = Result.query.filter_by(user_id=user_id).order_by(Result.completed_at.desc()).limit(20).all()
    weak = []
    for result in results:
      if result.score < 60 and result.quiz:
        weak.append({
          "quiz_id": result.quiz_id,
          "quiz_title": result.quiz.title,
          "score": result.score,
          "speciality": result.quiz.speciality,
        })

    progress = LearningService.get_or_create_progress(user_id)
    progress.weak_topics = weak
    db.session.commit()
    return weak

  @staticmethod
  def generate_recommendations(user_id):
    """Create course recommendations based on weak topics."""
    progress = LearningService.get_or_create_progress(user_id)
    weak_topics = progress.weak_topics or []
    if not weak_topics:
      weak_topics = LearningService.detect_weak_topics(user_id)
    created = []

    for item in weak_topics[:5]:
      if not isinstance(item, dict):
        continue
      speciality = item.get("speciality")
      course = None
      if speciality:
        course = Course.query.filter(
          or_(Course.is_published.is_(True), Course.is_published.is_(None)),
          Course.speciality.ilike(f"%{speciality}%"),
        ).first()
        if not course:
          # Alias short labels like Nursing → Nursing Fundamentals
          course = Course.query.filter(
            or_(Course.is_published.is_(True), Course.is_published.is_(None)),
            Course.speciality.ilike(f"%{str(speciality).split()[0]}%"),
          ).first()
      if not course:
        course = Course.query.filter(
          or_(Course.is_published.is_(True), Course.is_published.is_(None))
        ).first()
      if not course:
        continue

      existing = Recommendation.query.filter_by(
        user_id=user_id, course_id=course.id, weak_topic=item.get("quiz_title")
      ).first()
      if existing:
        continue

      rec = Recommendation(
        user_id=user_id,
        course_id=course.id,
        weak_topic=item.get("quiz_title"),
        reason=f"Low quiz score ({item.get('score')}%). Review {course.title}.",
        priority=1,
      )
      db.session.add(rec)
      created.append(rec)

    db.session.commit()
    return created

  @staticmethod
  def record_quiz_score(user_id, quiz_id, score):
    progress = LearningService.get_or_create_progress(user_id)
    scores = progress.quiz_scores or {}
    scores[str(quiz_id)] = score
    progress.quiz_scores = scores

    achievements = progress.achievements or []
    if score >= 90 and "quiz_master" not in achievements:
      achievements.append("quiz_master")
    if score == 100 and "perfect_score" not in achievements:
      achievements.append("perfect_score")
    progress.achievements = achievements

    db.session.commit()
    return progress

  @staticmethod
  def record_simulation_score(user_id, simulation_id, score):
    progress = LearningService.get_or_create_progress(user_id)
    scores = progress.simulation_scores or {}
    scores[str(simulation_id)] = score
    progress.simulation_scores = scores

    achievements = progress.achievements or []
    if score >= 80 and "simulation_expert" not in achievements:
      achievements.append("simulation_expert")
    progress.achievements = achievements

    db.session.commit()
    return progress
