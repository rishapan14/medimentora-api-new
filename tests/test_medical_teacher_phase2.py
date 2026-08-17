"""Phase 2 regression tests for asynchronous learning-document processing."""

from __future__ import annotations

import io
import uuid

from werkzeug.datastructures import FileStorage

from app.models.book_model import Book, DocumentProcessingJob
from app.services.medical_teacher.document_extractor import DocumentExtractor, PageStructure
from app.services.medical_teacher.document_validator import TeacherDocumentValidator
from app.services.medical_teacher.processing_job_service import DocumentProcessingJobService


def test_document_validator_rejects_duplicate_content_in_batch():
  first = FileStorage(stream=io.BytesIO(b"same course notes"), filename="notes-a.txt", content_type="text/plain")
  second = FileStorage(stream=io.BytesIO(b"same course notes"), filename="notes-b.txt", content_type="text/plain")

  result = TeacherDocumentValidator().validate([first, second])

  assert result.ok is False
  assert any(issue.code == "duplicate_content" for issue in result.errors)


def test_document_cleanup_removes_repeated_page_noise_and_ocr_duplicates():
  pages = [
    PageStructure(
      page_number=number,
      text=(
        "MediMentora Respiratory Course\n"
        f"Topic {number}\n"
        "Gas exchange transfers oxygen and carbon dioxide.\n"
        "Gas exchange transfers oxygen and carbon dioxide.\n"
        f"Page {number} of 4"
      ),
    )
    for number in range(1, 5)
  ]

  DocumentExtractor._clean_repeated_page_noise(pages)

  assert all("MediMentora Respiratory Course" not in page.text for page in pages)
  assert all("Page " not in page.text for page in pages)
  assert all(page.text.count("Gas exchange transfers") == 1 for page in pages)


def test_book_payload_does_not_expose_internal_file_path():
  book = Book(
    id=7,
    user_id=3,
    title="Respiratory Course",
    original_filename="respiratory.pdf",
    stored_filename="stored.pdf",
    file_path="/private/internal/stored.pdf",
    storage_backend="local",
    storage_key="stored.pdf",
    file_type="pdf",
    status="uploaded",
    chapter_count=0,
  )

  payload = book.to_dict()

  assert "file_path" not in payload
  assert payload["storage_backend"] == "local"


def test_processing_job_payload_clamps_progress_and_uses_public_identifier():
  job = DocumentProcessingJob(
    public_id="8cc5c8df-a62a-4ac6-9164-a8eb03706066",
    user_id=1,
    book_id=2,
    status="processing",
    stage="extracting_content",
    progress_percent=120,
    attempts=1,
    max_attempts=3,
  )

  payload = job.to_dict(include_book=False)

  assert payload["id"] == job.public_id
  assert payload["progress_percent"] == 100
  assert "user_id" not in payload


def test_processing_job_routes_require_authentication(client):
  listed = client.get("/api/medical-teacher/jobs")
  detail = client.get("/api/medical-teacher/jobs/not-a-real-job")

  assert listed.status_code == 401
  assert detail.status_code == 401


def test_uploaded_pdf_can_complete_durable_processing_job(client, auth_headers, app):
  import fitz

  pdf = fitz.open()
  page = pdf.new_page()
  page.insert_text((72, 72), f"Respiratory learning objective {uuid.uuid4().hex}")
  raw = pdf.tobytes()
  pdf.close()

  response = client.post(
    "/api/medical-teacher/books/upload-and-process",
    data={"files": (io.BytesIO(raw), "phase2-course.pdf")},
    headers=auth_headers,
    content_type="multipart/form-data",
  )
  assert response.status_code == 202
  item = response.get_json()["data"]["items"][0]
  job_id = item["job"]["id"]
  book_id = item["book"]["id"]

  try:
    with app.app_context():
      job = DocumentProcessingJob.query.filter_by(public_id=job_id).first()
      assert job is not None
      job.status = "processing"
      job.stage = "starting"
      job.lease_token = uuid.uuid4().hex
      job.attempts = 1
      from app.extensions import db

      db.session.commit()
      completed = DocumentProcessingJobService.process_claimed(job)
      assert completed.status == "succeeded"
      assert completed.result_json["page_count"] == 1

    status = client.get(f"/api/medical-teacher/jobs/{job_id}", headers=auth_headers)
    assert status.status_code == 200
    assert status.get_json()["data"]["job"]["stage"] == "ready"
  finally:
    client.delete(f"/api/medical-teacher/books/{book_id}", headers=auth_headers)
