"""Phase 8 tests for private, source-grounded study-question generation."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import Book, DocumentProcessingJob
from app.models.course_model import Course, Lesson
from app.models.quiz_model import Question, Quiz
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService
from app.services.medical_teacher.question_generation_service import (
  QUESTION_TYPES,
  QuestionGenerationService,
)


def test_phase8_question_contract_and_routes_require_authentication(client):
  assert {
    "multiple_choice", "true_false", "fill_in_blank", "short_answer",
    "case_based", "viva", "reasoning", "image_based",
  } == set(QUESTION_TYPES)
  assert client.post("/api/medical-teacher/books/1/generate-questions").status_code == 401
  assert client.get("/api/medical-teacher/books/1/questions").status_code == 401
  assert client.get("/api/medical-teacher/books/1/questions/1/answer").status_code == 401


def test_phase8_ai_candidates_require_verbatim_source_answers_and_evidence(app, monkeypatch):
  source = {
    "text": "Alveoli exchange oxygen and carbon dioxide across the respiratory membrane.",
  }
  lesson = Lesson(title="Gas exchange", course_id=1, module_id=1, order_index=1)
  monkeypatch.setattr(
    "app.services.medical_teacher.question_generation_service.TeacherAIClient.complete_json",
    lambda *_args, **_kwargs: (
      {
        "questions": [
          {
            "question_type": "short_answer",
            "question_text": "What crosses the respiratory membrane?",
            "options": [],
            "correct_answer": "oxygen and carbon dioxide",
            "evidence_quote": "Alveoli exchange oxygen and carbon dioxide",
          },
          {
            "question_type": "short_answer",
            "question_text": "What produces insulin?",
            "options": [],
            "correct_answer": "The liver",
            "evidence_quote": "The liver produces insulin",
          },
        ]
      },
      "gemini",
    ),
  )
  with app.app_context():
    accepted = QuestionGenerationService._ai_specs(lesson, source, 5, ["short_answer"])
  assert len(accepted) == 1
  assert accepted[0]["correct_answer"] == "oxygen and carbon dioxide"


def test_pipeline_generates_cached_private_questions_with_answer_gating(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cardiopulmonary Foundations\n"
    "Learning objective: explain circulation and gas exchange.\n"
    "CHAPTER 1: Circulation\n"
    "1.1 Cardiac Output\n"
    "Cardiac output is the volume of blood pumped by the heart each minute.\n"
    f"This emphasized circulation concept has source marker {marker}.\n"
    "1.2 Pulmonary Gas Exchange\n"
    "Alveoli exchange oxygen and carbon dioxide across the respiratory membrane.\n"
    "1.3 Blood Pressure\n"
    "Blood pressure reflects force exerted by circulating blood on vessel walls.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase8-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  question_id = None
  bank_id = None

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
      assert completed.result_json["questions_ready"] is True
      assert completed.result_json["question_count"] > 0

      book = db.session.get(Book, book_id)
      assert book is not None
      course = db.session.get(Course, completed.result_json["course_id"])
      assert course.question_generation_status == "ready"
      bank = Quiz.query.filter_by(source_book_id=book_id, quiz_type="question_bank").one()
      bank_id = bank.id
      assert bank.is_published is False
      question = Question.query.filter_by(book_id=book_id).first()
      assert question is not None
      question_id = question.id
      assert question.source_json["document_id"] == book_id
      assert question.source_json["chunk_ids"]
      assert question.priority_level in {"high", "important", "recommended"}
      assert "exam prediction" not in (question.priority_reason or "").lower()

    listed = client.get(f"/api/medical-teacher/books/{book_id}/questions", headers=auth_headers)
    assert listed.status_code == 200
    payload = listed.get_json()["data"]
    assert payload["question_count"] > 0
    assert payload["grounding"]["exam_prediction"] is False
    public_question = payload["questions"][0]
    assert "correct_answer" not in public_question
    assert public_question["explanation"] is None

    lesson_id = public_question["lesson_id"]
    filtered = client.get(
      f"/api/medical-teacher/books/{book_id}/questions",
      query_string={"lesson_id": lesson_id, "difficulty": public_question["difficulty"]},
      headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert all(item["lesson_id"] == lesson_id for item in filtered.get_json()["data"]["questions"])

    answer = client.get(
      f"/api/medical-teacher/books/{book_id}/questions/{public_question['id']}/answer",
      headers=auth_headers,
    )
    assert answer.status_code == 200
    revealed = answer.get_json()["data"]["question"]
    assert revealed["correct_answer"]
    assert revealed["explanation"] in revealed["source"]["evidence_quote"]

    reused = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-questions",
      json={},
      headers=auth_headers,
    )
    assert reused.status_code == 200
    assert reused.get_json()["data"]["created_count"] == 0
    assert reused.get_json()["data"]["reused_count"] > 0
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    with app.app_context():
      if bank_id is not None:
        assert db.session.get(Quiz, bank_id) is None
      if question_id is not None:
        assert db.session.get(Question, question_id) is None
