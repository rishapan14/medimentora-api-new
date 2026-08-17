"""Phase 11 tests for adaptive, grounded Teach Me sessions."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Lesson
from app.models.quiz_model import Question
from app.models.tutor_model import TutorMessage, TutorSession
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService
from app.services.medical_teacher.teach_me_service import TEACH_ME_DIFFICULTIES, TeachMeService


def test_phase11_contract_and_routes_require_authentication(client):
  assert set(TEACH_ME_DIFFICULTIES) == {"beginner", "intermediate", "advanced"}
  assert TeachMeService._shift_difficulty("beginner", 1) == "intermediate"
  assert TeachMeService._shift_difficulty("advanced", 1) == "advanced"
  assert TeachMeService._answer_is_correct("True", "true", "true_false") is True
  assert client.get("/api/medical-teacher/books/1/teach-me/configuration").status_code == 401
  assert client.get("/api/medical-teacher/books/1/teach-me/sessions").status_code == 401
  assert client.post("/api/medical-teacher/books/1/teach-me/sessions", json={"lesson_id": 1}).status_code == 401
  assert client.get("/api/medical-teacher/books/1/teach-me/sessions/session-id").status_code == 401
  assert client.post("/api/medical-teacher/books/1/teach-me/sessions/session-id/advance").status_code == 401
  assert client.post(
    "/api/medical-teacher/books/1/teach-me/sessions/session-id/answer",
    json={"answer": "test"},
  ).status_code == 401


def test_teach_me_guides_evaluates_adapts_and_persists(
  client,
  auth_headers,
  app,
):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Respiratory Physiology\n"
    "CHAPTER 1: Gas Exchange\n"
    "1.1 Alveolar Gas Exchange\n"
    "Alveoli are thin-walled air sacs where oxygen diffuses into pulmonary capillary blood.\n"
    "Carbon dioxide diffuses from pulmonary capillary blood into the alveoli for exhalation.\n"
    "A large surface area and a thin respiratory membrane support efficient diffusion.\n"
    "Learning objective: explain oxygen and carbon dioxide movement across the respiratory membrane.\n"
    "Key concept: diffusion follows a partial pressure gradient.\n"
    "Important: ventilation brings fresh gas to the alveoli while perfusion supplies capillary blood.\n"
    f"Source marker {marker}.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase11-{marker}.txt")},
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
      assert completed.result_json["teach_me_ready"] is True
      lesson = Lesson.query.filter_by(course_id=completed.result_json["course_id"]).first()
      assert lesson is not None
      lesson_id = lesson.id

    configured = client.get(
      f"/api/medical-teacher/books/{book_id}/teach-me/configuration",
      headers=auth_headers,
    )
    assert configured.status_code == 200
    assert configured.get_json()["data"]["grounding"]["adaptive"] is True

    created = client.post(
      f"/api/medical-teacher/books/{book_id}/teach-me/sessions",
      json={"lesson_id": lesson_id, "difficulty": "beginner", "language": "en"},
      headers=auth_headers,
    )
    assert created.status_code == 201
    session = created.get_json()["data"]["session"]
    session_id = session["id"]
    assert session["session_type"] == "teach_me"
    assert session["current_step_data"]["type"] == "explanation"
    assert session["current_step_data"]["source"]["page_numbers"] == [1]

    resumed = client.post(
      f"/api/medical-teacher/books/{book_id}/teach-me/sessions",
      json={"lesson_id": lesson_id, "difficulty": "advanced", "language": "en"},
      headers=auth_headers,
    )
    assert resumed.status_code == 200
    assert resumed.get_json()["data"]["reused"] is True
    assert resumed.get_json()["data"]["session"]["id"] == session_id
    assert resumed.get_json()["data"]["session"]["difficulty"] == "beginner"

    evaluations = []
    for _ in range(20):
      detail = client.get(
        f"/api/medical-teacher/books/{book_id}/teach-me/sessions/{session_id}",
        headers=auth_headers,
      )
      assert detail.status_code == 200
      session = detail.get_json()["data"]["session"]
      if session["status"] == "completed":
        break
      step = session["current_step_data"]
      if step["type"] != "question":
        advanced = client.post(
          f"/api/medical-teacher/books/{book_id}/teach-me/sessions/{session_id}/advance",
          headers=auth_headers,
        )
        assert advanced.status_code == 200
        continue
      assert "correct_answer" not in step
      assert "explanation" not in step
      with app.app_context():
        question = db.session.get(Question, int(step["question_id"]))
        assert question is not None
        correct_answer = question.correct_answer
      answered = client.post(
        f"/api/medical-teacher/books/{book_id}/teach-me/sessions/{session_id}/answer",
        json={"answer": correct_answer},
        headers=auth_headers,
      )
      assert answered.status_code == 201
      evaluation = answered.get_json()["data"]["evaluation"]
      assert evaluation["correct"] is True
      assert evaluation["source"]["document_id"] == book_id
      evaluations.append(evaluation)

    assert session["status"] == "completed"
    assert session["progress_percent"] == 100
    assert session["correct_answers"] >= 2
    assert session["difficulty"] == "intermediate"
    assert len(evaluations) >= 2

    listed = client.get(
      f"/api/medical-teacher/books/{book_id}/teach-me/sessions",
      headers=auth_headers,
    )
    assert listed.status_code == 200
    assert listed.get_json()["data"]["total"] == 1

    tutor_sessions = client.get(
      f"/api/medical-teacher/books/{book_id}/tutor/sessions",
      headers=auth_headers,
    )
    assert tutor_sessions.status_code == 200
    assert tutor_sessions.get_json()["data"]["total"] == 0

    with app.app_context():
      row = TutorSession.query.filter_by(public_id=session_id).first()
      assert row is not None
      session_db_id = row.id
      assert row.session_type == "teach_me"
      assert row.completed_at is not None
      assert TutorMessage.query.filter_by(session_id=row.id).count() >= 4
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    if session_db_id:
      with app.app_context():
        assert db.session.get(TutorSession, session_db_id) is None
        assert TutorMessage.query.filter_by(session_id=session_db_id).count() == 0
