from flask import current_app, request
from flask_jwt_extended import current_user
from sqlalchemy import or_

from app.extensions import db
from app.helpers.response import error_response, success_response
from app.models.course_model import (
  CompletedLesson,
  Course,
  CourseCategory,
  CourseProgress,
  Lesson,
  LessonBookmark,
)
from app.models.recommendation_model import Recommendation
from app.services.learning_service import LearningService
from app.utils import utc_now
from app.validations.learning_validation import validate_course, validate_lesson


# --- Categories ---

def list_categories():
  """Return active LMS categories for filters/browse."""
  categories = (
    CourseCategory.query.filter_by(is_active=True)
    .order_by(CourseCategory.sort_order, CourseCategory.name)
    .all()
  )
  return success_response(
    "Categories retrieved.",
    {"categories": [c.to_dict() for c in categories], "total": len(categories)},
  )


# --- Courses ---

def _accessible_course(course_id: int) -> Course | None:
  return Course.query.filter(
    Course.id == course_id,
    or_(
      Course.owner_user_id == current_user.id,
      Course.is_published.is_(True),
      Course.is_published.is_(None),
    ),
  ).first()

def list_courses():
  speciality = (request.args.get("speciality") or request.args.get("category") or "").strip()
  difficulty = (request.args.get("difficulty") or "").strip()
  search = (request.args.get("search") or request.args.get("q") or "").strip()

  query = Course.query.filter(
    or_(
      Course.owner_user_id == current_user.id,
      Course.is_published.is_(True),
      Course.is_published.is_(None),
    )
  )

  if speciality:
    # UI chip labels → API/seeded category names
    tokens = {speciality}
    lower = speciality.lower()
    alias_map = {
      "nursing fundamentals": ["Nursing", "Nursing Fundamentals"],
      "nursing": ["Nursing Fundamentals", "Nursing"],
      "emergency care": ["Emergency Medicine", "Emergency Care", "Emergency"],
      "emergency medicine": ["Emergency Care", "Emergency Medicine", "Emergency"],
      "surgery": ["Surgical Nursing", "Surgery"],
      "surgical nursing": ["Surgery", "Surgical Nursing"],
      "infectious disease": ["Infection Control", "Infectious Disease"],
      "infection control": ["Infectious Disease", "Infection Control"],
    }
    for alias in alias_map.get(lower, []):
      tokens.add(alias)
    like_filters = []
    for token in tokens:
      like_filters.extend(
        [
          Course.speciality.ilike(token),
          CourseCategory.name.ilike(token),
          Course.speciality.ilike(f"%{token}%"),
          CourseCategory.name.ilike(f"%{token}%"),
        ]
      )
    query = query.outerjoin(CourseCategory, Course.category_id == CourseCategory.id).filter(
      or_(*like_filters)
    )

  if difficulty:
    # Map LMS labels to legacy values
    difficulty_map = {
      "beginner": ["beginner", "easy"],
      "intermediate": ["intermediate", "medium"],
      "advanced": ["advanced", "hard"],
      "easy": ["easy", "beginner"],
      "medium": ["medium", "intermediate"],
      "hard": ["hard", "advanced"],
    }
    allowed = difficulty_map.get(difficulty.lower(), [difficulty])
    query = query.filter(Course.difficulty.in_(allowed))

  if search:
    like = f"%{search}%"
    query = query.filter(
      or_(
        Course.title.ilike(like),
        Course.description.ilike(like),
        Course.speciality.ilike(like),
        Course.instructor_name.ilike(like),
      )
    )

  courses = query.order_by(Course.created_at.desc()).all()
  return success_response("Courses retrieved.", {"courses": [c.to_dict() for c in courses]})


def get_course(course_id):
  course = _accessible_course(course_id)
  if not course:
    return error_response("Course not found.", 404)
  payload = course.to_dict(include_lessons=True, include_modules=True)
  # Attach media for each lesson
  payload["lessons"] = [l.to_dict(include_media=True) for l in course.lessons.order_by(Lesson.order_index)]
  return success_response("Course retrieved.", {"course": payload})


