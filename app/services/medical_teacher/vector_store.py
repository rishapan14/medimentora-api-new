"""Replaceable vector-store interface with a dependency-free SQL implementation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from app.extensions import db
from app.models.rag_model import ChunkEmbedding, DocumentChunk


@dataclass(frozen=True)
class VectorMatch:
  chunk: DocumentChunk
  score: float


class VectorStore(Protocol):
  def upsert(self, chunk: DocumentChunk, provider: str, model: str, vector: list[float]) -> None: ...
  def search(self, *, user_id: int, book_id: int, provider: str, model: str, query_vector: list[float], limit: int, topic_id: int | None = None) -> list[VectorMatch]: ...


class SqlJsonVectorStore:
  def upsert(self, chunk: DocumentChunk, provider: str, model: str, vector: list[float]) -> None:
    record = ChunkEmbedding.query.filter_by(chunk_id=chunk.id, provider=provider, model=model).first()
    if record is None:
      record = ChunkEmbedding(chunk_id=chunk.id, provider=provider, model=model)
      db.session.add(record)
    record.dimension = len(vector)
    record.vector_json = [float(value) for value in vector]

  def search(
    self,
    *,
    user_id: int,
    book_id: int,
    provider: str,
    model: str,
    query_vector: list[float],
    limit: int,
    topic_id: int | None = None,
  ) -> list[VectorMatch]:
    query = (
      db.session.query(ChunkEmbedding, DocumentChunk)
      .join(DocumentChunk, DocumentChunk.id == ChunkEmbedding.chunk_id)
      .filter(
        DocumentChunk.user_id == user_id,
        DocumentChunk.book_id == book_id,
        ChunkEmbedding.provider == provider,
        ChunkEmbedding.model == model,
      )
    )
    if topic_id is not None:
      query = query.filter(DocumentChunk.topic_id == topic_id)
    matches = []
    for embedding, chunk in query.all():
      vector = embedding.vector_json or []
      if len(vector) != len(query_vector):
        continue
      denominator = math.sqrt(math.fsum(v * v for v in vector)) * math.sqrt(math.fsum(v * v for v in query_vector))
      score = math.fsum(left * right for left, right in zip(vector, query_vector)) / denominator if denominator else 0.0
      matches.append(VectorMatch(chunk=chunk, score=max(-1.0, min(1.0, float(score)))))
    matches.sort(key=lambda item: (-item.score, item.chunk.chunk_index))
    return matches[:limit]
