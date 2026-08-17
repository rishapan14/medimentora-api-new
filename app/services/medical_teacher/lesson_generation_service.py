"""Phase 5: generate cached, source-grounded lessons for document topics."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.book_model import Book
from app.models.course_model import Course, CourseTopic, Lesson
from app.services.medical_teacher.ai_client import TeacherAIClient
from app.services.medical_teacher.course_generation_service import CourseGenerationService
from app.utils import utc_now


LESSON_AI_SYSTEM_PROMPT = (
  "You create educational lessons for healthcare students using ONLY the supplied uploaded-document text. "
  "Do not add medical facts, diagnoses, drug doses, or recommendations absent from the source. "
  "Every non-empty content field must be supported by verbatim quotes in evidence_map. "
  "If a requested section is unsupported, return an empty string or empty list. "
  "Return valid JSON only. Educational content is not personal medical advice."
)


@dataclass
class LessonGenerationResult:
  course: Course
  lessons: list[Lesson]
  created_count: int
  reused_count: int

  def to_dict(self, include_content: bool = False) -> dict[str, Any]:
    return {
      "course_id": self.course.id,
      "status": self.course.lesson_generation_status,
      "created_count": self.created_count,
      "reused_count": self.reused_count,
      "total": len(self.lessons),
      "lessons": [lesson.to_dict() if include_content else LessonGenerationService.lesson_summary(lesson) for lesson in self.lessons],
    }


class LessonGenerationService:
  """Generate one idempotent lesson per persisted topic/subtopic."""

  @classmethod
  def generate_for_book(
    cls,
    book_id: int,
    user_id: int,
    *,
    difficulty: str = "intermediate",
    use_ai: bool | None = None,
    progress_callback=None,
  ) -> LessonGenerationResult:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    course = CourseGenerationService.get_owned_for_book(book.id, user_id)
    if not course or course.generation_status != "ready":
      raise ValueError("Course outline must be generated before lesson generation.")

    normalized_difficulty = cls._difficulty(difficulty)
    ai_enabled = (
      bool(current_app.config.get("TEACHER_LESSON_USE_AI", False))
      if use_ai is None
      else bool(use_ai)
    )
    topics = (
      CourseTopic.query.filter_by(course_id=course.id)
      .order_by(CourseTopic.module_id, CourseTopic.parent_topic_id, CourseTopic.order_index, CourseTopic.id)
      .all()
    )
    if not topics:
      course.lesson_generation_status = "ready"
      db.session.commit()
      return LessonGenerationResult(course, [], 0, 0)

    existing = {
      lesson.topic_id: lesson
      for lesson in Lesson.query.filter(
        Lesson.course_id == course.id,
        Lesson.topic_id.isnot(None),
      ).all()
    }
    lessons: list[Lesson] = []
    created_count = 0
    reused_count = 0
    course.lesson_generation_status = "generating"
    db.session.flush()

    try:
      for index, topic in enumerate(topics, start=1):
        cached = existing.get(topic.id)
        if cached and cached.content_json and cached.source_hash == book.content_hash:
          lessons.append(cached)
          reused_count += 1
        else:
          lesson = cls._generate_topic_lesson(
            book,
            course,
            topic,
            topics,
            order_index=index,
            difficulty=normalized_difficulty,
            use_ai=ai_enabled,
          )
          db.session.add(lesson)
          lessons.append(lesson)
          created_count += 1
        if progress_callback:
          percent = 96 + round((index / max(1, len(topics))) * 3)
          progress_callback("generating_lessons", min(99, percent))

      course.lesson_generation_status = "ready"
      course.duration_hours = round(sum(int(item.duration_minutes or 0) for item in lessons) / 60, 2)
      course.updated_at = utc_now()
      db.session.commit()
    except IntegrityError:
      db.session.rollback()
      concurrent = Lesson.query.filter_by(course_id=course.id).filter(Lesson.topic_id.isnot(None)).all()
      if len(concurrent) == len(topics):
        course = db.session.get(Course, course.id)
        if course:
          course.lesson_generation_status = "ready"
          db.session.commit()
          return LessonGenerationResult(course, concurrent, 0, len(concurrent))
      raise
    except Exception:
      db.session.rollback()
      raise

    return LessonGenerationResult(course, lessons, created_count, reused_count)

  @classmethod
  def list_owned_for_book(cls, book_id: int, user_id: int) -> LessonGenerationResult:
    course = CourseGenerationService.get_owned_for_book(book_id, user_id)
    if not course:
      raise LookupError("Course not found.")
    lessons = Lesson.query.filter_by(course_id=course.id).order_by(Lesson.order_index, Lesson.id).all()
    return LessonGenerationResult(course, lessons, 0, len(lessons))

  @classmethod
  def _generate_topic_lesson(
    cls,
    book: Book,
    course: Course,
    topic: CourseTopic,
    all_topics: list[CourseTopic],
    *,
    order_index: int,
    difficulty: str,
    use_ai: bool,
  ) -> Lesson:
    source_text, source_pages = cls._source_slice(book, topic, all_topics)
    if not source_text.strip():
      raise ValueError(f"No grounded source text is available for topic '{topic.title}'.")
    deterministic = cls._deterministic_content(book, topic, all_topics, source_text, source_pages, difficulty)
    content_json = deterministic
    method = "deterministic_grounded"

    if use_ai:
      ai_data, provider = cls._ai_content(topic, source_text, deterministic, difficulty)
      if ai_data and provider != "none":
        content_json = cls._merge_ai_content(deterministic, ai_data, provider)
        method = f"{provider}_grounded"

    markdown = cls._to_markdown(topic.title, content_json)
    word_count = len(re.findall(r"\b\w+\b", markdown))
    duration = max(5, min(45, round(word_count / 180) or 5))
    concepts = [
      str(item.get("title"))
      for item in topic.important_concepts or []
      if isinstance(item, dict) and item.get("title")
    ]
    return Lesson(
      course_id=course.id,
      module_id=topic.module_id,
      topic_id=topic.id,
      title=topic.title[:200],
      content=markdown,
      summary=str(content_json.get("overview") or "")[:2000],
      order_index=order_index,
      duration_minutes=duration,
      topic_tags=[topic.title, *concepts][:20],
      content_json=content_json,
      source_json={
        "document_id": book.id,
        "topic_id": topic.id,
        "page_start": topic.page_start,
        "page_end": topic.page_end,
        "page_numbers": source_pages,
        "source_kind": "uploaded_document",
      },
      source_hash=book.content_hash,
      origin="uploaded_document",
      generation_method=method,
      difficulty_level=difficulty,
      generated_at=utc_now(),
      is_published=True,
    )

  @classmethod
  def _deterministic_content(
    cls,
    book: Book,
    topic: CourseTopic,
    all_topics: list[CourseTopic],
    source_text: str,
    source_pages: list[int],
    difficulty: str,
  ) -> dict[str, Any]:
    structure = (book.structure_json or {}).get("detected_structure") or {}
    overview = cls._overview(source_text, topic.title)
    objectives = cls._topic_values(topic.learning_objectives, "text")
    concepts = cls._topic_values(topic.important_concepts, "title")
    definitions = cls._page_evidence(structure.get("definitions") or [], topic)
    examples = cls._page_evidence(structure.get("examples") or [], topic)
    exam_items = cls._page_evidence(structure.get("exam_relevant_concepts") or [], topic)
    bullet_points = cls._source_bullets(source_text)
    related = [item.title for item in all_topics if item.id != topic.id][:8]
    revision = concepts[:8] + [
      f"{item.get('term')}: {item.get('definition')}"
      for item in definitions[:5]
      if item.get("term") and item.get("definition")
    ]
    return {
      "title": topic.title,
      "difficulty": difficulty,
      "overview": overview,
      "learning_objectives": objectives,
      "key_concepts": concepts,
      "important_definitions": definitions,
      "detailed_explanation": source_text,
      "examples": [item.get("text") for item in examples if item.get("text")],
      "key_points": cls._unique(concepts + bullet_points)[:15],
      "common_mistakes": [
        item.get("text")
        for item in exam_items
        if item.get("text") and re.search(r"(?i)mistake|avoid|confus", item.get("text"))
      ],
      "exam_tips": [item.get("text") for item in exam_items if item.get("text")],
      "quick_revision": revision[:12],
      "related_topics": related,
      "source_references": [
        {
          "document_id": book.id,
          "document_title": book.title,
          "topic_id": topic.id,
          "page_numbers": source_pages,
          "page_start": topic.page_start,
          "page_end": topic.page_end,
          "excerpt": source_text[:500],
        }
      ],
      "grounding": {
        "source_policy": "uploaded_document_only",
        "ai_generated": False,
        "educational_only": True,
        "note": "The detailed explanation is extracted from the uploaded material and is not personal medical advice.",
      },
    }

  @classmethod
  def _ai_content(
    cls,
    topic: CourseTopic,
    source_text: str,
    deterministic: dict[str, Any],
    difficulty: str,
  ) -> tuple[dict[str, Any] | None, str]:
    prompt = (
      f"Create a {difficulty} lesson for the topic: {topic.title}\n"
      "Return JSON with: overview (string), learning_objectives (array), key_concepts (array), "
      "detailed_explanation (string), examples (array), key_points (array), common_mistakes (array), "
      "exam_tips (array), quick_revision (array), related_topics (array), source_evidence (array of "
      "verbatim quotes copied from the source), and evidence_map (an object mapping every non-empty "
      "content field to one or more verbatim supporting quotes). Do not provide a section if unsupported.\n\n"
      f"Existing document-backed signals:\n{deterministic}\n\n"
      f"Uploaded-document source:\n{source_text}"
    )
    data, provider = TeacherAIClient.complete_json(LESSON_AI_SYSTEM_PROMPT, prompt)
    if not data or not cls._valid_ai_evidence(data, source_text):
      return None, "none"
    return data, provider

  @classmethod
  def _merge_ai_content(cls, base: dict[str, Any], ai_data: dict[str, Any], provider: str) -> dict[str, Any]:
    merged = dict(base)
    for field in ("overview", "detailed_explanation"):
      value = ai_data.get(field)
      if isinstance(value, str) and value.strip():
        merged[field] = value.strip()
    for field in (
      "learning_objectives",
      "key_concepts",
      "examples",
      "key_points",
      "common_mistakes",
      "exam_tips",
      "quick_revision",
      "related_topics",
    ):
      value = ai_data.get(field)
      if isinstance(value, list):
        merged[field] = [str(item).strip() for item in value if str(item).strip()][:30]
    grounding = dict(base.get("grounding") or {})
    grounding.update(
      {
        "ai_generated": True,
        "provider": provider,
        "verified_source_evidence": cls._ai_evidence_quotes(ai_data)[:20],
        "note": "AI explanation is grounded by verified quotes from the uploaded material; it is not personal medical advice.",
      }
    )
    merged["grounding"] = grounding
    return merged

  @staticmethod
  def _valid_ai_evidence(data: dict[str, Any], source_text: str) -> bool:
    evidence_map = data.get("evidence_map")
    if not isinstance(evidence_map, dict):
      return False
    normalized_source = re.sub(r"\s+", " ", source_text).casefold()
    content_fields = (
      "overview",
      "learning_objectives",
      "key_concepts",
      "detailed_explanation",
      "examples",
      "key_points",
      "common_mistakes",
      "exam_tips",
      "quick_revision",
      "related_topics",
    )
    supported_fields = 0
    for field in content_fields:
      value = data.get(field)
      if not value:
        continue
      quotes = evidence_map.get(field)
      if not isinstance(quotes, list) or not quotes:
        return False
      for quote in quotes[:10]:
        normalized_quote = re.sub(r"\s+", " ", str(quote)).strip().casefold()
        if len(normalized_quote) < 8 or normalized_quote not in normalized_source:
          return False
      supported_fields += 1
    return supported_fields > 0

  @staticmethod
  def _ai_evidence_quotes(data: dict[str, Any]) -> list[str]:
    values = []
    for quotes in (data.get("evidence_map") or {}).values():
      if isinstance(quotes, list):
        values.extend(str(quote) for quote in quotes if str(quote).strip())
    return LessonGenerationService._unique(values)

  @classmethod
  def _source_slice(
    cls,
    book: Book,
    topic: CourseTopic,
    all_topics: list[CourseTopic],
  ) -> tuple[str, list[int]]:
    start = int(topic.page_start or 1)
    end = int(topic.page_end or start)
    page_rows = []
    page_numbers = []
    for page in (book.structure_json or {}).get("pages") or []:
      if not isinstance(page, dict):
        continue
      number = int(page.get("page_number") or 0)
      if start <= number <= end:
        text = str(page.get("text") or "").strip()
        if text:
          page_rows.append(text)
          page_numbers.append(number)
    source = "\n\n".join(page_rows).strip()
    if not source:
      source = str((topic.source_json or {}).get("excerpt") or "").strip()
      page_numbers = list(range(start, end + 1))[:100]

    lower = source.casefold()
    current_position = lower.find(topic.title.casefold())
    if current_position >= 0:
      slice_start = current_position + len(topic.title)
      next_positions = []
      for other in all_topics:
        if other.id == topic.id:
          continue
        pos = lower.find(other.title.casefold(), slice_start)
        if pos > slice_start:
          next_positions.append(pos)
      slice_end = min(next_positions) if next_positions else len(source)
      candidate = source[slice_start:slice_end].strip(" \n:.-–")
      if len(candidate) >= 40:
        source = candidate

    max_chars = int(current_app.config.get("TEACHER_LESSON_MAX_SOURCE_CHARS", 12000))
    return source[:max_chars].strip(), page_numbers

  @staticmethod
  def _page_evidence(items: list[dict[str, Any]], topic: CourseTopic) -> list[dict[str, Any]]:
    start = int(topic.page_start or 1)
    end = int(topic.page_end or start)
    return [
      item
      for item in items
      if isinstance(item, dict)
      and start <= int((item.get("source") or {}).get("page_start") or -1) <= end
    ][:30]

  @staticmethod
  def _topic_values(items: list[dict[str, Any]] | None, field: str) -> list[str]:
    return [
      str(item.get(field)).strip()
      for item in items or []
      if isinstance(item, dict) and item.get(field)
    ][:30]

  @staticmethod
  def _overview(source_text: str, title: str) -> str:
    cleaned = re.sub(re.escape(title), " ", source_text, count=1, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", cleaned) if item.strip()]
    return " ".join(sentences[:2])[:800] if sentences else cleaned[:800]

  @staticmethod
  def _source_bullets(source_text: str) -> list[str]:
    values = []
    for raw in source_text.splitlines():
      stripped = raw.strip()
      if re.match(r"^[•\-*–]\s+\S", stripped):
        values.append(re.sub(r"^[•\-*–]\s+", "", stripped).strip())
    return values[:20]

  @staticmethod
  def _unique(values: list[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
      key = re.sub(r"\s+", " ", str(value)).strip().casefold()
      if not key or key in seen:
        continue
      seen.add(key)
      output.append(str(value).strip())
    return output

  @staticmethod
  def _difficulty(value: str) -> str:
    normalized = str(value or "intermediate").strip().lower()
    if normalized not in ("beginner", "intermediate", "advanced"):
      raise ValueError("Difficulty must be beginner, intermediate, or advanced.")
    return normalized

  @staticmethod
  def _to_markdown(title: str, content: dict[str, Any]) -> str:
    sections = [f"# {title}", "", "> Based on your uploaded course material. Educational use only."]
    scalar_sections = (("Overview", "overview"), ("Detailed explanation", "detailed_explanation"))
    for label, key in scalar_sections:
      value = content.get(key)
      if value:
        sections.extend(["", f"## {label}", "", str(value)])
    list_sections = (
      ("Learning objectives", "learning_objectives"),
      ("Key concepts", "key_concepts"),
      ("Examples", "examples"),
      ("Key points", "key_points"),
      ("Common mistakes", "common_mistakes"),
      ("Exam tips", "exam_tips"),
      ("Quick revision", "quick_revision"),
      ("Related topics", "related_topics"),
    )
    for label, key in list_sections:
      values = content.get(key) or []
      if values:
        sections.extend(["", f"## {label}", ""])
        sections.extend(f"- {value}" for value in values)
    definitions = content.get("important_definitions") or []
    if definitions:
      sections.extend(["", "## Important definitions", ""])
      sections.extend(
        f"- **{item.get('term')}**: {item.get('definition')}"
        for item in definitions
        if isinstance(item, dict) and item.get("term") and item.get("definition")
      )
    return "\n".join(sections).strip()

  @staticmethod
  def lesson_summary(lesson: Lesson) -> dict[str, Any]:
    payload = lesson.to_dict()
    payload.pop("content", None)
    payload.pop("content_json", None)
    return payload
