"""Page- and topic-aware chunking with explicit source provenance."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from flask import current_app

from app.models.book_model import Book
from app.models.course_model import CourseTopic


@dataclass(frozen=True)
class ChunkDraft:
  chunk_index: int
  content: str
  content_hash: str
  page_start: int
  page_end: int
  course_id: int | None
  topic_id: int | None
  lesson_id: int | None
  source: dict


class DocumentChunkingService:
  @classmethod
  def build(cls, book: Book) -> list[ChunkDraft]:
    pages = cls._pages(book)
    if not pages:
      raise ValueError("Document text must be extracted before indexing.")
    course = book.generated_course
    topics = (
      CourseTopic.query.filter_by(course_id=course.id).order_by(CourseTopic.order_index, CourseTopic.id).all()
      if course else []
    )
    size = max(400, int(current_app.config.get("TEACHER_CHUNK_SIZE_CHARS", 1800)))
    overlap = max(0, min(size // 2, int(current_app.config.get("TEACHER_CHUNK_OVERLAP_CHARS", 250))))
    drafts: list[ChunkDraft] = []
    for page_number, text in pages:
      for segment, topic in cls._topic_segments(page_number, text, topics):
        for piece in cls._split(segment, size, overlap):
          source = {
            "source_kind": "uploaded_document",
            "document_id": book.id,
            "document_title": book.title,
            "page_numbers": [page_number],
            "page_start": page_number,
            "page_end": page_number,
            "course_id": course.id if course else None,
            "course_title": course.title if course else None,
            "topic_id": topic.id if topic else None,
            "topic_title": topic.title if topic else None,
            "lesson_id": topic.lesson.id if topic and topic.lesson else None,
          }
          drafts.append(
            ChunkDraft(
              chunk_index=len(drafts),
              content=piece,
              content_hash=hashlib.sha256(piece.encode("utf-8")).hexdigest(),
              page_start=page_number,
              page_end=page_number,
              course_id=source["course_id"],
              topic_id=source["topic_id"],
              lesson_id=source["lesson_id"],
              source=source,
            )
          )
    return drafts

  @staticmethod
  def _pages(book: Book) -> list[tuple[int, str]]:
    rows = []
    for index, page in enumerate((book.structure_json or {}).get("pages") or []):
      if not isinstance(page, dict):
        continue
      text = str(page.get("text") or "").strip()
      if text:
        rows.append((int(page.get("page_number") or index + 1), text))
    if not rows and (book.extracted_text or "").strip():
      rows.append((1, book.extracted_text.strip()))
    return rows

  @staticmethod
  def _topic_segments(page_number: int, text: str, topics: list[CourseTopic]):
    covering = [
      topic for topic in topics
      if int(topic.page_start or 1) <= page_number <= int(topic.page_end or topic.page_start or page_number)
    ]
    positions = []
    lower = text.casefold()
    for topic in covering:
      position = lower.find(topic.title.casefold())
      if position >= 0:
        positions.append((position, topic))
    positions.sort(key=lambda item: (item[0], item[1].id or 0))
    if not positions:
      topic = covering[-1] if covering else None
      return [(text, topic)]
    segments = []
    if positions[0][0] > 0 and text[:positions[0][0]].strip():
      segments.append((text[:positions[0][0]].strip(), covering[-1] if covering else None))
    for index, (start, topic) in enumerate(positions):
      end = positions[index + 1][0] if index + 1 < len(positions) else len(text)
      segment = text[start:end].strip()
      if segment:
        segments.append((segment, topic))
    return segments

  @staticmethod
  def _split(text: str, size: int, overlap: int) -> list[str]:
    cleaned = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    if len(cleaned) <= size:
      return [cleaned] if cleaned else []
    pieces = []
    start = 0
    while start < len(cleaned):
      end = min(len(cleaned), start + size)
      if end < len(cleaned):
        boundary = max(cleaned.rfind("\n", start + size // 2, end), cleaned.rfind(" ", start + size // 2, end))
        if boundary > start:
          end = boundary
      piece = cleaned[start:end].strip()
      if piece:
        pieces.append(piece)
      if end >= len(cleaned):
        break
      start = max(start + 1, end - overlap)
    return pieces
