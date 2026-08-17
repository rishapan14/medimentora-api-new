"""Phase 4: persist a detected document hierarchy as a personal LMS course."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.book_model import Book
from app.models.course_model import Course, CourseCategory, CourseModule, CourseTopic
from app.services.medical_teacher.document_structure_service import DocumentStructureService
from app.utils import utc_now


@dataclass
class CourseGenerationResult:
  course: Course
  reused: bool
  counts: dict[str, int]

  def to_dict(self) -> dict[str, Any]:
    return {
      "reused": self.reused,
      "counts": self.counts,
      "course": CourseGenerationService.serialize_course(self.course),
    }


class CourseGenerationService:
  """Create one private, source-grounded course for an owned Book."""

  @classmethod
  def generate_from_book(cls, book_id: int, user_id: int) -> CourseGenerationResult:
    book = Book.query.filter_by(id=book_id, user_id=user_id).first()
    if not book:
      raise LookupError("Book not found.")
    structure = DocumentStructureService.get_for_book(book)
    if not structure:
      raise ValueError("Document structure must be detected before course generation.")

    existing = Course.query.filter_by(source_book_id=book.id).first()
    if existing:
      if existing.owner_user_id != user_id:
        raise LookupError("Course not found.")
      return CourseGenerationResult(
        course=existing,
        reused=True,
        counts=cls._course_counts(existing),
      )

    course = Course(
      title=str((structure.get("course") or {}).get("title") or book.title)[:200],
      description=book.description or f"Personal course generated from {book.original_filename}.",
      speciality=book.medical_subject,
      category_id=cls._matching_category_id(book.medical_subject),
      difficulty="medium",
      duration_hours=0,
      instructor_id=user_id,
      owner_user_id=user_id,
      source_book_id=book.id,
      origin="uploaded_document",
      generation_status="generating",
      source_structure_version=str(structure.get("schema_version") or "1.0")[:20],
      source_json={
        "document_id": book.id,
        "course_source": (structure.get("course") or {}).get("source"),
        "grounding": structure.get("grounding"),
      },
      learning_objectives=[
        item.get("text")
        for item in structure.get("learning_objectives") or []
        if isinstance(item, dict) and item.get("text")
      ][:100],
      prerequisites=[],
      certificate_eligible=False,
      is_published=False,
      created_at=utc_now(),
      updated_at=utc_now(),
    )
    db.session.add(course)

    try:
      db.session.flush()
      cls._persist_nodes(
        course,
        structure.get("hierarchy") or [],
        structure,
      )
      course.generation_status = "ready"
      course.updated_at = utc_now()
      db.session.commit()
    except IntegrityError:
      db.session.rollback()
      existing = Course.query.filter_by(source_book_id=book.id, owner_user_id=user_id).first()
      if existing:
        return CourseGenerationResult(
          course=existing,
          reused=True,
          counts=cls._course_counts(existing),
        )
      raise
    except Exception:
      db.session.rollback()
      raise

    return CourseGenerationResult(
      course=course,
      reused=False,
      counts=cls._course_counts(course),
    )

  @classmethod
  def get_owned_for_book(cls, book_id: int, user_id: int) -> Course | None:
    return (
      Course.query.join(Book, Course.source_book_id == Book.id)
      .filter(Course.source_book_id == book_id, Course.owner_user_id == user_id, Book.user_id == user_id)
      .first()
    )

  @classmethod
  def serialize_course(cls, course: Course) -> dict[str, Any]:
    payload = course.to_dict()
    root_modules = (
      CourseModule.query.filter_by(course_id=course.id, parent_module_id=None)
      .order_by(CourseModule.order_index, CourseModule.id)
      .all()
    )
    direct_topics = (
      CourseTopic.query.filter_by(course_id=course.id, module_id=None, parent_topic_id=None)
      .order_by(CourseTopic.order_index, CourseTopic.id)
      .all()
    )
    payload["modules"] = [cls._serialize_module(item) for item in root_modules]
    payload["topics"] = [item.to_dict(include_children=True) for item in direct_topics]
    payload["generation_counts"] = cls._course_counts(course)
    payload["source"] = course.source_json
    return payload

  @classmethod
  def _serialize_module(cls, module: CourseModule) -> dict[str, Any]:
    payload = module.to_dict()
    topics = (
      CourseTopic.query.filter_by(module_id=module.id, parent_topic_id=None)
      .order_by(CourseTopic.order_index, CourseTopic.id)
      .all()
    )
    children = (
      CourseModule.query.filter_by(parent_module_id=module.id)
      .order_by(CourseModule.order_index, CourseModule.id)
      .all()
    )
    payload["topics"] = [item.to_dict(include_children=True) for item in topics]
    payload["children"] = [cls._serialize_module(item) for item in children]
    return payload

  @classmethod
  def _persist_nodes(
    cls,
    course: Course,
    nodes: list[dict[str, Any]],
    structure: dict[str, Any],
    *,
    parent_module: CourseModule | None = None,
    current_module: CourseModule | None = None,
    parent_topic: CourseTopic | None = None,
  ) -> None:
    for sibling_order, node in enumerate(nodes, start=1):
      if not isinstance(node, dict):
        continue
      node_type = str(node.get("type") or "").lower()
      if node_type in ("module", "chapter"):
        module = CourseModule(
          course_id=course.id,
          parent_module_id=parent_module.id if parent_module else None,
          title=str(node.get("title") or "Untitled section")[:200],
          description=cls._page_description(node),
          order_index=sibling_order,
          structure_type=node_type,
          source_node_id=str(node.get("id") or "")[:80] or None,
          page_start=cls._int_or_none(node.get("page_start")),
          page_end=cls._int_or_none(node.get("page_end")),
          source_json=node.get("source"),
        )
        db.session.add(module)
        db.session.flush()
        cls._persist_nodes(
          course,
          node.get("children") or [],
          structure,
          parent_module=module,
          current_module=module,
          parent_topic=None,
        )
        continue

      if node_type not in ("topic", "subtopic"):
        continue
      topic = CourseTopic(
        course_id=course.id,
        module_id=current_module.id if current_module else None,
        parent_topic_id=parent_topic.id if parent_topic else None,
        title=str(node.get("title") or "Untitled topic")[:200],
        description=cls._page_description(node),
        order_index=sibling_order,
        structure_type=node_type,
        source_node_id=str(node.get("id") or "")[:80] or None,
        page_start=cls._int_or_none(node.get("page_start")),
        page_end=cls._int_or_none(node.get("page_end")),
        source_json=node.get("source"),
        learning_objectives=cls._evidence_for_node(
          structure.get("learning_objectives") or [],
          node,
          "text",
        ),
        important_concepts=cls._evidence_for_node(
          structure.get("important_concepts") or [],
          node,
          "title",
        ),
      )
      db.session.add(topic)
      db.session.flush()
      cls._persist_nodes(
        course,
        node.get("children") or [],
        structure,
        parent_module=parent_module,
        current_module=current_module,
        parent_topic=topic,
      )

  @staticmethod
  def _evidence_for_node(items: list[dict[str, Any]], node: dict[str, Any], field: str) -> list[dict[str, Any]]:
    start = CourseGenerationService._int_or_none(node.get("page_start"))
    end = CourseGenerationService._int_or_none(node.get("page_end"))
    if start is None:
      return []
    end = end if end is not None else start
    matched = []
    for item in items:
      if not isinstance(item, dict):
        continue
      source = item.get("source") or {}
      page = CourseGenerationService._int_or_none(source.get("page_start"))
      if page is None or not (start <= page <= end) or not item.get(field):
        continue
      matched.append({field: item[field], "source": source})
    return matched[:50]

  @staticmethod
  def _course_counts(course: Course) -> dict[str, int]:
    modules = CourseModule.query.filter_by(course_id=course.id).all()
    topics = CourseTopic.query.filter_by(course_id=course.id).all()
    return {
      "modules": sum(1 for item in modules if (item.structure_type or "module") == "module"),
      "chapters": sum(1 for item in modules if item.structure_type == "chapter"),
      "topics": sum(1 for item in topics if (item.structure_type or "topic") == "topic"),
      "subtopics": sum(1 for item in topics if item.structure_type == "subtopic"),
    }

  @staticmethod
  def _matching_category_id(subject: str | None) -> int | None:
    if not subject:
      return None
    category = CourseCategory.query.filter(CourseCategory.name.ilike(subject.strip())).first()
    return category.id if category else None

  @staticmethod
  def _page_description(node: dict[str, Any]) -> str | None:
    start = CourseGenerationService._int_or_none(node.get("page_start"))
    end = CourseGenerationService._int_or_none(node.get("page_end"))
    if start is None:
      return None
    return f"Based on uploaded material, page {start}." if start == end else f"Based on uploaded material, pages {start}–{end}."

  @staticmethod
  def _int_or_none(value) -> int | None:
    try:
      return int(value) if value is not None else None
    except (TypeError, ValueError):
      return None
