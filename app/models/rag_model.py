"""Document chunks and provider-agnostic embedding records for Learning RAG."""

from __future__ import annotations

import uuid

from app.extensions import db
from app.utils import utc_now


class DocumentChunk(db.Model):
  """A source-grounded slice of an uploaded learning document."""

  __tablename__ = "document_chunks"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  public_id = db.Column(db.String(36), nullable=False, unique=True, index=True, default=lambda: str(uuid.uuid4()))
  user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
  book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
  course_id = db.Column(db.Integer, db.ForeignKey("courses.id", ondelete="CASCADE"), nullable=True, index=True)
  topic_id = db.Column(db.Integer, db.ForeignKey("course_topics.id", ondelete="SET NULL"), nullable=True, index=True)
  lesson_id = db.Column(db.Integer, db.ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
  chunk_index = db.Column(db.Integer, nullable=False)
  content = db.Column(db.Text(length=16777215), nullable=False)
  content_hash = db.Column(db.String(64), nullable=False, index=True)
  document_hash = db.Column(db.String(64), nullable=True, index=True)
  char_count = db.Column(db.Integer, nullable=False, default=0)
  word_count = db.Column(db.Integer, nullable=False, default=0)
  page_start = db.Column(db.Integer, nullable=True, index=True)
  page_end = db.Column(db.Integer, nullable=True)
  source_json = db.Column(db.JSON, nullable=False)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  book = db.relationship("Book", back_populates="document_chunks")
  course = db.relationship("Course")
  topic = db.relationship("CourseTopic")
  lesson = db.relationship("Lesson")
  embeddings = db.relationship(
    "ChunkEmbedding",
    back_populates="chunk",
    lazy="dynamic",
    cascade="all, delete-orphan",
  )

  __table_args__ = (
    db.UniqueConstraint("book_id", "chunk_index", name="uq_document_chunk_index"),
    db.Index("ix_document_chunks_owner_book_page", "user_id", "book_id", "page_start"),
  )

  def to_dict(self, include_content: bool = True):
    data = {
      "id": self.public_id,
      "book_id": self.book_id,
      "course_id": self.course_id,
      "topic_id": self.topic_id,
      "lesson_id": self.lesson_id,
      "chunk_index": self.chunk_index,
      "char_count": self.char_count,
      "word_count": self.word_count,
      "page_start": self.page_start,
      "page_end": self.page_end,
      "source": self.source_json,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
    if include_content:
      data["content"] = self.content
    else:
      data["content_preview"] = (self.content or "")[:300]
    return data


class ChunkEmbedding(db.Model):
  """An embedding vector stored behind the VectorStore abstraction."""

  __tablename__ = "chunk_embeddings"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  chunk_id = db.Column(
    db.Integer,
    db.ForeignKey("document_chunks.id", ondelete="CASCADE"),
    nullable=False,
    index=True,
  )
  provider = db.Column(db.String(40), nullable=False, index=True)
  model = db.Column(db.String(120), nullable=False, index=True)
  dimension = db.Column(db.Integer, nullable=False)
  vector_json = db.Column(db.JSON, nullable=False)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  chunk = db.relationship("DocumentChunk", back_populates="embeddings")

  __table_args__ = (
    db.UniqueConstraint("chunk_id", "provider", "model", name="uq_chunk_embedding_provider_model"),
    db.Index("ix_chunk_embeddings_provider_model", "provider", "model"),
  )

  def metadata_dict(self):
    return {
      "provider": self.provider,
      "model": self.model,
      "dimension": self.dimension,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }

