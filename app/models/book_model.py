"""AI Medical Teacher — uploaded medical documents and parsed chapters.

Module 1: raw file + extracted text/structure
Module 2: chapters + content analysis (Book Parser)
"""

from __future__ import annotations

import uuid

from app.extensions import db
from app.utils import utc_now


BOOK_STATUS_UPLOADED = "uploaded"
BOOK_STATUS_PROCESSING = "processing"
BOOK_STATUS_EXTRACTED = "extracted"
BOOK_STATUS_PARSING = "parsing"
BOOK_STATUS_PARSED = "parsed"
BOOK_STATUS_FAILED = "failed"


class Book(db.Model):
  """Medical textbook / lecture notes / clinical guideline uploaded by a user."""

  __tablename__ = "books"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

  title = db.Column(db.String(300), nullable=False)
  author = db.Column(db.String(200), nullable=True)
  medical_subject = db.Column(db.String(150), nullable=True)
  description = db.Column(db.Text, nullable=True)

  original_filename = db.Column(db.String(255), nullable=False)
  stored_filename = db.Column(db.String(255), nullable=False)
  file_path = db.Column(db.String(500), nullable=False)
  storage_backend = db.Column(db.String(40), nullable=False, default="local")
  storage_key = db.Column(db.String(500), nullable=True, index=True)
  file_type = db.Column(db.String(20), nullable=False)  # pdf | docx | txt
  mime_type = db.Column(db.String(100), nullable=True)
  file_size = db.Column(db.Integer, nullable=True)
  content_hash = db.Column(db.String(64), nullable=True, index=True)

  status = db.Column(db.String(30), default=BOOK_STATUS_UPLOADED, index=True)
  extracted_text = db.Column(db.Text(length=4294967295), nullable=True)
  extraction_method = db.Column(db.String(40), nullable=True)
  page_count = db.Column(db.Integer, nullable=True)
  char_count = db.Column(db.Integer, nullable=True)
  word_count = db.Column(db.Integer, nullable=True)
  ocr_confidence = db.Column(db.Float, nullable=True)
  structure_json = db.Column(db.JSON, nullable=True)
  error_message = db.Column(db.Text, nullable=True)
  rag_status = db.Column(db.String(30), nullable=True, index=True)
  rag_provider = db.Column(db.String(40), nullable=True)
  rag_model = db.Column(db.String(120), nullable=True)
  rag_chunk_count = db.Column(db.Integer, nullable=True)
  rag_indexed_at = db.Column(db.DateTime, nullable=True)
  rag_error = db.Column(db.String(500), nullable=True)

  # Module 2 — Book Parser
  analysis_json = db.Column(db.JSON, nullable=True)
  parse_method = db.Column(db.String(40), nullable=True)  # heuristic | gemini | openai | hybrid
  chapter_count = db.Column(db.Integer, nullable=True)
  parsed_at = db.Column(db.DateTime, nullable=True)

  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  user = db.relationship("User", backref=db.backref("books", lazy="dynamic"))
  chapters = db.relationship(
    "Chapter",
    back_populates="book",
    lazy="dynamic",
    cascade="all, delete-orphan",
    order_by="Chapter.order_index",
  )
  processing_jobs = db.relationship(
    "DocumentProcessingJob",
    back_populates="book",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  generated_course = db.relationship(
    "Course",
    back_populates="source_book",
    uselist=False,
    cascade="all, delete-orphan",
    single_parent=True,
  )
  document_chunks = db.relationship(
    "DocumentChunk",
    back_populates="book",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  tutor_sessions = db.relationship(
    "TutorSession",
    back_populates="book",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )
  question_banks = db.relationship(
    "Quiz",
    back_populates="source_book",
    lazy="dynamic",
    cascade="all, delete-orphan",
    foreign_keys="Quiz.source_book_id",
  )
  learning_flashcards = db.relationship(
    "HubFlashcard",
    foreign_keys="HubFlashcard.book_id",
    cascade="all, delete-orphan",
  )

  def to_dict(
    self,
    include_text: bool = False,
    include_structure: bool = False,
    include_analysis: bool = False,
    include_chapters: bool = False,
  ):
    data = {
      "id": self.id,
      "user_id": self.user_id,
      "title": self.title,
      "author": self.author,
      "medical_subject": self.medical_subject,
      "description": self.description,
      "original_filename": self.original_filename,
      "stored_filename": self.stored_filename,
      "storage_backend": self.storage_backend or "local",
      "file_type": self.file_type,
      "mime_type": self.mime_type,
      "file_size": self.file_size,
      "content_hash": self.content_hash,
      "status": self.status,
      "extraction_method": self.extraction_method,
      "page_count": self.page_count,
      "char_count": self.char_count,
      "word_count": self.word_count,
      "ocr_confidence": self.ocr_confidence,
      "rag_status": self.rag_status,
      "rag_provider": self.rag_provider,
      "rag_model": self.rag_model,
      "rag_chunk_count": int(self.rag_chunk_count or 0),
      "rag_indexed_at": self.rag_indexed_at.isoformat() if self.rag_indexed_at else None,
      "rag_error": self.rag_error,
      "parse_method": self.parse_method,
      "chapter_count": self.chapter_count if self.chapter_count is not None else self.chapters.count(),
      "parsed_at": self.parsed_at.isoformat() if self.parsed_at else None,
      "error_message": self.error_message,
      "has_extracted_text": bool(self.extracted_text),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_text:
      data["extracted_text"] = self.extracted_text
    if include_structure:
      data["structure_json"] = self.structure_json
    if include_analysis:
      data["analysis_json"] = self.analysis_json
    if include_chapters:
      data["chapters"] = [c.to_dict() for c in self.chapters.order_by(Chapter.order_index)]
    return data


class DocumentProcessingJob(db.Model):
  """Durable background work for uploaded learning documents."""

  __tablename__ = "document_processing_jobs"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  public_id = db.Column(
    db.String(36),
    nullable=False,
    unique=True,
    index=True,
    default=lambda: str(uuid.uuid4()),
  )
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
  book_id = db.Column(
    db.Integer,
    db.ForeignKey("books.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  job_type = db.Column(db.String(40), nullable=False, default="extract")
  status = db.Column(db.String(30), nullable=False, default="queued", index=True)
  stage = db.Column(db.String(60), nullable=False, default="queued")
  progress_percent = db.Column(db.Integer, nullable=False, default=0)
  attempts = db.Column(db.Integer, nullable=False, default=0)
  max_attempts = db.Column(db.Integer, nullable=False, default=3)
  lease_token = db.Column(db.String(64), nullable=True, index=True)
  lease_expires_at = db.Column(db.DateTime, nullable=True, index=True)
  error_code = db.Column(db.String(80), nullable=True)
  error_message = db.Column(db.String(500), nullable=True)
  result_json = db.Column(db.JSON, nullable=True)
  started_at = db.Column(db.DateTime, nullable=True)
  completed_at = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now, index=True)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  book = db.relationship("Book", back_populates="processing_jobs")
  user = db.relationship("User")

  __table_args__ = (
    db.Index("ix_document_jobs_claim", "status", "lease_expires_at", "created_at"),
  )

  def to_dict(self, include_book: bool = True):
    data = {
      "id": self.public_id,
      "book_id": self.book_id,
      "job_type": self.job_type,
      "status": self.status,
      "stage": self.stage,
      "progress_percent": max(0, min(100, int(self.progress_percent or 0))),
      "attempts": int(self.attempts or 0),
      "max_attempts": int(self.max_attempts or 0),
      "error_code": self.error_code,
      "error_message": self.error_message,
      "result": self.result_json or None,
      "started_at": self.started_at.isoformat() if self.started_at else None,
      "completed_at": self.completed_at.isoformat() if self.completed_at else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_book and self.book:
      data["book"] = self.book.to_dict()
    return data


class Chapter(db.Model):
  """A chapter / major section detected from an uploaded book (Module 2)."""

  __tablename__ = "chapters"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id"), nullable=False, index=True)
  order_index = db.Column(db.Integer, default=0, nullable=False)
  title = db.Column(db.String(300), nullable=False)
  summary = db.Column(db.Text, nullable=True)
  content = db.Column(db.Text(length=4294967295), nullable=True)
  page_start = db.Column(db.Integer, nullable=True)
  page_end = db.Column(db.Integer, nullable=True)
  word_count = db.Column(db.Integer, nullable=True)

  topics = db.Column(db.JSON, nullable=True)  # list[str]
  subtopics = db.Column(db.JSON, nullable=True)
  key_concepts = db.Column(db.JSON, nullable=True)
  learning_objectives = db.Column(db.JSON, nullable=True)
  # Provenance: document vs ai_assisted educational labeling
  source = db.Column(db.String(40), default="document")  # document | hybrid | ai_assisted

  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  book = db.relationship("Book", back_populates="chapters")

  def to_dict(self, include_content: bool = False):
    data = {
      "id": self.id,
      "book_id": self.book_id,
      "order_index": self.order_index,
      "title": self.title,
      "summary": self.summary,
      "page_start": self.page_start,
      "page_end": self.page_end,
      "word_count": self.word_count,
      "topics": self.topics or [],
      "subtopics": self.subtopics or [],
      "key_concepts": self.key_concepts or [],
      "learning_objectives": self.learning_objectives or [],
      "source": self.source,
      "has_content": bool(self.content),
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_content:
      data["content"] = self.content
    else:
      data["content_preview"] = (self.content or "")[:400]
    return data