def create_course():
  data = request.get_json(silent=True)
  errors = validate_course(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  category_id = data.get("category_id")
  speciality = data.get("speciality")
  if category_id and not speciality:
    cat = CourseCategory.query.get(category_id)
    if cat:
      speciality = cat.name

  course = Course(
    title=data["title"],
    description=data.get("description"),
    speciality=speciality,
    category_id=category_id,
    difficulty=data.get("difficulty", "medium"),
    duration_hours=data.get("duration_hours", 0),
    instructor_name=data.get("instructor_name"),
    instructor_id=data.get("instructor_id"),
    thumbnail_url=data.get("thumbnail_url"),
    banner_url=data.get("banner_url"),
    learning_objectives=data.get("learning_objectives"),
    prerequisites=data.get("prerequisites"),
    certificate_eligible=data.get("certificate_eligible", True),
    is_published=data.get("is_published", True),
  )
  db.session.add(course)
  db.session.commit()
  return success_response("Course created.", {"course": course.to_dict()}, 201)


def update_course(course_id):
  course = Course.query.get(course_id)
  if not course:
    return error_response("Course not found.", 404)

  data = request.get_json(silent=True) or {}
  errors = validate_course(data, partial=True)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  updatable = (
    "title",
    "description",
    "speciality",
    "category_id",
    "difficulty",
    "duration_hours",
    "instructor_name",
    "instructor_id",
    "thumbnail_url",
    "banner_url",
    "learning_objectives",
    "prerequisites",
    "certificate_eligible",
    "is_published",
  )
  for field in updatable:
    if field in data:
      setattr(course, field, data[field])

  if "category_id" in data and data["category_id"] and not data.get("speciality"):
    cat = CourseCategory.query.get(data["category_id"])
    if cat:
      course.speciality = cat.name

  db.session.commit()
  return success_response("Course updated.", {"course": course.to_dict()})


def delete_course(course_id):
  course = Course.query.get(course_id)
  if not course:
    return error_response("Course not found.", 404)
  db.session.delete(course)
  db.session.commit()
  return success_response("Course deleted.")


# --- Lessons ---

def list_lessons(course_id):
  if not _accessible_course(course_id):
    return error_response("Course not found.", 404)
  lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order_index).all()
  return success_response(
    "Lessons retrieved.",
    {"lessons": [l.to_dict(include_media=True) for l in lessons]},
  )


def get_lesson(lesson_id):
  lesson = Lesson.query.get(lesson_id)
  if not lesson or not _accessible_course(lesson.course_id):
    return error_response("Lesson not found.", 404)
  completed = CompletedLesson.query.filter_by(user_id=current_user.id, lesson_id=lesson_id).first()
  payload = lesson.to_dict(include_media=True)
  payload["completed"] = completed is not None
  return success_response("Lesson retrieved.", {"lesson": payload})


def create_lesson():
  data = request.get_json(silent=True)
  errors = validate_lesson(data)
  if errors:
    return error_response("Validation failed.", 400, {"errors": errors})

  if not Course.query.get(data["course_id"]):
    return error_response("Course not found.", 404)

  lesson = Lesson(
    course_id=data["course_id"],
    module_id=data.get("module_id"),
    title=data["title"],
    content=data.get("content"),
    summary=data.get("summary"),
    order_index=data.get("order_index", 0),
    duration_minutes=data.get("duration_minutes", 15),
    topic_tags=data.get("topic_tags"),
    is_published=data.get("is_published", True),
  )
  db.session.add(lesson)
  db.session.commit()
  return success_response("Lesson created.", {"lesson": lesson.to_dict()}, 201)


def update_lesson(lesson_id):
  lesson = Lesson.query.get(lesson_id)
  if not lesson:
    return error_response("Lesson not found.", 404)

  data = request.get_json(silent=True) or {}
  for field in (
    "title",
    "content",
    "summary",
    "order_index",
    "duration_minutes",
    "topic_tags",
    "course_id",
    "module_id",
    "is_published",
  ):
    if field in data:
      setattr(lesson, field, data[field])
  db.session.commit()
  return success_response("Lesson updated.", {"lesson": lesson.to_dict(include_media=True)})


def delete_lesson(lesson_id):
  lesson = Lesson.query.get(lesson_id)
  if not lesson:
    return error_response("Lesson not found.", 404)
  db.session.delete(lesson)
  db.session.commit()
  return success_response("Lesson deleted.")


# --- Bookmarks ---

