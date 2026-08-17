"""Phase 5 tests for cached, source-grounded lesson generation."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Course, Lesson
from app.services.medical_teacher.lesson_generation_service import LessonGenerationService
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_phase5_reuses_lesson_model_with_grounding_fields():
  assert Lesson.__tablename__ == "lessons"
  assert Lesson.topic_id.property.columns[0].unique is True
  assert hasattr(Lesson, "content_json")
  assert hasattr(Lesson, "source_json")
  assert hasattr(Lesson, "generation_method")


def test_lesson_generation_routes_require_authentication(client):
  generated = client.post("/api/medical-teacher/books/1/generate-lessons")
  listed = client.get("/api/medical-teacher/books/1/lessons")

  assert generated.status_code == 401
  assert listed.status_code == 401


def test_ai_lesson_requires_verbatim_source_evidence():
  source = "The left ventricle pumps oxygenated blood into the aorta."

  assert LessonGenerationService._valid_ai_evidence(
    {
      "overview": "The left ventricle moves oxygenated blood.",
      "evidence_map": {"overview": ["left ventricle pumps oxygenated blood"]},
    },
    source,
  ) is True
  assert LessonGenerationService._valid_ai_evidence(
    {
      "overview": "The left ventricle produces insulin.",
      "evidence_map": {"overview": ["The left ventricle produces insulin"]},
    },
    source,
  ) is False


def test_pipeline_generates_cached_lessons_with_page_sources(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cardiovascular Foundations\n"
    "CHAPTER 1: Heart Anatomy\n"
    "1.1 Cardiac Chambers\n"
    "Learning Objectives\n"
    "- Identify the four cardiac chambers\n"
    "Atrium: An upper chamber of the heart.\n"
    "Important: Blood flow follows the sequence described in this material.\n"
    "1.1.1 Left Ventricle\n"
    f"The left ventricle pumps blood into the aorta and this source includes marker {marker}.\n"
  ).encode()
  response = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), "phase5-lessons.txt")},
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
      assert completed.result_json["lessons_ready"] is True
      assert completed.result_json["lesson_count"] == 2
      assert completed.result_json["lessons_created"] == 2
      course_id = completed.result_json["course_id"]

      course = db.session.get(Course, course_id)
      lessons = Lesson.query.filter_by(course_id=course_id).order_by(Lesson.order_index).all()
      assert course is not None
      assert course.lesson_generation_status == "ready"
      assert len(lessons) == 2
      assert all(lesson.origin == "uploaded_document" for lesson in lessons)
      assert all(lesson.generation_method == "deterministic_grounded" for lesson in lessons)
      assert all(lesson.content_json["grounding"]["ai_generated"] is False for lesson in lessons)
      assert all(lesson.source_json["document_id"] == book_id for lesson in lessons)
      assert all(lesson.source_json["page_numbers"] == [1] for lesson in lessons)
      assert any(marker in lesson.content_json["detailed_explanation"] for lesson in lessons)

    listed = client.get(
      f"/api/medical-teacher/books/{book_id}/lessons?include_content=true",
      headers=auth_headers,
    )
    assert listed.status_code == 200
    listed_lessons = listed.get_json()["data"]["lessons"]
    assert len(listed_lessons) == 2
    assert listed_lessons[0]["content_json"]["source_references"][0]["document_id"] == book_id

    repeated = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-lessons",
      json={"difficulty": "intermediate", "use_ai": False},
      headers=auth_headers,
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["data"]["created_count"] == 0
    assert repeated.get_json()["data"]["reused_count"] == 2

    course_detail = client.get(f"/api/learning/courses/{course_id}", headers=auth_headers)
    assert course_detail.status_code == 200
    api_lessons = course_detail.get_json()["data"]["course"]["lessons"]
    assert api_lessons[0]["source"]["document_id"] == book_id
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
