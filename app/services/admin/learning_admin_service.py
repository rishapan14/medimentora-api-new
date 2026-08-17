"""Admin Learning Content management (Module 7)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, or_

from app.extensions import db
from app.models.course_model import Course, CourseCategory, Lesson
from app.utils import utc_now
from app.validations.learning_validation import validate_course, validate_lesson

logger = logging.getLogger(__name__)


class AdminLearningService:
  """CRUD for courses and lessons in the Admin Panel."""

  # --- Categories ---

  @classmethod
  def list_categories(cls, *, include_inactive: bool = True) -> dict[str, Any]:
    query = CourseCategory.query
    if not include_inactive:
      query = query.filter_by(is_active=True)
    rows = query.order_by(CourseCategory.sort_order, CourseCategory.name).all()
    return {
      "categories": [
        {
          **c.to_dict(),
          "course_count_all": c.courses.count(),
        }
        for c in rows
      ],
      "total": len(rows),
    }

  # --- Stats ---

  @classmethod
  def stats(cls) -> dict[str, Any]:
    total_courses = Course.query.count()
    published = Course.query.filter(
      or_(Course.is_published.is_(True), Course.is_published.is_(None))
    ).count()
    draft = total_courses - published
    total_lessons = Lesson.query.count()
    published_lessons = Lesson.query.filter(
      or_(Lesson.is_published.is_(True), Lesson.is_published.is_(None))
    ).count()
    enrollments = db.session.query(func.coalesce(func.sum(Course.enrollment_count), 0)).scalar() or 0

    by_difficulty: dict[str, int] = {}
    for diff, count in (
      db.session.query(Course.difficulty, func.count(Course.id)).group_by(Course.difficulty).all()
    ):
      by_difficulty[str(diff or "medium")] = int(count)

    return {
      "courses": total_courses,
      "published_courses": published,
      "draft_courses": draft,
      "lessons": total_lessons,
      "published_lessons": published_lessons,
      "enrollments": int(enrollments),
      "by_difficulty": by_difficulty,
    }

  # --- Courses ---

  @classmethod
  def list_courses(
    cls,
    *,
    q: str | None = None,
    difficulty: str | None = None,
    published: bool | None = None,
    category_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
  ) -> dict[str, Any]:
    query = Course.query

    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        or_(
          Course.title.ilike(like),
          Course.description.ilike(like),
          Course.speciality.ilike(like),
          Course.instructor_name.ilike(like),
        )
      )

    if difficulty:
      query = query.filter(Course.difficulty == difficulty.strip().lower())

    if category_id is not None:
      query = query.filter(Course.category_id == int(category_id))

    if published is True:
      query = query.filter(or_(Course.is_published.is_(True), Course.is_published.is_(None)))
    elif published is False:
      query = query.filter(Course.is_published.is_(False))

    total = query.count()
    rows = (
      query.order_by(Course.updated_at.desc(), Course.id.desc())
      .offset(max(0, offset))
      .limit(min(max(int(limit), 1), 200))
      .all()
    )

    return {
      "courses": [c.to_dict(include_lessons=False) for c in rows],
      "total": total,
      "offset": offset,
      "limit": limit,
      "stats": cls.stats(),
    }

  @classmethod
  def get_course(cls, course_id: int) -> dict[str, Any] | None:
    course = db.session.get(Course, course_id)
    if not course:
      return None
    payload = course.to_dict(include_lessons=True, include_modules=True)
    payload["lessons"] = [
      l.to_dict(include_media=True) for l in course.lessons.order_by(Lesson.order_index)
    ]
    return payload

  @classmethod
  def create_course(cls, data: dict[str, Any] | None) -> dict[str, Any]:
    errors = validate_course(data)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    category_id = data.get("category_id")
    speciality = data.get("speciality")
    if category_id and not speciality:
      cat = db.session.get(CourseCategory, category_id)
      if cat:
        speciality = cat.name

    try:
      course = Course(
        title=data["title"].strip(),
        description=data.get("description"),
        speciality=speciality,
        category_id=category_id,
        difficulty=(data.get("difficulty") or "medium").lower(),
        duration_hours=data.get("duration_hours") or 0,
        instructor_name=data.get("instructor_name"),
        instructor_id=data.get("instructor_id"),
        thumbnail_url=data.get("thumbnail_url"),
        banner_url=data.get("banner_url"),
        learning_objectives=data.get("learning_objectives"),
        prerequisites=data.get("prerequisites"),
        certificate_eligible=bool(data.get("certificate_eligible", True)),
        is_published=bool(data.get("is_published", True)),
      )
      db.session.add(course)
      db.session.commit()
      return {
        "success": True,
        "message": "Course created.",
        "data": {"course": course.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin create course failed")
      return {
        "success": False,
        "message": "Could not create course.",
        "error_code": "create_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def update_course(cls, course_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    course = db.session.get(Course, course_id)
    if not course:
      return {"success": False, "message": "Course not found.", "error_code": "not_found"}

    errors = validate_course(data, partial=True)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
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
    try:
      for field in updatable:
        if field in data:
          value = data[field]
          if field == "difficulty" and value:
            value = str(value).lower()
          if field == "title" and isinstance(value, str):
            value = value.strip()
          setattr(course, field, value)

      if "category_id" in data and data["category_id"] and not data.get("speciality"):
        cat = db.session.get(CourseCategory, data["category_id"])
        if cat:
          course.speciality = cat.name

      course.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Course updated.",
        "data": {"course": course.to_dict()},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update course failed id=%s", course_id)
      return {
        "success": False,
        "message": "Could not update course.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def set_course_published(cls, course_id: int, *, published: bool) -> dict[str, Any]:
    return cls.update_course(course_id, {"is_published": bool(published)})

  @classmethod
  def delete_course(cls, course_id: int) -> dict[str, Any]:
    course = db.session.get(Course, course_id)
    if not course:
      return {"success": False, "message": "Course not found.", "error_code": "not_found"}
    try:
      db.session.delete(course)
      db.session.commit()
      logger.info("Admin deleted course id=%s", course_id)
      return {"success": True, "message": "Course deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete course failed id=%s", course_id)
      return {
        "success": False,
        "message": "Could not delete course.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }

  # --- Lessons ---

  @classmethod
  def list_lessons(cls, course_id: int) -> dict[str, Any]:
    course = db.session.get(Course, course_id)
    if not course:
      return {"success": False, "message": "Course not found.", "error_code": "not_found"}
    lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order_index).all()
    return {
      "success": True,
      "data": {
        "course_id": course_id,
        "lessons": [l.to_dict(include_media=True) for l in lessons],
        "total": len(lessons),
      },
    }

  @classmethod
  def create_lesson(cls, data: dict[str, Any] | None) -> dict[str, Any]:
    errors = validate_lesson(data)
    if errors:
      return {
        "success": False,
        "message": "Validation failed.",
        "error_code": "validation_error",
        "data": {"errors": errors},
      }

    assert data is not None
    course = db.session.get(Course, data["course_id"])
    if not course:
      return {"success": False, "message": "Course not found.", "error_code": "not_found"}

    try:
      order_index = data.get("order_index")
      if order_index is None:
        max_order = (
          db.session.query(func.max(Lesson.order_index))
          .filter_by(course_id=course.id)
          .scalar()
        )
        order_index = int(max_order or 0) + 1

      lesson = Lesson(
        course_id=course.id,
        module_id=data.get("module_id"),
        title=str(data["title"]).strip(),
        content=data.get("content"),
        summary=data.get("summary"),
        order_index=int(order_index),
        duration_minutes=int(data.get("duration_minutes") or 15),
        topic_tags=data.get("topic_tags"),
        is_published=bool(data.get("is_published", True)),
      )
      db.session.add(lesson)
      course.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Lesson created.",
        "data": {"lesson": lesson.to_dict(include_media=True)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin create lesson failed")
      return {
        "success": False,
        "message": "Could not create lesson.",
        "error_code": "create_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def update_lesson(cls, lesson_id: int, data: dict[str, Any] | None) -> dict[str, Any]:
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
      return {"success": False, "message": "Lesson not found.", "error_code": "not_found"}

    errors = validate_lesson(data, partial=True)
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
          value = data[field]
          if field == "title" and isinstance(value, str):
            value = value.strip()
          setattr(lesson, field, value)
      lesson.updated_at = utc_now()
      if lesson.course:
        lesson.course.updated_at = utc_now()
      db.session.commit()
      return {
        "success": True,
        "message": "Lesson updated.",
        "data": {"lesson": lesson.to_dict(include_media=True)},
      }
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin update lesson failed id=%s", lesson_id)
      return {
        "success": False,
        "message": "Could not update lesson.",
        "error_code": "update_failed",
        "data": {"detail": str(exc)},
      }

  @classmethod
  def delete_lesson(cls, lesson_id: int) -> dict[str, Any]:
    lesson = db.session.get(Lesson, lesson_id)
    if not lesson:
      return {"success": False, "message": "Lesson not found.", "error_code": "not_found"}
    try:
      course = lesson.course
      db.session.delete(lesson)
      if course:
        course.updated_at = utc_now()
      db.session.commit()
      return {"success": True, "message": "Lesson deleted."}
    except Exception as exc:
      db.session.rollback()
      logger.exception("Admin delete lesson failed id=%s", lesson_id)
      return {
        "success": False,
        "message": "Could not delete lesson.",
        "error_code": "delete_failed",
        "data": {"detail": str(exc)},
      }
