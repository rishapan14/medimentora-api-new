"""Phase 3 tests for grounded document-structure detection."""

from __future__ import annotations

import io
import uuid

from app.extensions import db
from app.models.book_model import Book, DocumentProcessingJob
from app.services.medical_teacher.document_structure_service import DocumentStructureDetector
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def _synthetic_book() -> Book:
  return Book(
    id=91,
    user_id=4,
    title="Respiratory Nursing",
    original_filename="respiratory.pdf",
    stored_filename="respiratory.pdf",
    file_path="respiratory.pdf",
    file_type="pdf",
    status="extracted",
    extracted_text="Respiratory source text",
    page_count=2,
    structure_json={
      "pages": [
        {
          "page_number": 1,
          "headings": [
            "MODULE 1: Respiratory Foundations",
            "CHAPTER 1: Lung Anatomy",
            "1.1 Gas Exchange",
          ],
          "text": (
            "MODULE 1: Respiratory Foundations\n"
            "CHAPTER 1: Lung Anatomy\n"
            "1.1 Gas Exchange\n"
            "Learning Objectives\n"
            "- Describe oxygen transport\n"
            "- Explain carbon dioxide removal\n"
            "Alveolus: A small air sac where gas exchange occurs.\n"
            "Clinical example: A patient may present with shortness of breath.\n"
            "Important: Match ventilation with perfusion for the exam."
          ),
        },
        {
          "page_number": 2,
          "headings": ["1.1.1 Diffusion"],
          "text": "1.1.1 Diffusion\nExample: Oxygen moves down its concentration gradient.",
        },
      ]
    },
  )


def test_detector_builds_page_grounded_hierarchy_and_signals():
  structure = DocumentStructureDetector.detect(_synthetic_book())

  module = structure["hierarchy"][0]
  chapter = module["children"][0]
  topic = chapter["children"][0]
  subtopic = topic["children"][0]

  assert [module["type"], chapter["type"], topic["type"], subtopic["type"]] == [
    "module",
    "chapter",
    "topic",
    "subtopic",
  ]
  assert topic["source"]["document_id"] == 91
  assert topic["source"]["page_start"] == 1
  assert subtopic["source"]["page_start"] == 2
  assert structure["counts"]["learning_objectives"] == 2
  assert structure["definitions"][0]["term"] == "Alveolus"
  assert len(structure["definitions"]) == 1
  assert structure["clinical_concepts"]
  assert structure["exam_relevant_concepts"]
  assert structure["grounding"]["ai_generated"] is False


def test_detector_does_not_invent_modules_or_chapters():
  book = _synthetic_book()
  book.structure_json = {
    "pages": [
      {
        "page_number": 1,
        "headings": ["Gas Exchange"],
        "text": "Gas Exchange\nOxygen and carbon dioxide move across the alveolar membrane.",
      }
    ]
  }

  structure = DocumentStructureDetector.detect(book)

  assert structure["counts"]["modules"] == 0
  assert structure["counts"]["chapters"] == 0
  assert structure["counts"]["topics"] == 1
  assert any("not invented" in warning for warning in structure["warnings"])


def test_structure_routes_require_authentication(client):
  detail = client.get("/api/medical-teacher/books/1/structure")
  detect = client.post("/api/medical-teacher/books/1/detect-structure")

  assert detail.status_code == 401
  assert detect.status_code == 401


def test_background_pipeline_persists_and_returns_detected_structure(client, auth_headers, app):
  marker = uuid.uuid4().hex
  content = (
    "MODULE 1: Cardiovascular Foundations\n"
    "CHAPTER 1: Heart Anatomy\n"
    "1.1 Cardiac Chambers\n"
    "Learning Objectives\n"
    "- Identify the four cardiac chambers\n"
    f"Course marker: {marker}\n"
  ).encode()
  response = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(content), "phase3-structure.txt")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert response.status_code == 202
  item = response.get_json()["data"]["items"][0]
  book_id = item["book"]["id"]
  job_id = item["job"]["id"]

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
      assert completed.result_json["structure_ready"] is True
      assert completed.result_json["structure_counts"]["modules"] == 1
      assert completed.result_json["course_ready"] is True

    structure_response = client.get(
      f"/api/medical-teacher/books/{book_id}/structure",
      headers=auth_headers,
    )
    assert structure_response.status_code == 200
    structure = structure_response.get_json()["data"]["structure"]
    assert structure["schema_version"] == "1.0"
    assert structure["hierarchy"][0]["title"] == "MODULE 1: Cardiovascular Foundations"
    assert structure["hierarchy"][0]["source"]["document_id"] == book_id
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
