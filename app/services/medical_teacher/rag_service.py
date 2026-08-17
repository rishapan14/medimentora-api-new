"""Grounded document indexing and retrieval for the learning engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from app.extensions import db
from app.models.book_model import Book
from app.models.rag_model import ChunkEmbedding, DocumentChunk
from app.services.medical_teacher.chunking_service import DocumentChunkingService
from app.services.medical_teacher.embedding_service import get_embedding_provider
from app.services.medical_teacher.vector_store import SqlJsonVectorStore
from app.utils import utc_now

ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class IndexResult:
  book: Book
  chunk_count: int
  provider: str
  model: str
  dimension: int
  reused: bool

  def to_dict(self):
    return {
      "book_id": self.book.id,
      "status": self.book.rag_status,
      "chunk_count": self.chunk_count,
      "provider": self.provider,
      "model": self.model,
      "dimension": self.dimension,
      "reused": self.reused,
      "indexed_at": self.book.rag_indexed_at.isoformat() if self.book.rag_indexed_at else None,
      "grounding": {
        "source_policy": "uploaded_document_only",
        "answer_generated": False,
      },
    }


class DocumentRagService:
  @classmethod
  def index_book(
    cls,
    book_id: int,
    user_id: int,
    *,
    force: bool = False,
    progress_callback: ProgressCallback | None = None,
  ) -> IndexResult:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    if not book.generated_course or book.generated_course.lesson_generation_status != "ready":
      raise ValueError("Lessons must be generated before indexing the document.")
    provider = get_embedding_provider()
    if not force and cls._is_current(book, provider.name, provider.model):
      return IndexResult(
        book=book,
        chunk_count=int(book.rag_chunk_count or 0),
        provider=provider.name,
        model=provider.model,
        dimension=cls._stored_dimension(book, provider.name, provider.model),
        reused=True,
      )

    book.rag_status = "indexing"
    book.rag_provider = provider.name
    book.rag_model = provider.model
    book.rag_error = None
    db.session.commit()
    try:
      if progress_callback:
        progress_callback("creating_chunks", 97)
      drafts = DocumentChunkingService.build(book)
      if not drafts:
        raise ValueError("No readable document chunks were produced.")

      for old_chunk in DocumentChunk.query.filter_by(book_id=book.id).all():
        db.session.delete(old_chunk)
      db.session.flush()
      chunks = []
      for draft in drafts:
        chunk = DocumentChunk(
          user_id=user_id,
          book_id=book.id,
          course_id=draft.course_id,
          topic_id=draft.topic_id,
          lesson_id=draft.lesson_id,
          chunk_index=draft.chunk_index,
          content=draft.content,
          content_hash=draft.content_hash,
          document_hash=book.content_hash,
          char_count=len(draft.content),
          word_count=len(draft.content.split()),
          page_start=draft.page_start,
          page_end=draft.page_end,
          source_json=draft.source,
        )
        db.session.add(chunk)
        chunks.append(chunk)
      db.session.flush()

      if progress_callback:
        progress_callback("generating_embeddings", 98)
      store = SqlJsonVectorStore()
      batch_size = 32
      for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        vectors = provider.embed_texts([chunk.content for chunk in batch])
        if len(vectors) != len(batch):
          raise RuntimeError("Embedding provider returned an incomplete batch.")
        for chunk, vector in zip(batch, vectors):
          if not vector:
            raise RuntimeError("Embedding provider returned an empty vector.")
          store.upsert(chunk, provider.name, provider.model, vector)

      book.rag_status = "ready"
      book.rag_provider = provider.name
      book.rag_model = provider.model
      book.rag_chunk_count = len(chunks)
      book.rag_indexed_at = utc_now()
      book.rag_error = None
      db.session.commit()
      if progress_callback:
        progress_callback("index_ready", 99)
      return IndexResult(
        book=book,
        chunk_count=len(chunks),
        provider=provider.name,
        model=provider.model,
        dimension=int(provider.dimension),
        reused=False,
      )
    except Exception as exc:
      db.session.rollback()
      failed = Book.query.filter_by(id=book_id, user_id=user_id).first()
      if failed:
        failed.rag_status = "failed"
        failed.rag_error = cls._safe_error(exc)
        db.session.commit()
      raise

  @classmethod
  def search(
    cls,
    book_id: int,
    user_id: int,
    query: str,
    *,
    limit: int = 5,
    topic_id: int | None = None,
  ) -> dict:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    clean_query = " ".join(str(query or "").split())
    if len(clean_query) < 2 or len(clean_query) > 1000:
      raise ValueError("Search query must contain between 2 and 1000 characters.")
    if book.rag_status != "ready" or not book.rag_provider or not book.rag_model:
      raise ValueError("Document index is not ready.")
    safe_limit = max(1, min(20, int(limit or 5)))
    dimension = cls._stored_dimension(book, book.rag_provider, book.rag_model)
    provider = get_embedding_provider(book.rag_provider, book.rag_model, dimension)
    vectors = provider.embed_texts([clean_query])
    if not vectors or not vectors[0]:
      raise RuntimeError("Embedding provider returned an empty query vector.")
    matches = SqlJsonVectorStore().search(
      user_id=user_id,
      book_id=book.id,
      provider=book.rag_provider,
      model=book.rag_model,
      query_vector=vectors[0],
      limit=safe_limit,
      topic_id=topic_id,
    )
    return {
      "query": clean_query,
      "book_id": book.id,
      "provider": book.rag_provider,
      "model": book.rag_model,
      "matches": [
        {"score": round(match.score, 6), "chunk": match.chunk.to_dict(include_content=True)}
        for match in matches
      ],
      "grounding": {
        "source_policy": "uploaded_document_only",
        "answer_generated": False,
        "note": "Results are source passages, not medical advice or an AI-generated answer.",
      },
    }

  @staticmethod
  def status(book_id: int, user_id: int) -> dict:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    return {
      "book_id": book.id,
      "status": book.rag_status or "not_indexed",
      "provider": book.rag_provider,
      "model": book.rag_model,
      "chunk_count": int(book.rag_chunk_count or 0),
      "indexed_at": book.rag_indexed_at.isoformat() if book.rag_indexed_at else None,
      "error": book.rag_error,
    }

  @staticmethod
  def _stored_dimension(book: Book, provider: str, model: str) -> int:
    record = (
      ChunkEmbedding.query.join(DocumentChunk)
      .filter(
        DocumentChunk.book_id == book.id,
        ChunkEmbedding.provider == provider,
        ChunkEmbedding.model == model,
      )
      .first()
    )
    return int(record.dimension if record else 0)

  @classmethod
  def _is_current(cls, book: Book, provider: str, model: str) -> bool:
    if book.rag_status != "ready" or book.rag_provider != provider or book.rag_model != model:
      return False
    expected = int(book.rag_chunk_count or 0)
    if expected < 1:
      return False
    chunks = DocumentChunk.query.filter_by(book_id=book.id, document_hash=book.content_hash).count()
    embeddings = (
      ChunkEmbedding.query.join(DocumentChunk)
      .filter(
        DocumentChunk.book_id == book.id,
        ChunkEmbedding.provider == provider,
        ChunkEmbedding.model == model,
      )
      .count()
    )
    return chunks == expected and embeddings == expected

  @staticmethod
  def _safe_error(exc: Exception) -> str:
    message = str(exc).strip()
    allowed = (
      "OPENAI_API_KEY is required",
      "Unsupported embedding provider",
      "No readable document chunks",
      "Embedding provider returned",
    )
    if message.startswith(allowed):
      return message[:500]
    return "The document search index could not be created. Check the embedding configuration and retry."
