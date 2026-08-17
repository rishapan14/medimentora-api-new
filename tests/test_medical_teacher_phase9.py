"""Phase 9 tests for private generated quizzes, attempts, and topic scoring."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Course
from app.models.quiz_model import Question, Quiz, Result
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService
from app.services.medical_teacher.quiz_engine_service import (
  QUIZ_COUNTS,
  QUIZ_DIFFICULTIES,
  QUIZ_MODES,
  QUIZ_SCOPES,
)


def test_phase9_contract_and_routes_require_authentication(client):
  assert set(QUIZ_COUNTS) == {5, 10, 20, 50}
  assert set(QUIZ_DIFFICULTIES) == {"easy", "medium", "hard", "mixed"}
  assert set(QUIZ_SCOPES) == {"entire_course", "module", "topic", "weak_topics"}
  assert set(QUIZ_MODES) == {"mcq", "mixed", "case_based", "exam_mode"}
  assert client.get("/api/medical-teacher/books/1/quiz-configuration").status_code == 401
  assert client.post("/api/medical-teacher/books/1/generate-quiz").status_code == 401
  assert client.get("/api/medical-teacher/books/1/quizzes").status_code == 401
  assert client.get("/api/medical-teacher/books/1/quizzes/1").status_code == 401
  assert client.post("/api/medical-teacher/books/1/quizzes/1/submit").status_code == 401
  assert client.get("/api/medical-teacher/books/1/quiz-attempts").status_code == 401


def test_pipeline_generates_private_quiz_scores_attempts_and_weak_topics(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Respiratory Foundations\n"
    "Learning objective: explain ventilation and gas exchange.\n"
    "CHAPTER 1: Pulmonary Physiology\n"
    "1.1 Ventilation\n"
    "Ventilation moves air between the atmosphere and the alveoli.\n"
    f"This respiratory source has marker {marker}.\n"
    "1.2 Gas Exchange\n"
    "Alveoli exchange oxygen and carbon dioxide across the respiratory membrane.\n"
    "1.3 Pulmonary Circulation\n"
    "Pulmonary arteries carry blood from the right ventricle toward the lungs.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase9-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  quiz_ids: list[int] = []
  result_ids: list[int] = []

  try:
    with app.app_context():
      job = DocumentProcessingJob.query.filter_by(public_id=job_id).first()
      job.status = "processing"
      job.stage = "starting"
      job.lease_token = uuid.uuid4().hex
      job.attempts = 1
      db.session.commit()
      completed = DocumentProcessingJobService.process_claimed(job)
      assert completed.status == "succeeded"
      assert completed.result_json["quizzes_ready"] is True
      assert completed.result_json["quiz_question_count"] > 0
      course = db.session.get(Course, completed.result_json["course_id"])
      assert course.quiz_generation_status == "ready"
      automatic_id = completed.result_json["quiz_id"]
      quiz_ids.append(automatic_id)
      automatic = db.session.get(Quiz, automatic_id)
      assert automatic.is_published is False
      assert automatic.quiz_type == "generated_learning"
      assert automatic.owner_user_id is not None
      assert automatic.source_question_bank_id is not None

    configuration = client.get(
      f"/api/medical-teacher/books/{book_id}/quiz-configuration",
      headers=auth_headers,
    )
    assert configuration.status_code == 200
    assert configuration.get_json()["data"]["question_counts"] == [5, 10, 20, 50]

    listed = client.get(f"/api/medical-teacher/books/{book_id}/quizzes", headers=auth_headers)
    assert listed.status_code == 200
    assert listed.get_json()["data"]["total"] >= 1

    public_list = client.get("/api/quizzes", headers=auth_headers)
    assert public_list.status_code == 200
    assert automatic_id not in [item["id"] for item in public_list.get_json()["data"]["quizzes"]]
    assert client.get(f"/api/quizzes/{automatic_id}", headers=auth_headers).status_code == 404

    detail = client.get(
      f"/api/medical-teacher/books/{book_id}/quizzes/{automatic_id}",
      headers=auth_headers,
    )
    assert detail.status_code == 200
    quiz_payload = detail.get_json()["data"]["quiz"]
    assert quiz_payload["questions"]
    assert all("correct_answer" not in question for question in quiz_payload["questions"])
    assert all(question["explanation"] is None for question in quiz_payload["questions"])

    with app.app_context():
      correct_answers = {
        str(question.id): question.correct_answer
        for question in Question.query.filter_by(quiz_id=automatic_id).all()
      }
    submitted = client.post(
      f"/api/medical-teacher/books/{book_id}/quizzes/{automatic_id}/submit",
      json={"answers": correct_answers, "time_taken_seconds": 42},
      headers=auth_headers,
    )
    assert submitted.status_code == 201
    scored = submitted.get_json()["data"]
    assert scored["result"]["score"] == 100
    assert scored["result"]["passed"] is True
    assert scored["result"]["time_taken_seconds"] == 42
    assert scored["topic_breakdown"]
    assert all(item["accuracy"] == 100 for item in scored["topic_breakdown"])
    assert all(item["correct"] for item in scored["validated_answers"].values())
    result_ids.append(scored["result"]["id"])

    wrong = client.post(
      f"/api/medical-teacher/books/{book_id}/quizzes/{automatic_id}/submit",
      json={"answers": {key: "definitely incorrect" for key in correct_answers}},
      headers=auth_headers,
    )
    assert wrong.status_code == 201
    wrong_result = wrong.get_json()["data"]["result"]
    assert wrong_result["score"] == 0
    assert any(item["level"] == "weak" for item in wrong_result["topic_breakdown"])
    result_ids.append(wrong_result["id"])

    weak_quiz = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-quiz",
      json={
        "question_count": 5,
        "difficulty": "mixed",
        "scope_type": "weak_topics",
        "question_mode": "mixed",
      },
      headers=auth_headers,
    )
    assert weak_quiz.status_code == 201
    weak_payload = weak_quiz.get_json()["data"]
    assert weak_payload["quiz"]["scope_type"] == "weak_topics"
    quiz_ids.append(weak_payload["quiz"]["id"])

    cached = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-quiz",
      json={
        "question_count": 5,
        "difficulty": "mixed",
        "scope_type": "weak_topics",
        "question_mode": "mixed",
      },
      headers=auth_headers,
    )
    assert cached.status_code == 200
    assert cached.get_json()["data"]["reused"] is True

    invalid = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-quiz",
      json={"question_count": 7},
      headers=auth_headers,
    )
    assert invalid.status_code == 400

    attempts = client.get(
      f"/api/medical-teacher/books/{book_id}/quiz-attempts",
      headers=auth_headers,
    )
    assert attempts.status_code == 200
    assert attempts.get_json()["data"]["total"] == 2
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    with app.app_context():
      assert Quiz.query.filter(Quiz.id.in_(quiz_ids)).count() == 0
      assert Result.query.filter(Result.id.in_(result_ids)).count() == 0
