"""Phase 10 tests for grounded course flashcards and review scheduling."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.body_system_model import HubFlashcard, HubFlashcardFavorite
from app.models.book_model import DocumentProcessingJob
from app.models.course_model import Course
from app.services.medical_teacher.flashcard_service import FLASHCARD_STYLES, REVIEW_ACTIONS
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_phase10_contract_and_routes_require_authentication(client):
  assert set(FLASHCARD_STYLES) == {"easy", "medium", "hard", "exam", "nursing", "clinical"}
  assert set(REVIEW_ACTIONS) == {"correct", "incorrect", "review_later", "mastered"}
  assert client.post("/api/medical-teacher/books/1/generate-flashcards").status_code == 401
  assert client.get("/api/medical-teacher/books/1/flashcards").status_code == 401
  assert client.post("/api/medical-teacher/books/1/flashcards/1/review").status_code == 401


def test_pipeline_generates_private_grounded_cards_and_schedules_reviews(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Nursing Respiratory Foundations\n"
    "Learning objective: explain ventilation and clinical gas exchange.\n"
    "CHAPTER 1: Pulmonary Physiology\n"
    "1.1 Ventilation\n"
    "Ventilation moves air between the atmosphere and the alveoli.\n"
    f"Nursing assessment monitors respiratory effort in this source {marker}.\n"
    "1.2 Clinical Gas Exchange\n"
    "A clinical patient case may assess oxygen and carbon dioxide exchange across the respiratory membrane.\n"
    "1.3 Pulmonary Circulation\n"
    "Pulmonary arteries carry blood from the right ventricle toward the lungs.\n"
  ).encode()
  uploaded = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), f"phase10-{marker}.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert uploaded.status_code == 202
  item = uploaded.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]
  card_ids: list[int] = []
  review_ids: list[int] = []

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
      assert completed.result_json["flashcards_ready"] is True
      assert completed.result_json["flashcard_count"] > 0
      course = db.session.get(Course, completed.result_json["course_id"])
      assert course.flashcard_generation_status == "ready"
      cards = HubFlashcard.query.filter_by(book_id=book_id).all()
      card_ids = [card.id for card in cards]
      assert cards
      assert all(card.owner_user_id is not None for card in cards)
      assert all(card.is_published is False for card in cards)
      assert all(card.origin == "uploaded_document" for card in cards)
      assert all(card.source_json["document_id"] == book_id for card in cards)
      assert all(card.source_json["chunk_ids"] for card in cards)

    listed = client.get(f"/api/medical-teacher/books/{book_id}/flashcards", headers=auth_headers)
    assert listed.status_code == 200
    payload = listed.get_json()["data"]
    assert payload["total"] > 0
    assert payload["stats"]["new"] == payload["total"]
    assert payload["spaced_repetition"]["available"] is True
    first = payload["cards"][0]
    assert first["front_text"]
    assert first["back_text"]
    assert first["source"]["page_numbers"] == [1]
    assert first["review"]["status"] == "new"

    public_cards = client.get("/api/learning/hub/flashcards", headers=auth_headers)
    assert public_cards.status_code == 200
    public_ids = [card["id"] for card in public_cards.get_json()["data"]["items"]]
    assert first["id"] not in public_ids

    correct = client.post(
      f"/api/medical-teacher/books/{book_id}/flashcards/{first['id']}/review",
      json={"action": "correct"},
      headers=auth_headers,
    )
    assert correct.status_code == 200
    first_review = correct.get_json()["data"]["review"]
    assert first_review["correct_count"] == 1
    assert first_review["repetitions"] == 1
    assert first_review["interval_days"] == 1
    assert first_review["next_review_at"] is not None
    review_ids.append(first_review["id"])

    second_correct = client.post(
      f"/api/medical-teacher/books/{book_id}/flashcards/{first['id']}/review",
      json={"action": "correct"},
      headers=auth_headers,
    )
    assert second_correct.status_code == 200
    assert second_correct.get_json()["data"]["review"]["interval_days"] == 6

    incorrect = client.post(
      f"/api/medical-teacher/books/{book_id}/flashcards/{first['id']}/review",
      json={"action": "incorrect"},
      headers=auth_headers,
    )
    assert incorrect.status_code == 200
    incorrect_review = incorrect.get_json()["data"]["review"]
    assert incorrect_review["repetitions"] == 0
    assert incorrect_review["incorrect_count"] == 1

    if len(payload["cards"]) > 1:
      second = payload["cards"][1]
      mastered = client.post(
        f"/api/medical-teacher/books/{book_id}/flashcards/{second['id']}/review",
        json={"action": "mastered"},
        headers=auth_headers,
      )
      assert mastered.status_code == 200
      mastered_review = mastered.get_json()["data"]["review"]
      assert mastered_review["status"] == "mastered"
      assert mastered_review["interval_days"] >= 30
      review_ids.append(mastered_review["id"])

    due = client.get(
      f"/api/medical-teacher/books/{book_id}/flashcards",
      query_string={"due_only": "true"},
      headers=auth_headers,
    )
    assert due.status_code == 200
    assert all(card["review"]["status"] != "mastered" for card in due.get_json()["data"]["cards"])

    style = first["card_level"]
    filtered = client.get(
      f"/api/medical-teacher/books/{book_id}/flashcards",
      query_string={"style": style},
      headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert all(card["card_level"] == style for card in filtered.get_json()["data"]["cards"])

    cached = client.post(
      f"/api/medical-teacher/books/{book_id}/generate-flashcards",
      json={},
      headers=auth_headers,
    )
    assert cached.status_code == 200
    assert cached.get_json()["data"]["reused_count"] > 0

    invalid = client.post(
      f"/api/medical-teacher/books/{book_id}/flashcards/{first['id']}/review",
      json={"action": "maybe"},
      headers=auth_headers,
    )
    assert invalid.status_code == 400
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
    with app.app_context():
      assert HubFlashcard.query.filter(HubFlashcard.id.in_(card_ids)).count() == 0
      assert HubFlashcardFavorite.query.filter(HubFlashcardFavorite.id.in_(review_ids)).count() == 0