def add_bookmark(lesson_id):
  lesson = Lesson.query.get(lesson_id)
  if not lesson or not _accessible_course(lesson.course_id):
    return error_response("Lesson not found.", 404)

  existing = LessonBookmark.query.filter_by(user_id=current_user.id, lesson_id=lesson_id).first()
  if existing:
    return success_response("Already bookmarked.", {"bookmark": existing.to_dict()})

  bookmark = LessonBookmark(user_id=current_user.id, lesson_id=lesson_id)
  db.session.add(bookmark)
  db.session.commit()
  return success_response("Lesson bookmarked.", {"bookmark": bookmark.to_dict()}, 201)


def remove_bookmark(lesson_id):
  bookmark = LessonBookmark.query.filter_by(user_id=current_user.id, lesson_id=lesson_id).first()
  if not bookmark:
    return error_response("Bookmark not found.", 404)
  db.session.delete(bookmark)
  db.session.commit()
  return success_response("Bookmark removed.")


def list_bookmarks():
  bookmarks = LessonBookmark.query.filter_by(user_id=current_user.id).all()
  return success_response("Bookmarks retrieved.", {"bookmarks": [b.to_dict() for b in bookmarks]})


# --- Completed lessons / progress ---

def complete_lesson(lesson_id):
  lesson = Lesson.query.get(lesson_id)
  if not lesson or not _accessible_course(lesson.course_id):
    return error_response("Lesson not found.", 404)

  existing = CompletedLesson.query.filter_by(user_id=current_user.id, lesson_id=lesson_id).first()
  newly_completed = False
  activity_record = existing
  if not existing:
    record = CompletedLesson(user_id=current_user.id, lesson_id=lesson_id)
    db.session.add(record)
    db.session.commit()
    activity_record = record
    newly_completed = True

  minutes = int(lesson.duration_minutes or 0) if newly_completed else 0
  progress = LearningService.update_learning_progress(current_user.id, minutes_delta=minutes)
  course_progress = LearningService.update_course_progress(
    current_user.id,
    lesson.course_id,
    last_lesson_id=lesson_id,
    minutes_delta=minutes,
  )
  if lesson.course and lesson.course.source_book_id:
    try:
      from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
      AdaptiveLearningService.refresh_book(lesson.course.source_book_id, current_user.id)
    except Exception:
      current_app.logger.exception("Adaptive topic mastery refresh failed after lesson completion.")
  try:
    from app.services.learning_dashboard_service import LearningDashboardService
    LearningDashboardService.record_activity(
      current_user.id,
      "lesson_completed",
      str(activity_record.id),
      f"Completed {lesson.title}",
      book_id=lesson.course.source_book_id if lesson.course else None,
      course_id=lesson.course_id,
      module_id=lesson.module_id,
      topic_id=lesson.topic_id,
      lesson_id=lesson.id,
      duration_minutes=int(lesson.duration_minutes or 0),
      occurred_at=activity_record.completed_at,
    )
  except Exception:
    current_app.logger.exception("Learning activity recording failed after lesson completion.")
  return success_response(
    "Lesson marked complete.",
    {
      "progress": progress.to_dict(),
      "course_progress": course_progress.to_dict() if course_progress else None,
    },
  )


def list_completed_lessons():
  records = CompletedLesson.query.filter_by(user_id=current_user.id).all()
  return success_response("Completed lessons retrieved.", {
    "completed_lessons": [r.to_dict() for r in records],
  })


def list_course_progress():
  rows = CourseProgress.query.filter_by(user_id=current_user.id).order_by(CourseProgress.updated_at.desc()).all()
  return success_response(
    "Course progress retrieved.",
    {"course_progress": [r.to_dict() for r in rows]},
  )


def enroll_course(course_id):
  course = _accessible_course(course_id)
  if not course:
    return error_response("Course not found.", 404)

  progress = LearningService.enroll_course(current_user.id, course_id)
  return success_response("Enrolled in course.", {"course_progress": progress.to_dict()}, 201)


# --- Recommendations ---

def list_recommendations():
  newly_created = LearningService.generate_recommendations(current_user.id)
  all_recs = Recommendation.query.filter_by(user_id=current_user.id).order_by(
    Recommendation.created_at.desc()
  ).all()
  return success_response("Recommendations retrieved.", {
    "recommendations": [r.to_dict() for r in all_recs],
    "newly_created": len(newly_created),
  })


def weak_topics():
  topics = LearningService.detect_weak_topics(current_user.id)
  return success_response("Weak topics detected.", {"weak_topics": topics})
