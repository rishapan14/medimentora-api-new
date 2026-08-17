"""Hub clinical cases + disease explorer wiring (Phase 9).

Reuses ClinicalCase LMS rows and HubDiseaseClinicalCase links.
Educational simulations only — never a real diagnosis tool.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import or_

from app.extensions import db
from app.models.body_system_model import (
  BodySystem,
  HubDisease,
  HubDiseaseClinicalCase,
  Organ,
)
from app.models.clinical_case_model import ClinicalCase
from app.services.body_systems.hub_service import BodySystemHubService, slugify
from app.utils import utc_now

logger = logging.getLogger(__name__)

HUB_CASE_PREFIX = "[Hub]"


class HubCaseService:
  """Generate and list educational hub clinical cases."""

  @classmethod
  def list_system_cases(
    cls,
    system_slug: str,
    *,
    organ_slug: str | None = None,
    disease_slug: str | None = None,
  ) -> dict[str, Any] | None:
    system = BodySystemHubService._resolve_system(system_slug)
    if not system:
      return None

    disease_query = HubDisease.query.filter_by(body_system_id=system.id, is_active=True).filter(
      or_(HubDisease.is_published.is_(True), HubDisease.is_published.is_(None))
    )
    if organ_slug:
      organ = Organ.query.filter_by(body_system_id=system.id, slug=organ_slug.strip()).first()
      if organ:
        disease_query = disease_query.filter(HubDisease.organ_id == organ.id)
    if disease_slug:
      disease_query = disease_query.filter(HubDisease.slug == disease_slug.strip())

    diseases = disease_query.order_by(HubDisease.sort_order, HubDisease.name).all()
    disease_ids = [d.id for d in diseases]
    items: list[dict[str, Any]] = []
    seen_case_ids: set[int] = set()

    if disease_ids:
      links = (
        HubDiseaseClinicalCase.query.filter(HubDiseaseClinicalCase.disease_id.in_(disease_ids))
        .order_by(HubDiseaseClinicalCase.sort_order, HubDiseaseClinicalCase.id)
        .all()
      )
      disease_by_id = {d.id: d for d in diseases}
      for link in links:
        case = ClinicalCase.query.get(link.clinical_case_id)
        if not case or not case.is_published or case.id in seen_case_ids:
          continue
        seen_case_ids.add(case.id)
        disease = disease_by_id.get(link.disease_id)
        items.append(
          {
            **link.to_dict(),
            "clinical_case": case.to_dict(),
            "hub_disease": disease.to_dict() if disease else None,
          }
        )

    return {
      "body_system": system.to_dict(include_counts=False),
      "items": items,
      "total": len(items),
      "diseases": [d.to_dict() for d in diseases],
      "walkthrough_steps": [
        "patient",
        "history",
        "symptoms",
        "vitals",
        "lab_reports",
        "xray",
        "questions",
        "ai_explanation",
        "correct_answer",
        "learning_points",
      ],
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Hub clinical cases are educational simulations only.",
      },
    }

  @classmethod
  def generate_system_cases(
    cls,
    system_slug: str,
    *,
    organ_slug: str | None = None,
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

    diseases = cls._ensure_diseases(system, organ)
    if not diseases:
      return None, "validation_error"

    existing = cls.list_system_cases(
      system.slug, organ_slug=organ.slug if organ else None
    )
    if existing and existing["total"] > 0 and not force:
      existing["generated"] = False
      return existing, "ok"

    if force and existing:
      for item in existing.get("items") or []:
        case_id = (item.get("clinical_case") or {}).get("id")
        link_id = item.get("id")
        if link_id:
          link = HubDiseaseClinicalCase.query.get(link_id)
          if link:
            db.session.delete(link)
        if case_id:
          case = ClinicalCase.query.get(case_id)
          if case and str(case.title or "").startswith(HUB_CASE_PREFIX):
            db.session.delete(case)
      db.session.commit()

    created = 0
    for disease in diseases[:4]:
      case = cls._build_case(system, organ, disease, user_id=user_id)
      db.session.add(case)
      db.session.flush()
      link = HubDiseaseClinicalCase(
        disease_id=disease.id,
        clinical_case_id=case.id,
        sort_order=created,
      )
      db.session.add(link)
      created += 1
    db.session.commit()

    payload = cls.list_system_cases(system.slug, organ_slug=organ.slug if organ else None)
    if payload is None:
      return None, "not_found"
    payload["generated"] = True
    payload["created_count"] = created
    return payload, "ok"

  @classmethod
  def ensure_disease_cases_on_get(cls, disease: HubDisease) -> list[dict[str, Any]]:
    links = (
      HubDiseaseClinicalCase.query.filter_by(disease_id=disease.id)
      .order_by(HubDiseaseClinicalCase.sort_order, HubDiseaseClinicalCase.id)
      .all()
    )
    out = []
    for link in links:
      case = ClinicalCase.query.get(link.clinical_case_id)
      if case and case.is_published:
        out.append({**link.to_dict(), "clinical_case": case.to_dict()})
    return out

  @classmethod
  def _ensure_diseases(cls, system: BodySystem, organ: Organ | None) -> list[HubDisease]:
    query = HubDisease.query.filter_by(body_system_id=system.id, is_active=True)
    if organ:
      query = query.filter_by(organ_id=organ.id)
    existing = query.order_by(HubDisease.sort_order, HubDisease.name).all()
    if existing:
      return existing

    seeds = cls._disease_seeds(system, organ)
    created: list[HubDisease] = []
    for idx, seed in enumerate(seeds):
      slug = slugify(seed["name"])
      row = HubDisease.query.filter_by(body_system_id=system.id, slug=slug).first()
      if row:
        created.append(row)
        continue
      row = HubDisease(
        body_system_id=system.id,
        organ_id=organ.id if organ else None,
        slug=slug,
        name=seed["name"],
        short_description=seed.get("summary"),
        content_json=seed.get("content_json") or {},
        difficulty="intermediate",
        topic_tags=seed.get("tags") or [],
        is_active=True,
        is_published=True,
        sort_order=idx * 10,
      )
      db.session.add(row)
      created.append(row)
    if created:
      db.session.commit()
    return created

  @classmethod
  def _disease_seeds(cls, system: BodySystem, organ: Organ | None) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    organs = [organ] if organ else (
      Organ.query.filter_by(body_system_id=system.id, is_active=True)
      .order_by(Organ.sort_order)
      .limit(3)
      .all()
    )
    for o in organs:
      cj = o.content_json if isinstance(o.content_json, dict) else {}
      diseases = cj.get("common_diseases") if isinstance(cj.get("common_diseases"), list) else []
      signs = cj.get("signs") or []
      symptoms = cj.get("symptoms") or []
      investigations = cj.get("investigations") or []
      nursing = cj.get("nursing_care") or []
      treatment = cj.get("treatment_overview")
      for d in diseases[:3]:
        if not isinstance(d, dict):
          continue
        name = str(d.get("name") or "").replace(" (educational)", "").strip()
        summary = str(d.get("summary") or "").strip()
        if not name:
          continue
        seeds.append(
          {
            "name": name,
            "summary": summary,
            "tags": [system.slug, o.slug],
            "content_json": {
              "overview": summary,
              "signs": signs[:5],
              "symptoms": symptoms[:5],
              "investigations": investigations[:5],
              "treatment_overview": treatment,
              "nursing_care": nursing[:5],
              "organ": o.name,
              "safety": {"educational_only": True, "not_a_diagnosis": True},
            },
          }
        )
    if not seeds:
      seeds.append(
        {
          "name": f"{system.name} educational case theme",
          "summary": system.short_description or f"Learning theme for {system.name}.",
          "tags": [system.slug],
          "content_json": {
            "overview": system.short_description,
            "signs": [],
            "symptoms": [],
            "investigations": [],
            "nursing_care": [],
            "safety": {"educational_only": True, "not_a_diagnosis": True},
          },
        }
      )
    return seeds

  @classmethod
  def _build_case(
    cls,
    system: BodySystem,
    organ: Organ | None,
    disease: HubDisease,
    *,
    user_id: int | None,
  ) -> ClinicalCase:
    dc = disease.content_json if isinstance(disease.content_json, dict) else {}
    organ_name = organ.name if organ else (dc.get("organ") or system.name)
    symptoms = [str(s) for s in (dc.get("symptoms") or []) if str(s).strip()] or [
      "Educational symptom pattern for learning discussion"
    ]
    signs = [str(s) for s in (dc.get("signs") or []) if str(s).strip()]
    investigations = [str(i) for i in (dc.get("investigations") or []) if str(i).strip()]
    nursing = [str(n) for n in (dc.get("nursing_care") or []) if str(n).strip()]
    overview = str(dc.get("overview") or disease.short_description or disease.name)

    content = {
      "patient": (
        f"Educational simulated patient presenting for {disease.name} learning discussion "
        f"(linked to {organ_name} / {system.name})."
      ),
      "history": (
        f"Learner reviews a brief educational history consistent with themes of {disease.name}. "
        "This is not a real patient record."
      ),
      "symptoms": symptoms,
      "vitals": {
        "HR": "educational example — interpret in context",
        "BP": "educational example — interpret in context",
        "RR": "educational example — interpret in context",
        "SpO2": "educational example — interpret in context",
        "Temp": "educational example — interpret in context",
      },
      "lab_reports": investigations[:4]
      or ["Educational lab panel discussion points (no real values invented as facts)"],
      "xray": (
        f"Educational imaging discussion for {organ_name} findings that may be discussed "
        f"alongside {disease.name} themes — not a diagnostic read."
      ),
      "questions": [
        {
          "prompt": f"Which educational assessment priorities fit a learner case about {disease.name}?",
          "hint": "Think nursing/medical learning frameworks, not personal diagnosis.",
        },
        {
          "prompt": f"List two educational investigations commonly discussed with {disease.name}.",
          "hint": "Use the investigations section of the disease explorer.",
        },
      ],
      "ai_explanation": (
        f"Educational explanation: {overview} Focus on anatomy, physiology, and safe learning "
        "language. Never treat this as a personal diagnosis."
      ),
      "correct_answer": (
        f"Learning focus: recognize educational patterns associated with {disease.name} "
        f"and escalate real patients to licensed clinicians."
      ),
      "learning_points": nursing[:4]
      or [
        f"Map {disease.name} to {organ_name} anatomy/physiology.",
        "Use cautious educational language (possible / may be consistent with).",
        "Differentiate learning content from clinical decision-making.",
      ],
      "signs": signs,
      "safety": {"educational_only": True, "not_a_diagnosis": True},
    }

    return ClinicalCase(
      created_by=user_id,
      title=f"{HUB_CASE_PREFIX} {disease.name} — {organ_name}",
      disease=disease.name,
      symptoms=symptoms,
      diagnosis=content["correct_answer"],
      treatment=str(dc.get("treatment_overview") or "Educational treatment overview only — clinician-directed in real care."),
      difficulty="medium",
      speciality=system.name,
      description=(
        f"Educational clinical case simulation for {disease.name} "
        f"({system.name}). For learning only."
      ),
      content_json=content,
      is_published=True,
    )
