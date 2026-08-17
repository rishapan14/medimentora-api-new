"""Admin service for Body Systems Learning Hub (Phase 2 / Phase 14-ready)."""

from __future__ import annotations

from typing import Any

from app.extensions import db
from app.models.body_system_model import (
  BodySystem,
  BodySystemCourse,
  BodySystemQuiz,
  HubDisease,
  Organ,
)
from app.models.course_model import Course
from app.models.quiz_model import Quiz
from app.services.body_systems.hub_service import BodySystemHubService, slugify
from app.utils import utc_now
from app.validations.body_system_validation import (
  validate_body_system_payload,
  validate_disease_payload,
  validate_organ_payload,
)


class AdminBodySystemService:
  """Admin CRUD for hub catalog entities."""

  @classmethod
  def list_systems(cls, *, q: str | None = None, include_inactive: bool = True) -> dict[str, Any]:
    return BodySystemHubService.list_systems(
      q=q,
      include_inactive=include_inactive,
      page=1,
      per_page=100,
    )

  @classmethod
  def get_system(cls, slug_or_id: str) -> dict[str, Any] | None:
    """Admin detail — includes unpublished organs/diseases and all course/quiz links."""
    system = BodySystemHubService._resolve_system(slug_or_id, include_inactive=True)
    if not system:
      return None

    organs = (
      Organ.query.filter_by(body_system_id=system.id)
      .order_by(Organ.sort_order, Organ.name)
      .all()
    )
    diseases = (
      HubDisease.query.filter_by(body_system_id=system.id)
      .order_by(HubDisease.sort_order, HubDisease.name)
      .limit(100)
      .all()
    )
    course_links = (
      BodySystemCourse.query.filter_by(body_system_id=system.id)
      .order_by(BodySystemCourse.sort_order)
      .all()
    )
    quiz_links = (
      BodySystemQuiz.query.filter_by(body_system_id=system.id)
      .order_by(BodySystemQuiz.sort_order)
      .all()
    )

    courses = []
    for link in course_links:
      course = db.session.get(Course, link.course_id)
      if course:
        courses.append({**link.to_dict(), "course": course.to_dict()})

    quizzes = []
    for link in quiz_links:
      quiz = db.session.get(Quiz, link.quiz_id)
      if quiz:
        quizzes.append({**link.to_dict(), "quiz": quiz.to_dict()})

    data = system.to_dict()
    data["organs"] = [o.to_dict() for o in organs]
    data["diseases"] = [d.to_dict() for d in diseases]
    data["courses"] = courses
    data["quizzes"] = quizzes
    data["safety"] = {
      "educational_only": True,
      "not_a_diagnosis": True,
      "note": "Admin catalog management for educational Body Systems Hub content.",
    }
    return data

  @classmethod
  def create_system(cls, payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str | None]:
    errors = validate_body_system_payload(payload, partial=False)
    if errors:
      return None, "validation_error", errors[0]

    slug = slugify(payload.get("slug") or payload.get("name") or "")
    if BodySystem.query.filter_by(slug=slug).first():
      return None, "conflict", f"Body system slug '{slug}' already exists."

    row = BodySystem(
      slug=slug,
      name=(payload.get("name") or "").strip(),
      short_description=(payload.get("short_description") or "").strip() or None,
      long_description=(payload.get("long_description") or "").strip() or None,
      icon=(payload.get("icon") or "").strip() or None,
      emoji=(payload.get("emoji") or "").strip() or None,
      illustration_url=(payload.get("illustration_url") or "").strip() or None,
      difficulty=(payload.get("difficulty") or "intermediate").strip().lower(),
      estimated_minutes=int(payload.get("estimated_minutes") or 120),
      sort_order=int(payload.get("sort_order") or 0),
      is_active=bool(payload.get("is_active", True)),
      is_published=bool(payload.get("is_published", True)),
      category_id=payload.get("category_id"),
      default_course_id=payload.get("default_course_id"),
      meta_json=payload.get("meta_json") if isinstance(payload.get("meta_json"), dict) else {},
    )
    db.session.add(row)
    db.session.commit()
    return row.to_dict(), None, None

  @classmethod
  def update_system(
    cls, slug_or_id: str, payload: dict[str, Any]
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    row = BodySystemHubService._resolve_system(slug_or_id, include_inactive=True)
    if not row:
      return None, "not_found", "Body system not found."
    errors = validate_body_system_payload(payload, partial=True)
    if errors:
      return None, "validation_error", errors[0]

    for field in (
      "name",
      "short_description",
      "long_description",
      "icon",
      "emoji",
      "illustration_url",
      "difficulty",
    ):
      if field in payload and payload[field] is not None:
        setattr(row, field, str(payload[field]).strip() if isinstance(payload[field], str) else payload[field])

    if "slug" in payload and payload["slug"]:
      new_slug = slugify(str(payload["slug"]))
      clash = BodySystem.query.filter(BodySystem.slug == new_slug, BodySystem.id != row.id).first()
      if clash:
        return None, "conflict", f"Body system slug '{new_slug}' already exists."
      row.slug = new_slug

    for field in ("estimated_minutes", "sort_order", "category_id", "default_course_id"):
      if field in payload and payload[field] is not None:
        try:
          setattr(row, field, int(payload[field]))
        except (TypeError, ValueError):
          return None, "validation_error", f"{field} must be an integer."

    for field in ("is_active", "is_published"):
      if field in payload and payload[field] is not None:
        setattr(row, field, bool(payload[field]))

    if "meta_json" in payload and isinstance(payload["meta_json"], dict):
      row.meta_json = payload["meta_json"]

    row.updated_at = utc_now()
    db.session.commit()
    return row.to_dict(), None, None

  @classmethod
  def delete_system(cls, slug_or_id: str) -> tuple[bool, str | None, str | None]:
    row = BodySystemHubService._resolve_system(slug_or_id, include_inactive=True)
    if not row:
      return False, "not_found", "Body system not found."
    # Soft-delete preferred for educational catalogs
    row.is_active = False
    row.is_published = False
    row.updated_at = utc_now()
    db.session.commit()
    return True, None, None

  @classmethod
  def create_organ(
    cls, system_slug: str, payload: dict[str, Any]
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    system = BodySystemHubService._resolve_system(system_slug, include_inactive=True)
    if not system:
      return None, "not_found", "Body system not found."
    errors = validate_organ_payload(payload, partial=False)
    if errors:
      return None, "validation_error", errors[0]
    slug = slugify(payload.get("slug") or payload.get("name") or "")
    if Organ.query.filter_by(body_system_id=system.id, slug=slug).first():
      return None, "conflict", f"Organ slug '{slug}' already exists in this system."
    row = Organ(
      body_system_id=system.id,
      slug=slug,
      name=(payload.get("name") or "").strip(),
      short_description=(payload.get("short_description") or "").strip() or None,
      overview=(payload.get("overview") or "").strip() or None,
      location=(payload.get("location") or "").strip() or None,
      region_key=(payload.get("region_key") or slug).strip(),
      illustration_url=(payload.get("illustration_url") or "").strip() or None,
      animation_key=(payload.get("animation_key") or "").strip() or None,
      content_json=payload.get("content_json") if isinstance(payload.get("content_json"), dict) else {},
      learning_objectives=payload.get("learning_objectives")
      if isinstance(payload.get("learning_objectives"), list)
      else [],
      sort_order=int(payload.get("sort_order") or 0),
      is_active=bool(payload.get("is_active", True)),
      is_published=bool(payload.get("is_published", True)),
    )
    db.session.add(row)
    db.session.commit()
    return row.to_dict(), None, None

  @classmethod
  def update_organ(
    cls, organ_slug_or_id: str, payload: dict[str, Any], *, system_slug: str | None = None
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    row = BodySystemHubService._resolve_organ(organ_slug_or_id, system_slug=system_slug)
    if not row:
      # allow inactive lookup for admin
      raw = (organ_slug_or_id or "").strip()
      if raw.isdigit():
        row = Organ.query.filter_by(id=int(raw)).first()
      else:
        q = Organ.query.filter_by(slug=raw)
        if system_slug:
          system = BodySystemHubService._resolve_system(system_slug, include_inactive=True)
          if system:
            q = q.filter_by(body_system_id=system.id)
        row = q.first()
    if not row:
      return None, "not_found", "Organ not found."
    errors = validate_organ_payload(payload, partial=True)
    if errors:
      return None, "validation_error", errors[0]

    for field in (
      "name",
      "short_description",
      "overview",
      "location",
      "region_key",
      "illustration_url",
      "animation_key",
    ):
      if field in payload and payload[field] is not None:
        setattr(row, field, str(payload[field]).strip() if isinstance(payload[field], str) else payload[field])
    if "slug" in payload and payload["slug"]:
      new_slug = slugify(str(payload["slug"]))
      clash = Organ.query.filter(
        Organ.body_system_id == row.body_system_id,
        Organ.slug == new_slug,
        Organ.id != row.id,
      ).first()
      if clash:
        return None, "conflict", f"Organ slug '{new_slug}' already exists in this system."
      row.slug = new_slug
    if "sort_order" in payload and payload["sort_order"] is not None:
      row.sort_order = int(payload["sort_order"])
    for field in ("is_active", "is_published"):
      if field in payload and payload[field] is not None:
        setattr(row, field, bool(payload[field]))
    if "content_json" in payload and isinstance(payload["content_json"], dict):
      row.content_json = payload["content_json"]
    if "learning_objectives" in payload and isinstance(payload["learning_objectives"], list):
      row.learning_objectives = payload["learning_objectives"]
    row.updated_at = utc_now()
    db.session.commit()
    return row.to_dict(), None, None

  @classmethod
  def create_disease(
    cls, system_slug: str, payload: dict[str, Any]
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    system = BodySystemHubService._resolve_system(system_slug, include_inactive=True)
    if not system:
      return None, "not_found", "Body system not found."
    errors = validate_disease_payload(payload, partial=False)
    if errors:
      return None, "validation_error", errors[0]
    slug = slugify(payload.get("slug") or payload.get("name") or "")
    if HubDisease.query.filter_by(body_system_id=system.id, slug=slug).first():
      return None, "conflict", f"Disease slug '{slug}' already exists in this system."
    organ_id = payload.get("organ_id")
    if payload.get("organ_slug"):
      organ = Organ.query.filter_by(
        body_system_id=system.id, slug=str(payload["organ_slug"]).strip()
      ).first()
      organ_id = organ.id if organ else organ_id
    row = HubDisease(
      body_system_id=system.id,
      organ_id=int(organ_id) if organ_id not in (None, "") else None,
      slug=slug,
      name=(payload.get("name") or "").strip(),
      short_description=(payload.get("short_description") or "").strip() or None,
      content_json=payload.get("content_json") if isinstance(payload.get("content_json"), dict) else {},
      difficulty=(payload.get("difficulty") or "intermediate").strip().lower(),
      topic_tags=payload.get("topic_tags") if isinstance(payload.get("topic_tags"), list) else [],
      sort_order=int(payload.get("sort_order") or 0),
      is_active=bool(payload.get("is_active", True)),
      is_published=bool(payload.get("is_published", True)),
    )
    db.session.add(row)
    db.session.commit()
    return row.to_dict(), None, None

  @classmethod
  def link_course(
    cls, system_slug: str, course_id: int, *, role: str = "related", sort_order: int = 0
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    system = BodySystemHubService._resolve_system(system_slug, include_inactive=True)
    if not system:
      return None, "not_found", "Body system not found."
    course = db.session.get(Course, int(course_id))
    if not course:
      return None, "not_found", "Course not found."
    existing = BodySystemCourse.query.filter_by(
      body_system_id=system.id, course_id=course.id
    ).first()
    if existing:
      existing.role = role or existing.role
      existing.sort_order = sort_order
      db.session.commit()
      return existing.to_dict(), None, None
    link = BodySystemCourse(
      body_system_id=system.id,
      course_id=course.id,
      role=role or "related",
      sort_order=int(sort_order or 0),
    )
    db.session.add(link)
    if role == "primary":
      system.default_course_id = course.id
    db.session.commit()
    return link.to_dict(), None, None

  @classmethod
  def link_quiz(
    cls, system_slug: str, quiz_id: int, *, is_required: bool = False, sort_order: int = 0
  ) -> tuple[dict[str, Any] | None, str | None, str | None]:
    system = BodySystemHubService._resolve_system(system_slug, include_inactive=True)
    if not system:
      return None, "not_found", "Body system not found."
    quiz = db.session.get(Quiz, int(quiz_id))
    if not quiz:
      return None, "not_found", "Quiz not found."
    existing = BodySystemQuiz.query.filter_by(body_system_id=system.id, quiz_id=quiz.id).first()
    if existing:
      existing.is_required = bool(is_required)
      existing.sort_order = int(sort_order or 0)
      db.session.commit()
      return existing.to_dict(), None, None
    link = BodySystemQuiz(
      body_system_id=system.id,
      quiz_id=quiz.id,
      is_required=bool(is_required),
      sort_order=int(sort_order or 0),
    )
    db.session.add(link)
    db.session.commit()
    return link.to_dict(), None, None
