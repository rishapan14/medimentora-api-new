"""Phase 2 — Body Systems Learning Hub service layer.

Educational APIs only — not diagnostic. Reuses LMS Course / Lesson / Quiz links.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import or_

from app.extensions import db
from app.models.body_system_model import (
  BodySystem,
  BodySystemCourse,
  BodySystemProgress,
  BodySystemQuiz,
  HubDisease,
  HubFlashcard,
  HubRecommendation,
  Organ,
)
from app.models.course_model import Course, Lesson
from app.models.quiz_model import Quiz
from app.utils import utc_now

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
  text = (value or "").strip().lower()
  text = _SLUG_RE.sub("-", text).strip("-")
  return text[:80] or "item"


class BodySystemHubService:
  """Student-facing hub queries."""

  @classmethod
  def list_systems(
    cls,
    *,
    user_id: int | None = None,
    q: str | None = None,
    difficulty: str | None = None,
    page: int = 1,
    per_page: int = 20,
    include_inactive: bool = False,
  ) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 20)))

    query = BodySystem.query
    if not include_inactive:
      query = query.filter(
        BodySystem.is_active.is_(True),
        or_(BodySystem.is_published.is_(True), BodySystem.is_published.is_(None)),
      )
    if difficulty:
      query = query.filter(BodySystem.difficulty == difficulty.strip().lower())
    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        or_(
          BodySystem.name.ilike(like),
          BodySystem.short_description.ilike(like),
          BodySystem.slug.ilike(like),
        )
      )

    total = query.count()
    rows = (
      query.order_by(BodySystem.sort_order, BodySystem.name)
      .offset((page - 1) * per_page)
      .limit(per_page)
      .all()
    )

    progress_map: dict[int, BodySystemProgress] = {}
    if user_id and rows:
      ids = [r.id for r in rows]
      for prog in BodySystemProgress.query.filter(
        BodySystemProgress.user_id == user_id,
        BodySystemProgress.body_system_id.in_(ids),
      ).all():
        progress_map[prog.body_system_id] = prog

    items = []
    for row in rows:
      item = row.to_dict()
      prog = progress_map.get(row.id)
      item["progress"] = prog.to_dict() if prog else cls._empty_progress(row.id)
      item["can_continue"] = bool(prog and prog.status in ("in_progress", "completed") and prog.progress_percent > 0)
      items.append(item)

    return {
      "items": items,
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def get_system(
    cls,
    slug_or_id: str,
    *,
    user_id: int | None = None,
    include_inactive: bool = False,
  ) -> dict[str, Any] | None:
    system = cls._resolve_system(slug_or_id, include_inactive=include_inactive)
    if not system:
      return None

    organs = (
      Organ.query.filter_by(body_system_id=system.id, is_active=True)
      .filter(or_(Organ.is_published.is_(True), Organ.is_published.is_(None)))
      .order_by(Organ.sort_order, Organ.name)
      .all()
    )
    diseases = (
      HubDisease.query.filter_by(body_system_id=system.id, is_active=True)
      .filter(or_(HubDisease.is_published.is_(True), HubDisease.is_published.is_(None)))
      .order_by(HubDisease.sort_order, HubDisease.name)
      .limit(50)
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
      if not course:
        continue
      if course.is_published is False:
        continue
      courses.append({**link.to_dict(), "course": course.to_dict()})

    quizzes = []
    for link in quiz_links:
      quiz = db.session.get(Quiz, link.quiz_id)
      if not quiz or quiz.is_published is False:
        continue
      quizzes.append({**link.to_dict(), "quiz": quiz.to_dict()})

    progress = None
    if user_id:
      progress = BodySystemProgress.query.filter_by(
        user_id=user_id, body_system_id=system.id
      ).first()

    data = system.to_dict()
    data["organs"] = [o.to_dict() for o in organs]
    data["diseases"] = [d.to_dict() for d in diseases]
    data["courses"] = courses
    data["quizzes"] = quizzes
    data["progress"] = progress.to_dict() if progress else cls._empty_progress(system.id)
    data["can_continue"] = bool(
      progress and progress.status in ("in_progress", "completed") and progress.progress_percent > 0
    )
    data["safety"] = {"educational_only": True, "not_a_diagnosis": True}
    return data

  @classmethod
  def list_organs(
    cls,
    system_slug: str,
    *,
    q: str | None = None,
    page: int = 1,
    per_page: int = 50,
  ) -> dict[str, Any] | None:
    system = cls._resolve_system(system_slug)
    if not system:
      return None
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 50)))
    query = Organ.query.filter_by(body_system_id=system.id, is_active=True).filter(
      or_(Organ.is_published.is_(True), Organ.is_published.is_(None))
    )
    if q:
      like = f"%{q.strip()}%"
      query = query.filter(or_(Organ.name.ilike(like), Organ.slug.ilike(like), Organ.short_description.ilike(like)))
    total = query.count()
    rows = query.order_by(Organ.sort_order, Organ.name).offset((page - 1) * per_page).limit(per_page).all()
    return {
      "body_system": system.to_dict(include_counts=False),
      "items": [r.to_dict() for r in rows],
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def get_organ(
    cls,
    slug_or_id: str,
    *,
    system_slug: str | None = None,
    user_id: int | None = None,
  ) -> dict[str, Any] | None:
    organ = cls._resolve_organ(slug_or_id, system_slug=system_slug)
    if not organ:
      return None
    system = organ.body_system
    diseases = (
      HubDisease.query.filter_by(organ_id=organ.id, is_active=True)
      .filter(or_(HubDisease.is_published.is_(True), HubDisease.is_published.is_(None)))
      .order_by(HubDisease.sort_order, HubDisease.name)
      .all()
    )
    data = organ.to_dict()
    data["body_system"] = system.to_dict(include_counts=False) if system else None
    data["diseases"] = [d.to_dict() for d in diseases]
    # Phase 4 — normalized section map for organ page UI (derived from content_json)
    cj = data.get("content_json") if isinstance(data.get("content_json"), dict) else {}
    data["sections"] = {
      "overview": cj.get("overview") or data.get("overview"),
      "location": cj.get("location_detail") or data.get("location"),
      "functions": cj.get("functions") or [],
      "parts": cj.get("parts") or [],
      "blood_supply": cj.get("blood_supply"),
      "nerves": cj.get("nerves"),
      "physiology": cj.get("physiology"),
      "anatomy": cj.get("anatomy"),
      "clinical_importance": cj.get("clinical_importance"),
      "normal_anatomy": cj.get("normal_anatomy"),
      "common_diseases": cj.get("common_diseases") or [],
      "signs": cj.get("signs") or [],
      "symptoms": cj.get("symptoms") or [],
      "investigations": cj.get("investigations") or [],
      "treatment_overview": cj.get("treatment_overview"),
      "nursing_care": cj.get("nursing_care") or [],
      "complications": cj.get("complications") or [],
      "patient_education": cj.get("patient_education") or [],
      "prevention": cj.get("prevention") or [],
      "clinical_pearls": cj.get("clinical_pearls") or [],
      "images": cj.get("images") or [],
      "illustrations": cj.get("illustrations") or [],
      "animation_notes": cj.get("animation_notes"),
    }
    data["safety"] = {
      "educational_only": True,
      "not_a_diagnosis": True,
      "note": "Organ pages are for educational purposes only and must not be used as a diagnosis.",
    }
    # Phase 12 — soft progress bump when a learner opens an organ page
    if user_id and system:
      progress = cls.touch_progress_for_organ(user_id, organ)
      data["progress"] = progress
    return data

  @classmethod
  def touch_progress_for_organ(cls, user_id: int, organ: Organ) -> dict[str, Any]:
    """Ensure progress row, set last_organ_id, bump % when visiting a new organ."""
    system_id = organ.body_system_id
    prog = BodySystemProgress.query.filter_by(user_id=user_id, body_system_id=system_id).first()
    if not prog:
      prog = BodySystemProgress(
        user_id=user_id,
        body_system_id=system_id,
        status="in_progress",
        progress_percent=0,
        started_at=utc_now(),
      )
      db.session.add(prog)

    if prog.status == "not_started":
      prog.status = "in_progress"
      prog.started_at = prog.started_at or utc_now()

    # Only bump when switching to a different organ (avoid refresh inflation)
    if prog.last_organ_id != organ.id:
      bump = 4.0
      prog.progress_percent = min(100.0, float(prog.progress_percent or 0) + bump)
      prog.study_minutes = int(prog.study_minutes or 0) + 1
      prog.last_organ_id = organ.id
      if prog.progress_percent >= 100:
        prog.status = "completed"
        prog.completed_at = utc_now()
    prog.updated_at = utc_now()
    db.session.commit()

    if prog.status == "completed" or float(prog.progress_percent or 0) >= 100:
      try:
        from app.services.body_systems.hub_certificate_service import HubCertificateService

        HubCertificateService.maybe_issue_for_progress(prog)
      except Exception:
        pass

    return prog.to_dict()

  @classmethod
  def get_progress_summary(cls, user_id: int) -> dict[str, Any]:
    """Phase 12 — hub-wide progress dashboard payload."""
    systems = (
      BodySystem.query.filter_by(is_active=True)
      .filter(or_(BodySystem.is_published.is_(True), BodySystem.is_published.is_(None)))
      .order_by(BodySystem.sort_order, BodySystem.name)
      .all()
    )
    progress_rows = {
      p.body_system_id: p
      for p in BodySystemProgress.query.filter_by(user_id=user_id).all()
    }

    items: list[dict[str, Any]] = []
    not_started = in_progress = completed = 0
    total_minutes = 0
    percent_sum = 0.0

    for system in systems:
      prog = progress_rows.get(system.id)
      progress = prog.to_dict() if prog else cls._empty_progress(system.id)
      status = progress.get("status") or "not_started"
      pct = float(progress.get("progress_percent") or 0)
      if status == "completed" or pct >= 100:
        completed += 1
      elif status == "in_progress" or pct > 0:
        in_progress += 1
      else:
        not_started += 1
      total_minutes += int(progress.get("study_minutes") or 0)
      percent_sum += pct

      last_organ = None
      if prog and prog.last_organ_id:
        organ = Organ.query.filter_by(id=prog.last_organ_id).first()
        if organ:
          last_organ = {
            "id": organ.id,
            "slug": organ.slug,
            "name": organ.name,
            "href": f"/learning/body-systems/{system.slug}/organs/{organ.slug}",
          }

      items.append(
        {
          **system.to_dict(include_counts=False),
          "progress": progress,
          "can_continue": status in ("in_progress", "completed") or pct > 0,
          "href": f"/learning/body-systems/{system.slug}",
          "last_organ": last_organ,
        }
      )

    total = len(systems) or 1
    overall = round(percent_sum / total, 1)

    recently = sorted(
      [i for i in items if i["progress"].get("updated_at")],
      key=lambda i: i["progress"].get("updated_at") or "",
      reverse=True,
    )[:6]

    return {
      "summary": {
        "total_systems": len(systems),
        "not_started": not_started,
        "in_progress": in_progress,
        "completed": completed,
        "overall_percent": overall,
        "total_study_minutes": total_minutes,
      },
      "systems": items,
      "recently_studied": recently,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Progress tracking reflects educational study activity only.",
      },
    }

  @classmethod
  def list_diseases(
    cls,
    system_slug: str,
    *,
    q: str | None = None,
    organ_slug: str | None = None,
    page: int = 1,
    per_page: int = 50,
  ) -> dict[str, Any] | None:
    system = cls._resolve_system(system_slug)
    if not system:
      return None
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 50)))
    query = HubDisease.query.filter_by(body_system_id=system.id, is_active=True).filter(
      or_(HubDisease.is_published.is_(True), HubDisease.is_published.is_(None))
    )
    if organ_slug:
      organ = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug.strip()).first()
      if organ:
        query = query.filter(HubDisease.organ_id == organ.id)
    if q:
      like = f"%{q.strip()}%"
      query = query.filter(
        or_(HubDisease.name.ilike(like), HubDisease.slug.ilike(like), HubDisease.short_description.ilike(like))
      )
    total = query.count()
    rows = (
      query.order_by(HubDisease.sort_order, HubDisease.name)
      .offset((page - 1) * per_page)
      .limit(per_page)
      .all()
    )
    return {
      "body_system": system.to_dict(include_counts=False),
      "items": [r.to_dict() for r in rows],
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def get_disease(cls, slug_or_id: str, *, system_slug: str | None = None) -> dict[str, Any] | None:
    disease = cls._resolve_disease(slug_or_id, system_slug=system_slug)
    if not disease:
      return None
    data = disease.to_dict()
    data["body_system"] = disease.body_system.to_dict(include_counts=False) if disease.body_system else None
    data["organ"] = disease.organ.to_dict() if disease.organ else None
    from app.services.body_systems.hub_case_service import HubCaseService

    data["clinical_cases"] = HubCaseService.ensure_disease_cases_on_get(disease)
    cj = data.get("content_json") if isinstance(data.get("content_json"), dict) else {}
    data["explorer"] = {
      "overview": cj.get("overview") or data.get("short_description"),
      "signs": cj.get("signs") or [],
      "symptoms": cj.get("symptoms") or [],
      "investigations": cj.get("investigations") or [],
      "treatment_overview": cj.get("treatment_overview"),
      "nursing_care": cj.get("nursing_care") or [],
    }
    data["safety"] = disease.to_dict()["safety"]
    return data

  @classmethod
  def search(cls, q: str, *, limit: int = 20) -> dict[str, Any]:
    term = (q or "").strip()
    if len(term) < 2:
      return {
        "query": term,
        "systems": [],
        "organs": [],
        "diseases": [],
        "courses": [],
        "total": 0,
        "safety": {"educational_only": True, "not_a_diagnosis": True},
      }
    like = f"%{term}%"
    limit = min(50, max(1, int(limit or 20)))

    systems = (
      BodySystem.query.filter(
        BodySystem.is_active.is_(True),
        or_(BodySystem.is_published.is_(True), BodySystem.is_published.is_(None)),
        or_(BodySystem.name.ilike(like), BodySystem.short_description.ilike(like)),
      )
      .order_by(BodySystem.sort_order)
      .limit(limit)
      .all()
    )
    organs = (
      Organ.query.filter(
        Organ.is_active.is_(True),
        or_(Organ.is_published.is_(True), Organ.is_published.is_(None)),
        or_(Organ.name.ilike(like), Organ.short_description.ilike(like)),
      )
      .order_by(Organ.sort_order)
      .limit(limit)
      .all()
    )
    diseases = (
      HubDisease.query.filter(
        HubDisease.is_active.is_(True),
        or_(HubDisease.is_published.is_(True), HubDisease.is_published.is_(None)),
        or_(HubDisease.name.ilike(like), HubDisease.short_description.ilike(like)),
      )
      .order_by(HubDisease.sort_order)
      .limit(limit)
      .all()
    )
    courses = (
      Course.query.filter(
        or_(Course.is_published.is_(True), Course.is_published.is_(None)),
        or_(Course.title.ilike(like), Course.description.ilike(like)),
      )
      .order_by(Course.title)
      .limit(limit)
      .all()
    )

    return {
      "query": term,
      "systems": [s.to_dict(include_counts=False) for s in systems],
      "organs": [o.to_dict() for o in organs],
      "diseases": [d.to_dict() for d in diseases],
      "courses": [c.to_dict() for c in courses],
      "total": len(systems) + len(organs) + len(diseases) + len(courses),
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def get_or_start_progress(cls, user_id: int, system_slug: str) -> dict[str, Any] | None:
    system = cls._resolve_system(system_slug)
    if not system:
      return None
    prog = BodySystemProgress.query.filter_by(user_id=user_id, body_system_id=system.id).first()
    if not prog:
      prog = BodySystemProgress(
        user_id=user_id,
        body_system_id=system.id,
        status="in_progress",
        progress_percent=0,
        started_at=utc_now(),
        last_course_id=system.default_course_id,
      )
      db.session.add(prog)
      db.session.commit()
    elif prog.status == "not_started":
      prog.status = "in_progress"
      prog.started_at = prog.started_at or utc_now()
      prog.updated_at = utc_now()
      db.session.commit()
    return {
      "body_system": system.to_dict(include_counts=False),
      "progress": prog.to_dict(),
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def update_progress(
    cls,
    user_id: int,
    system_slug: str,
    payload: dict[str, Any],
  ) -> tuple[dict[str, Any] | None, str | None]:
    system = cls._resolve_system(system_slug)
    if not system:
      return None, "not_found"
    prog = BodySystemProgress.query.filter_by(user_id=user_id, body_system_id=system.id).first()
    if not prog:
      prog = BodySystemProgress(user_id=user_id, body_system_id=system.id, started_at=utc_now())
      db.session.add(prog)

    status = (payload.get("status") or prog.status or "in_progress").strip().lower()
    if status not in ("not_started", "in_progress", "completed"):
      return None, "validation_error"

    if "progress_percent" in payload and payload["progress_percent"] is not None:
      try:
        pct = float(payload["progress_percent"])
      except (TypeError, ValueError):
        return None, "validation_error"
      prog.progress_percent = max(0.0, min(100.0, pct))

    if "study_minutes" in payload and payload["study_minutes"] is not None:
      try:
        prog.study_minutes = max(0, int(payload["study_minutes"]))
      except (TypeError, ValueError):
        return None, "validation_error"

    for field, attr in (
      ("last_course_id", "last_course_id"),
      ("last_lesson_id", "last_lesson_id"),
      ("last_organ_id", "last_organ_id"),
      ("lessons_completed", "lessons_completed"),
      ("lessons_total", "lessons_total"),
    ):
      if field in payload and payload[field] is not None:
        try:
          setattr(prog, attr, int(payload[field]))
        except (TypeError, ValueError):
          return None, "validation_error"

    prog.status = status
    if status == "in_progress" and not prog.started_at:
      prog.started_at = utc_now()
    if status == "completed":
      prog.progress_percent = max(float(prog.progress_percent or 0), 100.0)
      prog.completed_at = utc_now()
    prog.updated_at = utc_now()
    db.session.commit()

    if prog.status == "completed" or float(prog.progress_percent or 0) >= 100:
      try:
        from app.services.body_systems.hub_certificate_service import HubCertificateService

        HubCertificateService.maybe_issue_for_progress(prog)
      except Exception:
        pass

    return {
      "body_system": system.to_dict(include_counts=False),
      "progress": prog.to_dict(),
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }, None

  @classmethod
  def list_recommendations(
    cls,
    user_id: int,
    *,
    limit: int = 20,
    source_type: str | None = None,
    source_id: int | None = None,
  ) -> dict[str, Any]:
    limit = min(50, max(1, int(limit or 20)))
    query = HubRecommendation.query.filter_by(user_id=user_id)
    if source_type:
      query = query.filter_by(source_type=str(source_type).strip().lower())
    if source_id is not None:
      query = query.filter_by(source_id=int(source_id))
    rows = (
      query.order_by(HubRecommendation.priority.desc(), HubRecommendation.created_at.desc())
      .limit(limit)
      .all()
    )
    return {
      "items": [r.to_dict() for r in rows],
      "total": len(rows),
      "source_type": source_type,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def list_flashcards(
    cls,
    *,
    system_slug: str | None = None,
    organ_slug: str | None = None,
    card_level: str | None = None,
    page: int = 1,
    per_page: int = 30,
  ) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 30)))
    query = HubFlashcard.query.filter(
      or_(HubFlashcard.is_published.is_(True), HubFlashcard.is_published.is_(None))
    )
    if system_slug:
      system = cls._resolve_system(system_slug)
      if not system:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "has_more": False}
      query = query.filter(HubFlashcard.body_system_id == system.id)
    if organ_slug:
      organ = Organ.query.filter_by(slug=organ_slug.strip()).first()
      if organ:
        query = query.filter(HubFlashcard.organ_id == organ.id)
    if card_level:
      query = query.filter(HubFlashcard.card_level == card_level.strip().lower())
    total = query.count()
    rows = query.order_by(HubFlashcard.id.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return {
      "items": [r.to_dict() for r in rows],
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def get_explorer_catalog(cls) -> dict[str, Any]:
    """Phase 5 — interactive body explorer catalog (2D SVG now; 3D-ready)."""
    systems = {
      s.id: s
      for s in BodySystem.query.filter_by(is_active=True)
      .filter(or_(BodySystem.is_published.is_(True), BodySystem.is_published.is_(None)))
      .all()
    }
    organs = (
      Organ.query.filter_by(is_active=True)
      .filter(or_(Organ.is_published.is_(True), Organ.is_published.is_(None)))
      .order_by(Organ.sort_order, Organ.name)
      .all()
    )
    items: list[dict[str, Any]] = []
    for organ in organs:
      system = systems.get(organ.body_system_id)
      if not system:
        continue
      layer = "organ"
      if organ.slug in ("bones",):
        layer = "skeletal"
      elif organ.slug in ("muscles",):
        layer = "muscular"
      items.append(
        {
          "id": organ.id,
          "slug": organ.slug,
          "name": organ.name,
          "short_description": organ.short_description,
          "region_key": organ.region_key or organ.slug,
          "location": organ.location,
          "animation_key": organ.animation_key,
          "layer": layer,
          "href": f"/learning/body-systems/{system.slug}/organs/{organ.slug}",
          "body_system": {
            "id": system.id,
            "slug": system.slug,
            "name": system.name,
            "emoji": system.emoji,
          },
        }
      )
    return {
      "renderer": "svg-2d",
      "supported_renderers": ["svg-2d", "gltf-3d"],
      "views": [
        {"id": "anterior", "label": "Anterior", "available": True},
        {"id": "posterior", "label": "Posterior", "available": False, "note": "Future view"},
      ],
      "layers": [
        {"id": "organ", "label": "Organs"},
        {"id": "skeletal", "label": "Skeletal"},
        {"id": "muscular", "label": "Muscular"},
      ],
      "capabilities": {
        "zoom": True,
        "hover": True,
        "highlight": True,
        "click_to_open": True,
        "rotate": False,
        "rotate_future_ready": True,
        "renderer_3d_future_ready": True,
      },
      "items": items,
      "total": len(items),
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Interactive body explorer is for educational navigation only.",
      },
    }

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _empty_progress(body_system_id: int) -> dict[str, Any]:
    return {
      "id": None,
      "user_id": None,
      "body_system_id": body_system_id,
      "status": "not_started",
      "progress_percent": 0,
      "study_minutes": 0,
      "lessons_completed": 0,
      "lessons_total": 0,
      "last_course_id": None,
      "last_lesson_id": None,
      "last_organ_id": None,
      "started_at": None,
      "completed_at": None,
      "updated_at": None,
    }

  @staticmethod
  def _resolve_system(slug_or_id: str, *, include_inactive: bool = False) -> BodySystem | None:
    raw = (slug_or_id or "").strip()
    if not raw:
      return None
    query = BodySystem.query
    if not include_inactive:
      query = query.filter(BodySystem.is_active.is_(True))
    if raw.isdigit():
      return query.filter_by(id=int(raw)).first()
    return query.filter_by(slug=raw).first()

  @staticmethod
  def _resolve_organ(slug_or_id: str, *, system_slug: str | None = None) -> Organ | None:
    raw = (slug_or_id or "").strip()
    if not raw:
      return None
    query = Organ.query.filter(Organ.is_active.is_(True))
    if system_slug:
      system = BodySystemHubService._resolve_system(system_slug)
      if not system:
        return None
      query = query.filter(Organ.body_system_id == system.id)
    if raw.isdigit():
      return query.filter_by(id=int(raw)).first()
    return query.filter_by(slug=raw).first()

  @staticmethod
  def _resolve_disease(slug_or_id: str, *, system_slug: str | None = None) -> HubDisease | None:
    raw = (slug_or_id or "").strip()
    if not raw:
      return None
    query = HubDisease.query.filter(HubDisease.is_active.is_(True))
    if system_slug:
      system = BodySystemHubService._resolve_system(system_slug)
      if not system:
        return None
      query = query.filter(HubDisease.body_system_id == system.id)
    if raw.isdigit():
      return query.filter_by(id=int(raw)).first()
    return query.filter_by(slug=raw).first()
