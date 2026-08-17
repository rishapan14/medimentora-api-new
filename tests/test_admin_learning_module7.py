"""Module 7 — Admin Learning Content management API tests."""

from __future__ import annotations


def test_admin_learning_requires_admin(client, auth_headers):
  resp = client.get("/api/admin/learning/courses", headers=auth_headers)
  assert resp.status_code in (401, 403)


def test_admin_list_courses_and_categories(client, admin_auth_headers):
  cats = client.get("/api/admin/learning/categories", headers=admin_auth_headers)
  assert cats.status_code == 200
  assert "categories" in cats.get_json()["data"]

  courses = client.get("/api/admin/learning/courses?limit=20", headers=admin_auth_headers)
  assert courses.status_code == 200
  data = courses.get_json()["data"]
  assert "courses" in data
  assert "stats" in data
  assert "courses" in data["stats"]


def test_admin_course_and_lesson_crud(client, admin_auth_headers, app_ctx):
  from app.extensions import db
  from app.models.course_model import Course, Lesson

  create = client.post(
    "/api/admin/learning/courses",
    json={
      "title": "Admin Module 7 Test Course",
      "description": "Educational course created by Module 7 tests.",
      "difficulty": "beginner",
      "instructor_name": "Test Instructor",
      "is_published": False,
      "duration_hours": 1.5,
    },
    headers=admin_auth_headers,
  )
  assert create.status_code == 201
  course = create.get_json()["data"]["course"]
  course_id = course["id"]
  assert course["is_published"] is False
  assert course["title"] == "Admin Module 7 Test Course"

  publish = client.post(
    f"/api/admin/learning/courses/{course_id}/publish",
    json={"is_published": True},
    headers=admin_auth_headers,
  )
  assert publish.status_code == 200
  assert publish.get_json()["data"]["course"]["is_published"] is True

  lesson = client.post(
    "/api/admin/learning/lessons",
    json={
      "course_id": course_id,
      "title": "Intro Lesson",
      "content": "Welcome to the course.",
      "duration_minutes": 10,
      "summary": "Overview",
    },
    headers=admin_auth_headers,
  )
  assert lesson.status_code == 201
  lesson_id = lesson.get_json()["data"]["lesson"]["id"]

  listed = client.get(
    f"/api/admin/learning/courses/{course_id}/lessons",
    headers=admin_auth_headers,
  )
  assert listed.status_code == 200
  ids = [l["id"] for l in listed.get_json()["data"]["lessons"]]
  assert lesson_id in ids

  updated = client.patch(
    f"/api/admin/learning/lessons/{lesson_id}",
    json={"title": "Intro Lesson Updated"},
    headers=admin_auth_headers,
  )
  assert updated.status_code == 200
  assert updated.get_json()["data"]["lesson"]["title"] == "Intro Lesson Updated"

  deleted_lesson = client.delete(
    f"/api/admin/learning/lessons/{lesson_id}",
    headers=admin_auth_headers,
  )
  assert deleted_lesson.status_code == 200
  assert db.session.get(Lesson, lesson_id) is None

  deleted_course = client.delete(
    f"/api/admin/learning/courses/{course_id}",
    headers=admin_auth_headers,
  )
  assert deleted_course.status_code == 200
  assert db.session.get(Course, course_id) is None


def test_admin_create_course_validation(client, admin_auth_headers):
  resp = client.post(
    "/api/admin/learning/courses",
    json={"description": "missing title"},
    headers=admin_auth_headers,
  )
  assert resp.status_code == 400
