"""Verify LMS learning schema after Module 1 upgrade."""
from sqlalchemy import inspect

from app import create_app
from app.extensions import db
from app.helpers.schema_patches import ensure_learning_schema
from app.models.course_model import Course, CourseCategory, CourseModule, Lesson

REQUIRED_TABLES = {
    "courses",
    "course_categories",
    "course_modules",
    "lessons",
    "lesson_resources",
    "lesson_videos",
    "lesson_bookmarks",
    "completed_lessons",
    "course_progress",
    "course_bookmarks",
    "course_reviews",
    "quizzes",
    "questions",
    "quiz_answers",
    "results",
    "certificates",
    "recommendations",
}

app = create_app()
with app.app_context():
    ensure_learning_schema()
    tables = set(inspect(db.engine).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - tables)
    print("=== LMS tables ===")
    for name in sorted(REQUIRED_TABLES):
        print(f"  [{'OK' if name in tables else 'MISS'}] {name}")
    print()
    if missing_tables:
        print("MISSING TABLES:", missing_tables)
        raise SystemExit(1)

    cats = CourseCategory.query.count()
    print(f"course_categories seeded: {cats}")
    assert cats >= 30, "Expected medical categories to be seeded"

    # Ensure existing courses still load
    course_count = Course.query.count()
    lesson_count = Lesson.query.count()
    print(f"existing courses: {course_count}, lessons: {lesson_count}")

    # Smoke: create a module under first course if any
    course = Course.query.first()
    if course:
        module = CourseModule(
            course_id=course.id,
            title="Module 1 — Foundations",
            description="Auto-created for schema verification",
            order_index=1,
        )
        db.session.add(module)
        db.session.commit()
        mid = module.id
        db.session.delete(module)
        db.session.commit()
        print(f"course_modules smoke OK (temp id={mid})")

    print("Learning database module verified.")
