"""Durable queue and worker operations for learning-document processing."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from flask import current_app
from sqlalchemy import and_, or_

from app.extensions import db
from app.models.book_model import (
  BOOK_STATUS_EXTRACTED,
  BOOK_STATUS_PARSED,
  Book,
  DocumentProcessingJob,
)
from app.services.medical_teacher.document_service import DocumentService
from app.services.medical_teacher.document_structure_service import DocumentStructureService
from app.services.medical_teacher.course_generation_service import CourseGenerationService
from app.services.medical_teacher.lesson_generation_service import LessonGenerationService
from app.services.medical_teacher.rag_service import DocumentRagService
from app.services.medical_teacher.question_generation_service import QuestionGenerationService
from app.services.medical_teacher.quiz_engine_service import LearningQuizEngineService
from app.services.medical_teacher.flashcard_service import LearningFlashcardService
from app.services.medical_teacher.adaptive_learning_service import AdaptiveLearningService
from app.utils import utc_now

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "processing")
FINAL_STATUSES = ("succeeded", "failed", "cancelled")


class DocumentProcessingJobService:
  """Create, lease, execute, and inspect persisted processing jobs."""

  @classmethod
  def enqueue(cls, book: Book, user_id: int) -> DocumentProcessingJob | None:
    if book.user_id != user_id:
      raise LookupError("Book not found.")
    structure_ready = bool((book.structure_json or {}).get("detected_structure"))
    course_ready = bool(book.generated_course and book.generated_course.generation_status == "ready")
    lessons_ready = bool(
      book.generated_course and book.generated_course.lesson_generation_status == "ready"
    )
    rag_ready = book.rag_status == "ready"
    questions_ready = bool(
      book.generated_course and book.generated_course.question_generation_status == "ready"
    )
    quizzes_ready = bool(
      book.generated_course and book.generated_course.quiz_generation_status == "ready"
    )
    flashcards_ready = bool(
      book.generated_course and book.generated_course.flashcard_generation_status == "ready"
    )
    if (
      book.status in (BOOK_STATUS_EXTRACTED, BOOK_STATUS_PARSED)
      and book.extracted_text
      and structure_ready
      and course_ready
      and lessons_ready
      and rag_ready
      and questions_ready
      and quizzes_ready
      and flashcards_ready
    ):
      return None

    existing = (
      DocumentProcessingJob.query.filter(
        DocumentProcessingJob.book_id == book.id,
        DocumentProcessingJob.user_id == user_id,
        DocumentProcessingJob.status.in_(ACTIVE_STATUSES),
      )
      .order_by(DocumentProcessingJob.created_at.desc())
      .first()
    )
    if existing:
      return existing

    job = DocumentProcessingJob(
      user_id=user_id,
      book_id=book.id,
      job_type="document_pipeline",
      status="queued",
      stage="queued",
      progress_percent=5,
      max_attempts=int(current_app.config.get("TEACHER_JOB_MAX_ATTEMPTS", 3)),
    )
    db.session.add(job)
    db.session.commit()
    return job

  @staticmethod
  def get_owned(public_id: str, user_id: int) -> DocumentProcessingJob | None:
    return DocumentProcessingJob.query.filter_by(public_id=public_id, user_id=user_id).first()

  @staticmethod
  def list_owned(user_id: int, limit: int = 20) -> list[DocumentProcessingJob]:
    safe_limit = min(100, max(1, int(limit or 20)))
    return (
      DocumentProcessingJob.query.filter_by(user_id=user_id)
      .order_by(DocumentProcessingJob.created_at.desc())
      .limit(safe_limit)
      .all()
    )

  @classmethod
  def retry(cls, job: DocumentProcessingJob) -> DocumentProcessingJob:
    if job.status not in FINAL_STATUSES:
      return job
    if job.attempts >= job.max_attempts:
      job.attempts = 0
    job.status = "queued"
    job.stage = "queued"
    job.progress_percent = 5
    job.error_code = None
    job.error_message = None
    job.result_json = None
    job.lease_token = None
    job.lease_expires_at = None
    job.completed_at = None
    job.updated_at = utc_now()
    db.session.commit()
    return job

  @classmethod
  def claim_next(cls) -> DocumentProcessingJob | None:
    now = utc_now()
    query = (
      DocumentProcessingJob.query.filter(
        DocumentProcessingJob.attempts < DocumentProcessingJob.max_attempts,
        or_(
          DocumentProcessingJob.status == "queued",
          and_(
            DocumentProcessingJob.status == "processing",
            DocumentProcessingJob.lease_expires_at.isnot(None),
            DocumentProcessingJob.lease_expires_at < now,
          ),
        ),
      )
      .order_by(DocumentProcessingJob.created_at.asc())
      .with_for_update(skip_locked=True)
    )
    try:
      job = query.first()
      if not job:
        db.session.rollback()
        return None
      token = uuid.uuid4().hex
      job.status = "processing"
      job.stage = "starting"
      job.progress_percent = max(10, int(job.progress_percent or 0))
      job.attempts = int(job.attempts or 0) + 1
      job.lease_token = token
      job.lease_expires_at = now + timedelta(
        seconds=int(current_app.config.get("TEACHER_JOB_LEASE_SECONDS", 1800))
      )
      job.started_at = job.started_at or now
      job.updated_at = now
      db.session.commit()
      return job
    except Exception:
      db.session.rollback()
      raise

  @classmethod
  def process_claimed(cls, job: DocumentProcessingJob) -> DocumentProcessingJob:
    lease_token = job.lease_token
    if not lease_token:
      raise RuntimeError("Processing job does not have a lease.")

    def progress(stage: str, percent: int) -> None:
      cls._update_leased(job.id, lease_token, stage=stage, progress_percent=percent)

    try:
      book = DocumentService.get_book(job.book_id, user_id=job.user_id)
      if not book:
        raise LookupError("Book not found.")
      if not (book.extracted_text or "").strip():
        book = DocumentService.extract_document(
          job.book_id,
          user_id=job.user_id,
          progress_callback=progress,
        )
      progress("analyzing_structure", 90)
      structure = DocumentStructureService.detect_for_book(book.id, user_id=job.user_id)
      progress("generating_course", 94)
      generated = CourseGenerationService.generate_from_book(book.id, user_id=job.user_id)
      progress("generating_lessons", 96)
      lesson_result = LessonGenerationService.generate_for_book(
        book.id,
        user_id=job.user_id,
        progress_callback=progress,
      )
      progress("lessons_ready", 97)
      index_result = DocumentRagService.index_book(
        book.id,
        user_id=job.user_id,
        progress_callback=progress,
      )
      question_result = QuestionGenerationService.generate_for_book(
        book.id,
        user_id=job.user_id,
      )
      progress("questions_ready", 99)
      quiz_result = None
      if question_result.questions:
        progress("generating_quizzes", 99)
        quiz_result = LearningQuizEngineService.generate_for_book(
          book.id,
          user_id=job.user_id,
          question_count=int(current_app.config.get("TEACHER_DEFAULT_QUIZ_QUESTION_COUNT", 10)),
        )
      else:
        generated.course.quiz_generation_status = "ready"
        db.session.commit()
      progress("quizzes_ready", 99)
      progress("generating_flashcards", 99)
      flashcard_result = LearningFlashcardService.generate_for_book(
        book.id,
        user_id=job.user_id,
      )
      progress("flashcards_ready", 99)
      progress("preparing_tutor", 99)
      progress("preparing_adaptive_learning", 99)
      AdaptiveLearningService.refresh_book(book.id, job.user_id)
      current = cls._get_leased(job.id, lease_token)
      if not current:
        raise RuntimeError("Processing lease was lost.")
      current.status = "succeeded"
      current.stage = "ready"
      current.progress_percent = 100
      current.result_json = {
        "book_id": book.id,
        "status": book.status,
        "extraction_method": book.extraction_method,
        "page_count": book.page_count,
        "char_count": book.char_count,
        "word_count": book.word_count,
        "ocr_required": book.extraction_method in ("ocr", "hybrid"),
        "structure_ready": True,
        "structure_counts": structure.get("counts") or {},
        "course_ready": True,
        "course_id": generated.course.id,
        "course_counts": generated.counts,
        "course_reused": generated.reused,
        "lessons_ready": True,
        "lesson_count": len(lesson_result.lessons),
        "lessons_created": lesson_result.created_count,
        "lessons_reused": lesson_result.reused_count,
        "rag_ready": True,
        "chunk_count": index_result.chunk_count,
        "embedding_provider": index_result.provider,
        "embedding_model": index_result.model,
        "index_reused": index_result.reused,
        "tutor_ready": True,
        "teach_me_ready": True,
        "adaptive_learning_ready": True,
        "questions_ready": True,
        "question_count": len(question_result.questions),
        "questions_created": question_result.created_count,
        "questions_reused": question_result.reused_count,
        "quizzes_ready": True,
        "quiz_id": quiz_result.quiz.id if quiz_result else None,
        "quiz_question_count": quiz_result.quiz.questions.count() if quiz_result else 0,
        "quiz_reused": quiz_result.reused if quiz_result else False,
        "flashcards_ready": True,
        "flashcard_count": len(flashcard_result.cards),
        "flashcards_created": flashcard_result.created_count,
        "flashcards_reused": flashcard_result.reused_count,
      }
      current.error_code = None
      current.error_message = None
      current.completed_at = utc_now()
      current.lease_token = None
      current.lease_expires_at = None
      current.updated_at = utc_now()
      db.session.commit()
      return current
    except Exception as exc:
      logger.exception("Learning document job failed: %s", job.public_id)
      db.session.rollback()
      current = cls._get_leased(job.id, lease_token)
      if not current:
        raise
      current.status = "failed"
      current.stage = "failed"
      current.error_code = cls._safe_error_code(exc)
      current.error_message = cls._safe_error_message(exc)
      current.completed_at = utc_now()
      current.lease_token = None
      current.lease_expires_at = None
      current.updated_at = utc_now()
      db.session.commit()
      return current

  @classmethod
  def _update_leased(
    cls,
    job_id: int,
    lease_token: str,
    *,
    stage: str,
    progress_percent: int,
  ) -> None:
    job = cls._get_leased(job_id, lease_token)
    if not job:
      raise RuntimeError("Processing lease was lost.")
    job.stage = stage[:60]
    job.progress_percent = max(job.progress_percent or 0, min(99, int(progress_percent)))
    job.lease_expires_at = utc_now() + timedelta(
      seconds=int(current_app.config.get("TEACHER_JOB_LEASE_SECONDS", 1800))
    )
    job.updated_at = utc_now()
    db.session.commit()

  @staticmethod
  def _get_leased(job_id: int, lease_token: str) -> DocumentProcessingJob | None:
    return DocumentProcessingJob.query.filter_by(
      id=job_id,
      status="processing",
      lease_token=lease_token,
    ).first()

  @staticmethod
  def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
      return "stored_document_missing"
    if isinstance(exc, TimeoutError):
      return "processing_timeout"
    return "document_processing_failed"

  @staticmethod
  def _safe_error_message(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
      return "The uploaded document is no longer available. Please upload it again."
    message = str(exc).strip()
    allowed = (
      "No readable text found",
      "OCR timed out",
      "Stored document is unavailable",
      "PyMuPDF is required",
    )
    if message.startswith(allowed):
      return message[:500]
    return "The document could not be processed. Retry the job or upload a clearer PDF."
