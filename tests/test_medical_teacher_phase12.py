"""Phase 12 tests for multi-signal adaptive learning and weak-topic detection."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.adaptive_learning_model import LearningTopicMastery
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import CourseTopic
from app.models.quiz_model import Question
from app.services.medical_teacher.adaptive_learning_service import (
  MASTERY_LEVELS,
  MIN_RELIABLE_EVIDENCE,
  AdaptiveLearningService,
)
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_phase12_contract_requires_repeated_evidence_and_authentication(client):
  assert set(MASTERY_LEVELS) == {"mastered", "strong", "needs_practice", "weak"}
  values = {
    "quiz_attempts": 1,
    "quiz_questions": 1,
    "quiz_correct": 0,
    "flashcard_reviews": 0,
    "flashcard_correct": 0,
    "flashcard_incorrect": 0,
    "flashcards_mastered": 0,
    "teach_me_answers": 0,
    "teach_me_correct": 0,
    "teach_me_incorrect": 0,
    "lesson_completed": False,
  }
  _, level, confidence = AdaptiveLearningService._score(values)
  assert values["evidence_count"] == 1
  assert level == "needs_practice"
  assert confidence == "low"
  assert MIN_RELIABLE_EVIDENCE > 1
  assert client.get("/api/medical-teacher/books/1/adaptive-learning").status_code == 401
  assert client.post("/api/medical-teacher/books/1/adaptive-learning/refresh").status_code == 401


def test_adaptive_learning_combines_signals_detects_weakness_and_improvement(
  client,
  auth_headers,
  app,
):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cardiovascular Physiology\n"
    "CHAPTER 1: Cardiac Output\n"
    "1.1 Stroke Volume\n"
    "Cardiac output is the volume of blood pumped by the heart each minute.\n"
    "Cardiac output equals heart rate multiplied by stroke volume.\n"
    "Stroke volume is influenced by preload, afterload, and myocardial contractility.\n"
    "Learning objective: explain the determinants of cardiac output and stroke volume.\n"
    "Important concept: venous return contributes to ventricular preload.\n"
    "Clinical example: reduced contractility can reduce stroke volume and cardiac output.\n"
    f"Source marker {marker}.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase12-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  mastery_ids: list[int] = []
  quiz_ids: list[int] = []

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
      assert completed.result_json["adaptive_learning_ready"] is True
      course_id = completed.result_json["course_id"]
      topic = CourseTopic.query.filter_by(course_id=course_id).first()
      assert topic is not None
      topic_id = topic.id
      lesson_id = topic.lesson.id

    initial = client.get(
      f"/api/medical-teacher/books/{book_id}/adaptive-learning",
      headers=auth_headers,
    )
    assert initial.status_code == 200
    initial_data = initial.get_json()["data"]
    assert initial_data["scoring"]["single_error_creates_weak_topic"] is False
    initial_topic = next(row for row in initial_data["topics"] if row["topic_id"] == topic_id)
    assert initial_topic["level"] == "needs_practice"
    assert initial_topic["evidence_count"] == 0

    generated = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-quiz",
      json={
        "question_count": 5,
        "difficulty": "mixed",
        "scope_type": "topic",
        "scope_id": topic_id,
        "question_mode": "mixed",
      },
      headers=auth_headers,
    )
    assert generated.status_code == 201
    quiz = generated.get_json()["data"]["quiz"]
    quiz_id = quiz["id"]
    quiz_ids.append(quiz_id)
    question_ids = [question["id"] for question in quiz["questions"]]
    assert len(question_ids) >= MIN_RELIABLE_EVIDENCE

    wrong = client.post(
      f"/api/medical-teacher/books/{book_id}/quizzes/{quiz_id}/submit",
      json={"answers": {str(question_id): "unsupported wrong answer" for question_id in question_ids}},
      headers=auth_headers,
    )
    assert wrong.status_code == 201

    weak_snapshot = client.get(
      f"/api/medical-teacher/books/{book_id}/adaptive-learning?refresh=false",
      headers=auth_headers,
    ).get_json()["data"]
    weak_topic = next(row for row in weak_snapshot["topics"] if row["topic_id"] == topic_id)
    assert weak_topic["level"] == "weak"
    assert weak_topic["quiz_attempts"] == 1
    assert weak_topic["quiz_questions"] == len(question_ids)
    assert weak_snapshot["study_plan"][0]["action_type"] == "targeted_revision"

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
    quiz_ids.append(weak_quiz.get_json()["data"]["quiz"]["id"])

    with app.app_context():
      correct_answers = {
        str(question_id): db.session.get(Question, question_id).correct_answer
        for question_id in question_ids
      }
    for _ in range(3):
      correct = client.post(
        f"/api/medical-teacher/books/{book_id}/quizzes/{quiz_id}/submit",
        json={"answers": correct_answers},
        headers=auth_headers,
      )
      assert correct.status_code == 201

    completed_lesson = client.post(
      f"/api/learning/lessons/{lesson_id}/complete",
      headers=auth_headers,
    )
    assert completed_lesson.status_code == 200

    cards = client.get(
      f"/api/medical-teacher/books/{book_id}/flashcards",
      headers=auth_headers,
    ).get_json()["data"]["cards"]
    topic_card = next(card for card in cards if card["topic_id"] == topic_id)
    reviewed = client.post(
      f"/api/medical-teacher/books/{book_id}/flashcards/{topic_card['id']}/review",
      json={"action": "correct"},
      headers=auth_headers,
    )
    assert reviewed.status_code == 200

    improved = client.post(
      f"/api/medical-teacher/books/{book_id}/adaptive-learning/refresh",
      headers=auth_headers,
    )
    assert improved.status_code == 200
    improved_data = improved.get_json()["data"]
    improved_topic = next(row for row in improved_data["topics"] if row["topic_id"] == topic_id)
    assert improved_topic["level"] in {"strong", "mastered"}
    assert improved_topic["mastery_score"] > weak_topic["mastery_score"]
    assert improved_topic["quiz_attempts"] == 4
    assert improved_topic["flashcard_reviews"] == 1
    assert improved_topic["lesson_completed"] is True
    assert improved_topic["signals"]["quiz_accuracy"] == 75

    with app.app_context():
      rows = LearningTopicMastery.query.filter_by(book_id=book_id).all()
      mastery_ids = [row.id for row in rows]
      assert rows
      assert all(row.user_id is not None for row in rows)
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    if mastery_ids:
      with app.app_context():
        assert all(db.session.get(LearningTopicMastery, row_id) is None for row_id in mastery_ids)
