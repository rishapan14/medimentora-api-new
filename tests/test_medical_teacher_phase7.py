"""Phase 7 tests for the persisted, document-grounded Ask Your Lesson tutor."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Lesson
from app.models.tutor_model import TutorMessage, TutorSession
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService
from app.services.medical_teacher.tutor_service import (
  TUTOR_LANGUAGES,
  TUTOR_MODES,
  UNSUPPORTED_ANSWER,
  LessonTutorService,
)


def test_phase7_models_and_modes_cover_tutor_contract():
  assert TutorSession.__tablename__ == "tutor_sessions"
  assert TutorMessage.__tablename__ == "tutor_messages"
  assert {
    "beginner",
    "detailed",
    "nursing",
    "exam_prep",
    "quick_revision",
    "question_me",
    "case_based",
  } == set(TUTOR_MODES)
  assert {"en", "ta", "si"} == set(TUTOR_LANGUAGES)


def test_tutor_routes_require_authentication(client):
  assert client.get("/api/medical-teacher/books/1/tutor/configuration").status_code == 401
  assert client.get("/api/medical-teacher/books/1/tutor/sessions").status_code == 401
  assert client.post("/api/medical-teacher/books/1/tutor/sessions", json={"lesson_id": 1}).status_code == 401
  assert client.get("/api/medical-teacher/books/1/tutor/sessions/session-id").status_code == 401
  assert client.post(
    "/api/medical-teacher/books/1/tutor/sessions/session-id/messages",
    json={"message": "Explain this"},
  ).status_code == 401


def test_ai_tutor_response_requires_valid_sources_and_verbatim_evidence():
  sources = {
    "S1": {
      "excerpt": "Mitochondria generate ATP through oxidative phosphorylation.",
    }
  }
  assert LessonTutorService._valid_ai_response(
    {
      "supported": True,
      "answer": "ATP is generated through oxidative phosphorylation.",
      "cited_source_ids": ["S1"],
      "evidence_quotes": ["generate ATP through oxidative phosphorylation"],
    },
    sources,
  ) is True
  assert LessonTutorService._valid_ai_response(
    {
      "supported": True,
      "answer": "Mitochondria produce insulin.",
      "cited_source_ids": ["S1"],
      "evidence_quotes": ["Mitochondria produce insulin"],
    },
    sources,
  ) is False

  assert "හෘදය" in LessonTutorService._meaningful_terms("හෘදය ගැන පැහැදිලි කරන්න")
  assert "இதயம்" in LessonTutorService._meaningful_terms("இதயம் பற்றி விளக்கவும்")
  assert LessonTutorService._valid_ai_response(
    {
      "supported": True,
      "answer": "Unsupported citation.",
      "cited_source_ids": ["S9"],
      "evidence_quotes": ["generate ATP"],
    },
    sources,
  ) is False


def test_tutor_persists_grounded_turns_and_refuses_unsupported_questions(
  client,
  auth_headers,
  app,
  monkeypatch,
):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cellular Medicine\n"
    "CHAPTER 1: Cell Biology\n"
    "1.1 Mitochondrial Function\n"
    "Mitochondria generate adenosine triphosphate ATP through oxidative phosphorylation.\n"
    f"ATP provides cellular energy in this source passage {marker}.\n"
    "1.2 Cell Membrane\n"
    "The cell membrane controls movement of substances into and out of the cell.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase7-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  session_db_id = None

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
      assert completed.result_json["tutor_ready"] is True
      course_id = completed.result_json["course_id"]
      lesson = Lesson.query.filter(
        Lesson.course_id == course_id,
        Lesson.title.ilike("%Mitochondrial%"),
      ).first()
      assert lesson is not None
      lesson_id = lesson.id

    config = client.get(
      f"/api/medical-teacher/books/{book_id}/tutor/configuration",
      headers=auth_headers,
    )
    assert config.status_code == 200
    assert {item["id"] for item in config.get_json()["data"]["languages"]} == {"en", "ta", "si"}

    created = client.post(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions",
      json={"lesson_id": lesson_id, "mode": "detailed", "language": "en"},
      headers=auth_headers,
    )
    assert created.status_code == 201
    session = created.get_json()["data"]["session"]
    session_id = session["id"]
    assert session["lesson_id"] == lesson_id

    monkeypatch.setattr(
      "app.services.medical_teacher.tutor_service.TeacherAIClient.complete_json",
      lambda *_args, **_kwargs: (
        {
          "supported": True,
          "answer": "Mitochondria generate ATP through oxidative phosphorylation.",
          "cited_source_ids": ["S1"],
          "evidence_quotes": [
            "Mitochondria generate adenosine triphosphate ATP through oxidative phosphorylation."
          ],
          "follow_up_question": "Which process generates ATP?",
        },
        "gemini",
      ),
    )
    answered = client.post(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions/{session_id}/messages",
      json={
        "message": "Explain mitochondrial ATP and cellular energy.",
        "mode": "detailed",
        "language": "en",
      },
      headers=auth_headers,
    )
    assert answered.status_code == 201
    answer = answered.get_json()["data"]["assistant_message"]
    assert answer["supported"] is True
    assert answer["used_fallback"] is False
    assert answer["provider"] == "gemini"
    assert answer["sources"]
    assert answer["sources"][0]["page_numbers"] == [1]
    assert "ATP" in answer["content"]
    assert answer["safety"]["not_a_diagnosis"] is True

    monkeypatch.setattr(
      "app.services.medical_teacher.tutor_service.TeacherAIClient.complete_json",
      lambda *_args, **_kwargs: (None, "none"),
    )
    fallback = client.post(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions/{session_id}/messages",
      json={
        "message": "Give the key points about ATP and cellular energy.",
        "mode": "quick_revision",
        "language": "en",
      },
      headers=auth_headers,
    )
    assert fallback.status_code == 201
    fallback_answer = fallback.get_json()["data"]["assistant_message"]
    assert fallback_answer["supported"] is True
    assert fallback_answer["used_fallback"] is True
    assert fallback_answer["provider"] == "offline"
    assert fallback_answer["sources"]

    refused = client.post(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions/{session_id}/messages",
      json={"message": "What is insulin?", "mode": "beginner", "language": "en"},
      headers=auth_headers,
    )
    assert refused.status_code == 201
    refusal = refused.get_json()["data"]["assistant_message"]
    assert refusal["content"] == UNSUPPORTED_ANSWER
    assert refusal["supported"] is False
    assert refusal["sources"] == []

    detail = client.get(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions/{session_id}",
      headers=auth_headers,
    )
    assert detail.status_code == 200
    persisted = detail.get_json()["data"]["session"]
    assert persisted["message_count"] == 6
    assert [message["role"] for message in persisted["messages"]] == [
      "user",
      "assistant",
      "user",
      "assistant",
      "user",
      "assistant",
    ]
    assert all("vector_json" not in message for message in persisted["messages"])

    listed = client.get(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions",
      headers=auth_headers,
    )
    assert listed.status_code == 200
    assert listed.get_json()["data"]["total"] == 1

    with app.app_context():
      row = TutorSession.query.filter_by(public_id=session_id).first()
      assert row is not None
      session_db_id = row.id
      assert TutorMessage.query.filter_by(session_id=row.id).count() == 6
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    if session_db_id:
      with app.app_context():
        assert db.session.get(TutorSession, session_db_id) is None
        assert TutorMessage.query.filter_by(session_id=session_db_id).count() == 0
