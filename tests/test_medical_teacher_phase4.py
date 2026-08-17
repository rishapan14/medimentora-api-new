"""Phase 4 tests for grounded course/module/topic persistence."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Course, CourseModule, CourseTopic, Lesson
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_phase4_models_reuse_courses_and_add_only_missing_topic_entity():
  assert Course.__tablename__ == "courses"
  assert CourseModule.__tablename__ == "course_modules"
  assert CourseTopic.__tablename__ == "course_topics"
  assert Course.owner_user_id.property.columns[0].nullable is True
  assert Course.source_book_id.property.columns[0].unique is True


def test_phase4_course_routes_require_authentication(client):
  generated = client.post("/api/medical-teacher/books/1/generate-course")
  detail = client.get("/api/medical-teacher/books/1/course")

  assert generated.status_code == 401
  assert detail.status_code == 401


def test_pipeline_generates_idempotent_private_grounded_course(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cardiovascular Foundations\n"
    "CHAPTER 1: Heart Anatomy\n"
    "1.1 Cardiac Chambers\n"
    "Learning Objectives\n"
    "- Identify the four cardiac chambers\n"
    "1.1.1 Left Ventricle\n"
    f"Source marker: {marker}\n"
  ).encode()
  response = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), "phase4-course.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert response.status_code == 202
  item = response.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  course_id = None

  try:
    with app.app_context():
      job = DocumentProcessingJob.query.filter_by(public_id=job_id).first()
      assert job is not None
      job.status = "processing"
      job.stage = "starting"
      job.lease_token = uuid.uuid4().hex
      job.attempts = 1
      db.session.commit()
      completed = DocumentProcessingJobService.process_claimed(job)
      assert completed.status == "succeeded"
      assert completed.result_json["course_ready"] is True
      assert completed.result_json["course_counts"] == {
        "modules": 1,
        "chapters": 1,
        "topics": 1,
        "subtopics": 1,
      }
      course_id = completed.result_json["course_id"]

      course = db.session.get(Course, course_id)
      assert course is not None
      assert course.source_book_id == book_id
      assert course.owner_user_id is not None
      assert course.is_published is False
      assert course.origin == "uploaded_document"
      assert course.lesson_generation_status == "ready"
      assert Lesson.query.filter_by(course_id=course.id).count() == 2

    detail = client.get(f"/api/medical-teacher/books/{book_id}/course", headers=auth_headers)
    assert detail.status_code == 200
    generated = detail.get_json()["data"]["course"]
    assert generated["generation_status"] == "ready"
    assert generated["source_book_id"] == book_id
    assert generated["modules"][0]["structure_type"] == "module"
    chapter = generated["modules"][0]["children"][0]
    assert chapter["structure_type"] == "chapter"
    assert chapter["topics"][0]["structure_type"] == "topic"
    assert chapter["topics"][0]["children"][0]["structure_type"] == "subtopic"
    assert chapter["topics"][0]["source"]["document_id"] == book_id

    repeated = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-course",
      headers=auth_headers,
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["data"]["reused"] is True
    assert repeated.get_json()["data"]["course"]["id"] == course_id

    learning_detail = client.get(f"/api/learning/courses/{course_id}", headers=auth_headers)
    assert learning_detail.status_code == 200
    courses = client.get("/api/learning/courses", headers=auth_headers)
    assert courses.status_code == 200
    assert course_id in [course["id"] for course in courses.get_json()["data"]["courses"]]
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    if course_id is not None:
      with app.app_context():
        assert db.session.get(Course, course_id) is None
