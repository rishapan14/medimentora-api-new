"""Hub flashcard generation, favorites, and study helpers (Phase 8)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_

from app.extensions import db
from app.models.body_system_model import (
  BodySystem,
  HubFlashcard,
  HubFlashcardFavorite,
  Organ,
)
from app.services.body_systems.hub_service import BodySystemHubService
from app.utils import utc_now

logger = logging.getLogger(__name__)

CARD_LEVELS = ("basic", "advanced", "exam_revision")


class HubFlashcardService:
  """Generate and manage educational hub flashcards."""

  @classmethod
  def list_cards(
    cls,
    *,
    user_id: int | None = None,
    system_slug: str | None = None,
    organ_slug: str | None = None,
    card_level: str | None = None,
    favorites_only: bool = False,
    page: int = 1,
    per_page: int = 40,
  ) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 40)))

    query = HubFlashcard.query.filter(
      or_(HubFlashcard.is_published.is_(True), HubFlashcard.is_published.is_(None))
    )
    system = None
    organ = None
    if system_slug:
      system = BodySystemHubService._resolve_system(system_slug)
      if not system:
        return cls._empty(page, per_page)
      query = query.filter(HubFlashcard.body_system_id == system.id)
    if organ_slug:
      organ_q = Organ.query.filter_by(slug=organ_slug.strip())
      if system:
        organ_q = organ_q.filter_by(body_system_id=system.id)
      organ = organ_q.first()
      if organ:
        query = query.filter(HubFlashcard.organ_id == organ.id)
    if card_level:
      level = card_level.strip().lower().replace("-", "_").replace(" ", "_")
      if level in ("exam", "examrevision"):
        level = "exam_revision"
      query = query.filter(HubFlashcard.card_level == level)

    fav_ids: set[int] = set()
    if user_id:
      fav_ids = {
        row.flashcard_id
        for row in HubFlashcardFavorite.query.filter_by(user_id=user_id)
        .with_entities(HubFlashcardFavorite.flashcard_id)
        .all()
      }
      if favorites_only:
        if not fav_ids:
          return cls._empty(page, per_page, system=system, organ=organ)
        query = query.filter(HubFlashcard.id.in_(fav_ids))

    total = query.count()
    rows = query.order_by(HubFlashcard.card_level, HubFlashcard.id).offset((page - 1) * per_page).limit(per_page).all()
    items = []
    for card in rows:
      data = card.to_dict()
      data["is_favorite"] = card.id in fav_ids
      items.append(data)

    return {
      "items": items,
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "levels": [{"id": lv, "label": lv.replace("_", " ").title()} for lv in CARD_LEVELS],
      "body_system": system.to_dict(include_counts=False) if system else None,
      "organ": organ.to_dict() if organ else None,
      "spaced_repetition": {
        "available": False,
        "future_ready": True,
        "note": "Favorites store SR fields for a future scheduler.",
      },
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Flashcards are for educational revision only.",
      },
    }

  @classmethod
  def generate(
    cls,
    *,
    system_slug: str,
    organ_slug: str | None = None,
    levels: list[str] | None = None,
    force: bool = False,
    user_id: int | None = None,
  ) -> tuple[dict[str, Any] | None, str]:
    system = BodySystemHubService._resolve_system(system_slug)
    if not system:
      return None, "not_found"

    organ = None
    if organ_slug:
      organ = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug.strip()).first()
      if not organ:
        return None, "not_found"

    target_levels = [lv for lv in (levels or list(CARD_LEVELS)) if lv in CARD_LEVELS]
    if not target_levels:
      target_levels = list(CARD_LEVELS)

    existing_q = HubFlashcard.query.filter_by(body_system_id=system.id)
    if organ:
      existing_q = existing_q.filter_by(organ_id=organ.id)
    else:
      existing_q = existing_q.filter(HubFlashcard.organ_id.is_(None))

    if force:
      existing_q.delete(synchronize_session=False)
      db.session.commit()
    elif existing_q.count() > 0:
      payload = cls.list_cards(
        user_id=user_id,
        system_slug=system.slug,
        organ_slug=organ.slug if organ else None,
        per_page=100,
      )
      payload["generated"] = False
      return payload, "ok"

    specs = cls._build_specs(system, organ, target_levels)
    if not specs:
      return None, "validation_error"

    created = 0
    for spec in specs:
      db.session.add(
        HubFlashcard(
          body_system_id=system.id,
          organ_id=organ.id if organ else None,
          front_text=spec["front"],
          back_text=spec["back"],
          card_level=spec["level"],
          topic_tags=spec.get("tags") or [],
          is_published=True,
          created_by=user_id,
        )
      )
      created += 1
    db.session.commit()

    payload = cls.list_cards(
      user_id=user_id,
      system_slug=system.slug,
      organ_slug=organ.slug if organ else None,
      per_page=100,
    )
    payload["generated"] = True
    payload["created_count"] = created
    return payload, "ok"

  @classmethod
  def add_favorite(cls, user_id: int, flashcard_id: int) -> tuple[dict[str, Any] | None, str]:
    card = HubFlashcard.query.get(flashcard_id)
    if not card or not card.is_published:
      return None, "not_found"
    existing = HubFlashcardFavorite.query.filter_by(
      user_id=user_id, flashcard_id=flashcard_id
    ).first()
    if existing:
      return existing.to_dict(include_card=True), "ok"
    fav = HubFlashcardFavorite(
      user_id=user_id,
      flashcard_id=flashcard_id,
      ease_factor=2.5,
      interval_days=0,
      repetitions=0,
      next_review_at=None,
    )
    db.session.add(fav)
    db.session.commit()
    return fav.to_dict(include_card=True), "ok"

  @classmethod
  def remove_favorite(cls, user_id: int, flashcard_id: int) -> tuple[bool, str]:
    fav = HubFlashcardFavorite.query.filter_by(
      user_id=user_id, flashcard_id=flashcard_id
    ).first()
    if not fav:
      return False, "not_found"
    db.session.delete(fav)
    db.session.commit()
    return True, "ok"

  @classmethod
  def list_favorites(cls, user_id: int, *, page: int = 1, per_page: int = 40) -> dict[str, Any]:
    page = max(1, int(page or 1))
    per_page = min(100, max(1, int(per_page or 40)))
    query = HubFlashcardFavorite.query.filter_by(user_id=user_id)
    total = query.count()
    rows = (
      query.order_by(HubFlashcardFavorite.created_at.desc())
      .offset((page - 1) * per_page)
      .limit(per_page)
      .all()
    )
    return {
      "items": [r.to_dict(include_card=True) for r in rows],
      "total": total,
      "page": page,
      "per_page": per_page,
      "has_more": page * per_page < total,
      "spaced_repetition": {
        "available": False,
        "future_ready": True,
      },
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def _empty(
    cls,
    page: int,
    per_page: int,
    *,
    system: BodySystem | None = None,
    organ: Organ | None = None,
  ) -> dict[str, Any]:
    return {
      "items": [],
      "total": 0,
      "page": page,
      "per_page": per_page,
      "has_more": False,
      "levels": [{"id": lv, "label": lv.replace("_", " ").title()} for lv in CARD_LEVELS],
      "body_system": system.to_dict(include_counts=False) if system else None,
      "organ": organ.to_dict() if organ else None,
      "spaced_repetition": {"available": False, "future_ready": True},
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

  @classmethod
  def _build_specs(
    cls, system: BodySystem, organ: Organ | None, levels: list[str]
  ) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if organ:
      sources = [organ]
    else:
      sources = (
        Organ.query.filter_by(body_system_id=system.id, is_active=True)
        .order_by(Organ.sort_order, Organ.name)
        .limit(5)
        .all()
      )
      if not sources:
        # System-only cards
        for level in levels:
          specs.extend(cls._system_only_specs(system, level))
        return specs

    for o in sources:
      for level in levels:
        specs.extend(cls._organ_specs(system, o, level))
    return specs[:60]

  @classmethod
  def _organ_specs(cls, system: BodySystem, organ: Organ, level: str) -> list[dict[str, Any]]:
    cj = organ.content_json if isinstance(organ.content_json, dict) else {}
    functions = [str(f) for f in (cj.get("functions") or []) if str(f).strip()]
    parts = [str(p) for p in (cj.get("parts") or []) if str(p).strip()]
    pearls = [str(p) for p in (cj.get("clinical_pearls") or []) if str(p).strip()]
    overview = str(cj.get("overview") or organ.overview or organ.short_description or "").strip()
    location = str(cj.get("location_detail") or organ.location or "").strip()
    nursing = [str(n) for n in (cj.get("nursing_care") or []) if str(n).strip()]
    diseases = cj.get("common_diseases") if isinstance(cj.get("common_diseases"), list) else []
    tags = [system.slug, organ.slug, level]

    out: list[dict[str, Any]] = []
    if level == "basic":
      if overview:
        out.append(
          {
            "front": f"What is the {organ.name}? (basic)",
            "back": overview[:500],
            "level": "basic",
            "tags": tags,
          }
        )
      if location:
        out.append(
          {
            "front": f"Where is the {organ.name} located?",
            "back": location,
            "level": "basic",
            "tags": tags,
          }
        )
      for fn in functions[:3]:
        out.append(
          {
            "front": f"Name a function of the {organ.name}.",
            "back": fn,
            "level": "basic",
            "tags": tags,
          }
        )
      for part in parts[:2]:
        out.append(
          {
            "front": f"Name a part of the {organ.name}.",
            "back": part,
            "level": "basic",
            "tags": tags,
          }
        )

    elif level == "advanced":
      phys = str(cj.get("physiology") or "").strip()
      anat = str(cj.get("anatomy") or "").strip()
      blood = str(cj.get("blood_supply") or "").strip()
      if phys:
        out.append(
          {
            "front": f"Describe key physiology of the {organ.name}.",
            "back": phys[:600],
            "level": "advanced",
            "tags": tags,
          }
        )
      if anat:
        out.append(
          {
            "front": f"Describe anatomy highlights of the {organ.name}.",
            "back": anat[:600],
            "level": "advanced",
            "tags": tags,
          }
        )
      if blood:
        out.append(
          {
            "front": f"What is the blood supply of the {organ.name}?",
            "back": blood[:500],
            "level": "advanced",
            "tags": tags,
          }
        )
      for pearl in pearls[:2]:
        out.append(
          {
            "front": f"Clinical pearl — {organ.name}",
            "back": pearl,
            "level": "advanced",
            "tags": tags,
          }
        )

    else:  # exam_revision
      for n in nursing[:3]:
        out.append(
          {
            "front": f"Exam revision: nursing consideration for {organ.name}?",
            "back": n,
            "level": "exam_revision",
            "tags": tags + ["nursing"],
          }
        )
      for d in diseases[:3]:
        if not isinstance(d, dict):
          continue
        name = str(d.get("name") or "").strip()
        summary = str(d.get("summary") or "").strip()
        if name:
          out.append(
            {
              "front": f"Exam revision: educational disease theme linked to {organ.name}?",
              "back": f"{name} — {summary}".strip(" —"),
              "level": "exam_revision",
              "tags": tags + ["disease"],
            }
          )
      objectives = organ.learning_objectives if isinstance(organ.learning_objectives, list) else []
      for obj in objectives[:3]:
        out.append(
          {
            "front": f"Learning objective check — {organ.name}",
            "back": str(obj),
            "level": "exam_revision",
            "tags": tags + ["objective"],
          }
        )
      if not out and overview:
        out.append(
          {
            "front": f"Exam revision: summarize the {organ.name}.",
            "back": overview[:500],
            "level": "exam_revision",
            "tags": tags,
          }
        )

    return out

  @classmethod
  def _system_only_specs(cls, system: BodySystem, level: str) -> list[dict[str, Any]]:
    return [
      {
        "front": f"What is the {system.name}? ({level.replace('_', ' ')})",
        "back": system.short_description or system.name,
        "level": level,
        "tags": [system.slug, level],
      },
      {
        "front": f"Body system slug for {system.name}?",
        "back": system.slug,
        "level": level,
        "tags": [system.slug, level],
      },
    ]
