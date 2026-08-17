"""Phase 13 tests for the evidence-backed personalized learning dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.extensions import db
from app.models.course_model import CompletedLesson, Course, CourseModule, Lesson
from app.models.learning_activity_model import LearningActivity
from app.models.user_model import User
from app.services.learning_dashboard_service import LearningDashboardService
from app.utils import utc_now


def test_phase13_dashboard_requires_auth_and_calculates_streaks(client):
  assert client.get("/api/progress/learning-dashboard").status_code == 401
  now = utc_now()
  activities = [
    SimpleNamespace(occurred_at=now),
    SimpleNamespace(occurred_at=now - timedelta(days=1)),
    SimpleNamespace(occurred_at=now - timedelta(days=3)),
  ]
  assert LearningDashboardService._streak(activities) == {"current": 2, "best": 2}
  assert LearningActivity.__table__.name == "learning_activities"
  assert any(
    constraint.name == "uq_learning_activity_source"
    for constraint in LearningActivity.__table__.constraints
  )


def test_phase13_dashboard_uses_owned_idempotent_learning_evidence(client, auth_headers, app):
  marker = uuid.uuid4().hex
  course_id = None
  completion_id = None
  foreign_user_id = None
  foreign_course_id = None
  with app.app_context():
    user = User.query.filter_by(email="student@clinical.com").first()
    assert user is not None
    foreign_user = User(email=f"phase13-{marker}@example.com", role="medical_student")
    foreign_user.set_password("test-only-password")
    db.session.add(foreign_user)
    db.session.flush()
    foreign_user_id = foreign_user.id

    course = Course(
      title=f"Phase 13 Learning {marker}",
      owner_user_id=user.id,
      origin="uploaded_document",
      is_published=True,
    )
    foreign_course = Course(
      title=f"Private foreign course {marker}",
      owner_user_id=foreign_user.id,
      origin="uploaded_document",
      is_published=True,
    )
    db.session.add_all([course, foreign_course])
    db.session.flush()
    course_id = course.id
    foreign_course_id = foreign_course.id
    module = CourseModule(course_id=course.id, title="Foundations", order_index=1)
    db.session.add(module)
    db.session.flush()
    first = Lesson(
      course_id=course.id,
      module_id=module.id,
      title="Measured lesson",
      duration_minutes=20,
      order_index=1,
    )
    second = Lesson(
      course_id=course.id,
      module_id=module.id,
      title="Recommended next lesson",
      duration_minutes=15,
      order_index=2,
    )
    db.session.add_all([first, second])
    db.session.flush()
    completion = CompletedLesson(user_id=user.id, lesson_id=first.id, completed_at=utc_now())
    db.session.add(completion)
    db.session.commit()
    completion_id = completion.id

    first_activity = LearningDashboardService.record_activity(
      user.id,
      "lesson_completed",
      str(completion.id),
      f"Completed {first.title}",
      course_id=course.id,
      module_id=module.id,
      lesson_id=first.id,
      duration_minutes=20,
      occurred_at=completion.completed_at,
    )
    duplicate = LearningDashboardService.record_activity(
      user.id,
      "lesson_completed",
      str(completion.id),
      "This duplicate must not replace the source event",
      duration_minutes=999,
    )
    assert duplicate.id == first_activity.id
    assert duplicate.duration_minutes == 20
    LearningDashboardService.record_activity(
      user.id,
      "ai_tutor",
      f"phase13-zero-{marker}",
      "Source-grounded tutor session",
      course_id=course.id,
      lesson_id=first.id,
      duration_minutes=0,
    )
    LearningDashboardService.record_activity(
      foreign_user.id,
      "lesson_completed",
      f"phase13-private-{marker}",
      "Foreign private evidence",
      course_id=foreign_course.id,
      duration_minutes=600,
    )

  response = client.get("/api/progress/learning-dashboard", headers=auth_headers)
  assert response.status_code == 200
  dashboard = response.get_json()["data"]["dashboard"]
  row = next(item for item in dashboard["courses"] if item["course_id"] == course_id)
  assert row["progress_percent"] == 50
  assert row["lessons_completed"] == 1
  assert row["lessons_total"] == 2
  assert row["module_progress"][0]["progress_percent"] == 50
  assert row["recommended_lesson_title"] == "Recommended next lesson"
  assert row["study_minutes"] == 20
  assert dashboard["overview"]["study_minutes"] >= 20
  assert dashboard["overview"]["current_streak"] >= 1
  assert dashboard["tracking"]["study_time_policy"].startswith("Recorded durations only")
  with app.app_context():
    user = User.query.filter_by(email="student@clinical.com").first()
    assert LearningActivity.query.filter_by(
      user_id=user.id,
      source_id=f"phase13-zero-{marker}",
    ).count() == 1
  assert all(item["course_id"] != foreign_course_id for item in dashboard["courses"])
  assert all(item["title"] != "Foreign private evidence" for item in dashboard["recent_activity"])
  today = datetime.fromisoformat(dashboard["generated_at"]).date().isoformat()
  today_activity = next(item for item in dashboard["weekly_activity"] if item["date"] == today)
  assert today_activity["minutes"] >= 20
  assert today_activity["activities"] >= 2

  with app.app_context():
    LearningActivity.query.filter(
      LearningActivity.source_id.in_([
        str(completion_id),
        f"phase13-zero-{marker}",
        f"phase13-private-{marker}",
      ])
    ).delete(synchronize_session=False)
    if completion_id:
      completion = db.session.get(CompletedLesson, completion_id)
      if completion:
        db.session.delete(completion)
    if course_id:
      course = db.session.get(Course, course_id)
      if course:
        db.session.delete(course)
    if foreign_course_id:
      foreign_course = db.session.get(Course, foreign_course_id)
      if foreign_course:
        db.session.delete(foreign_course)
    db.session.commit()
    if foreign_user_id:
      foreign_user = db.session.get(User, foreign_user_id)
      if foreign_user:
        db.session.delete(foreign_user)
        db.session.commit()
