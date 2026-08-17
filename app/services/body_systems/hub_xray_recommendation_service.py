"""Map AI X-ray findings → Body Systems Hub recommendations (Phase 11).

Educational only — never a diagnosis. Example:
Pneumonia-like finding → Respiratory → Lungs → quiz / flashcards / cases.
"""

from __future__ import annotations

import logging
from typing import Any

from app.extensions import db
from app.models.body_system_model import BodySystem, HubDisease, HubRecommendation, Organ
from app.models.xray_analysis_model import XrayAnalysis

logger = logging.getLogger(__name__)

XRAY_REC_VERSION = "phase11-3d-v1"

# Finding / body-part signal → hub learning target (educational mapping)
FINDING_HUB_MAP: list[dict[str, Any]] = [
  {
    "signals": [
      "pneumonia",
      "consolidation",
      "opacity",
      "atelectasis",
      "infiltrate",
      "lung",
    ],
    "system_slug": "respiratory",
    "organ_slug": "lungs",
    "disease_keywords": ["pneumonia"],
    "title": "Study respiratory themes from chest X-ray findings",
    "topics": ["Respiratory system", "Lung anatomy", "Chest X-ray interpretation"],
    "priority": 92,
  },
  {
    "signals": ["pleural effusion", "effusion", "pleural"],
    "system_slug": "respiratory",
    "organ_slug": "lungs",
    "disease_keywords": ["effusion", "pleural"],
    "title": "Study pleural / respiratory educational themes",
    "topics": ["Pleural space", "Respiratory system"],
    "priority": 88,
  },
  {
    "signals": ["pneumothorax"],
    "system_slug": "respiratory",
    "organ_slug": "lungs",
    "disease_keywords": ["pneumothorax"],
    "title": "Study pneumothorax educational assessment themes",
    "topics": ["Respiratory system", "Thoracic anatomy"],
    "priority": 90,
  },
  {
    "signals": ["cardiomegaly", "cardiac silhouette", "heart enlargement", "cardiac"],
    "system_slug": "circulatory",
    "organ_slug": "heart",
    "disease_keywords": ["heart failure", "cardiomegaly"],
    "title": "Study heart / circulatory themes from chest X-ray findings",
    "topics": ["Heart", "Circulatory system", "Chest X-ray interpretation"],
    "priority": 90,
  },
  {
    "signals": ["nodule", "mass", "lesion"],
    "system_slug": "respiratory",
    "organ_slug": "lungs",
    "disease_keywords": [],
    "title": "Study pulmonary pathology educational themes",
    "topics": ["Lung anatomy", "Pulmonary pathology (educational)"],
    "priority": 75,
  },
  {
    "signals": ["fracture", "break", "broken"],
    "system_slug": "skeletal",
    "organ_slug": "bones",
    "disease_keywords": ["fracture"],
    "title": "Study skeletal / fracture learning path",
    "topics": ["Skeletal system", "Bone anatomy", "Fracture care (educational)"],
    "priority": 88,
  },
  {
    "signals": ["dislocation", "joint", "soft tissue"],
    "system_slug": "skeletal",
    "organ_slug": "bones",
    "disease_keywords": [],
    "title": "Study musculoskeletal / joint educational themes",
    "topics": ["Skeletal system", "Joint assessment (educational)"],
    "priority": 78,
  },
  {
    "signals": ["spine", "vertebral", "cervical", "lumbar", "thoracic spine"],
    "system_slug": "skeletal",
    "organ_slug": "bones",
    "disease_keywords": [],
    "title": "Study spine / skeletal educational themes",
    "topics": ["Skeletal system", "Spine anatomy"],
    "priority": 80,
  },
]

# Body-part fallback when findings are sparse / normal-only
BODY_PART_HUB_MAP: list[dict[str, Any]] = [
  {
    "signals": ["chest", "thorax", "lung"],
    "system_slug": "respiratory",
    "organ_slug": "lungs",
    "disease_keywords": [],
    "title": "Study respiratory system from chest imaging context",
    "topics": ["Respiratory system", "Chest X-ray interpretation"],
    "priority": 55,
  },
  {
    "signals": [
      "hand",
      "wrist",
      "finger",
      "elbow",
      "shoulder",
      "clavicle",
      "spine",
      "pelvis",
      "hip",
      "femur",
      "knee",
      "leg",
      "ankle",
      "foot",
      "bone",
    ],
    "system_slug": "skeletal",
    "organ_slug": "bones",
    "disease_keywords": [],
    "title": "Study skeletal system from musculoskeletal imaging context",
    "topics": ["Skeletal system", "Bone anatomy"],
    "priority": 55,
  },
]


class HubXrayRecommendationService:
  """Build HubRecommendation rows from XrayAnalysis findings."""

  @classmethod
  def recommend_for_analysis(
    cls, analysis: XrayAnalysis, *, user_id: int | None = None
  ) -> list[dict[str, Any]]:
    uid = int(user_id or analysis.user_id)
    HubRecommendation.query.filter_by(
      user_id=uid, source_type="xray", source_id=analysis.id
    ).delete(synchronize_session=False)

    matches = cls._match_findings(analysis)
    created: list[HubRecommendation] = []
    for match in matches:
      system = BodySystem.query.filter_by(slug=match["system_slug"], is_active=True).first()
      organ = None
      if match.get("organ_slug") and system:
        organ = Organ.query.filter_by(
          body_system_id=system.id, slug=match["organ_slug"], is_active=True
        ).first()
      disease = cls._resolve_disease(system, match.get("disease_keywords") or [])

      system_href = (
        f"/learning/body-systems/{match['system_slug']}"
        if match.get("system_slug")
        else "/learning/body-systems"
      )
      organ_href = (
        f"{system_href}/organs/{match['organ_slug']}"
        if match.get("organ_slug") and match.get("system_slug")
        else system_href
      )
      explorer_3d = cls._explorer_3d_href(
        organ_slug=match.get("organ_slug"),
        system_slug=match.get("system_slug"),
        analysis_id=analysis.id,
      )
      links = {
        "system": system_href,
        "organ": organ_href if match.get("organ_slug") else None,
        "quiz": system_href,
        "flashcards": system_href,
        "cases": system_href,
        "explorer": "/learning/body-systems/explorer",
        "explorer_3d": explorer_3d,
      }

      reason = (
        f"Educational suggestion based on X-ray findings related to "
        f"{', '.join(match.get('matched_signals') or match.get('topics') or ['imaging themes'])}. "
        "Not a diagnosis — use the Body Systems Hub to study related anatomy and nursing themes."
      )
      row = HubRecommendation(
        user_id=uid,
        body_system_id=system.id if system else None,
        organ_id=organ.id if organ else None,
        disease_id=disease.id if disease else None,
        source_type="xray",
        source_id=analysis.id,
        title=match["title"],
        reason=reason,
        href=organ_href if organ else system_href,
        priority=int(match.get("priority") or 50),
        is_read=False,
        meta_json={
          "version": XRAY_REC_VERSION,
          "xray_id": analysis.id,
          "body_part": analysis.body_part,
          "matched_signals": match.get("matched_signals") or [],
          "topics": match.get("topics") or [],
          "links": links,
          "educational_path": [
            (system.name if system else match.get("system_slug")),
            (organ.name if organ else None),
            (disease.name if disease else (match.get("topics") or [None])[0]),
            "Quiz",
            "Flashcards",
            "Clinical Cases",
          ],
          "safety": {
            "educational_only": True,
            "not_a_diagnosis": True,
          },
        },
      )
      db.session.add(row)
      created.append(row)

    db.session.commit()
    return [r.to_dict() for r in created]

  @classmethod
  def _explorer_3d_href(
    cls,
    *,
    organ_slug: str | None,
    system_slug: str | None,
    analysis_id: int,
  ) -> str:
    """Deep-link into the 3D Human Body Explorer for X-ray-driven study."""
    params: list[str] = ["from=xray", f"source_id={int(analysis_id)}"]
    if organ_slug:
      params.insert(0, f"part={organ_slug}")
    elif system_slug:
      params.insert(0, f"mode={system_slug}")
    return "/learning/body-systems/explorer-3d?" + "&".join(params)

  @classmethod
  def list_for_user(
    cls,
    user_id: int,
    *,
    source_type: str | None = "xray",
    source_id: int | None = None,
    limit: int = 20,
  ) -> dict[str, Any]:
    limit = min(50, max(1, int(limit or 20)))
    query = HubRecommendation.query.filter_by(user_id=user_id)
    if source_type:
      query = query.filter_by(source_type=source_type)
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
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "X-ray-linked recommendations are educational study suggestions only.",
      },
    }

  @classmethod
  def list_for_xray(cls, xray_id: int, *, user_id: int | None = None) -> list[dict[str, Any]]:
    query = HubRecommendation.query.filter_by(source_type="xray", source_id=int(xray_id))
    if user_id is not None:
      query = query.filter_by(user_id=int(user_id))
    rows = query.order_by(HubRecommendation.priority.desc(), HubRecommendation.created_at.desc()).all()
    return [r.to_dict() for r in rows]

  @classmethod
  def _match_findings(cls, analysis: XrayAnalysis) -> list[dict[str, Any]]:
    blobs: list[str] = []
    findings = analysis.possible_findings or []
    if not findings and isinstance(analysis.structured_findings, dict):
      findings = analysis.structured_findings.get("findings") or []
    for item in findings:
      if isinstance(item, dict):
        blobs.append(
          " ".join(
            str(item.get(k) or "")
            for k in ("label", "name", "finding", "region", "rationale", "certainty")
          )
        )
      else:
        blobs.append(str(item))
    if analysis.body_part:
      blobs.append(str(analysis.body_part))
    if analysis.ai_summary:
      blobs.append(str(analysis.ai_summary))
    for topic_list in (analysis.learning_recommendations or []):
      if isinstance(topic_list, dict):
        blobs.append(str(topic_list.get("title") or ""))
        for t in topic_list.get("topics") or []:
          blobs.append(str(t))

    haystack = " ".join(blobs).lower()
    if not haystack.strip():
      return []

    matched: list[dict[str, Any]] = []
    seen_systems: set[str] = set()
    for rule in FINDING_HUB_MAP:
      hits = [s for s in rule["signals"] if s in haystack]
      if not hits:
        continue
      key = rule["system_slug"]
      if key in seen_systems:
        continue
      seen_systems.add(key)
      row = dict(rule)
      row["matched_signals"] = hits
      matched.append(row)

    # Body-part fallback if no finding-based match
    if not matched:
      for rule in BODY_PART_HUB_MAP:
        hits = [s for s in rule["signals"] if s in haystack]
        if not hits:
          continue
        key = rule["system_slug"]
        if key in seen_systems:
          continue
        seen_systems.add(key)
        row = dict(rule)
        row["matched_signals"] = hits
        matched.append(row)

    matched.sort(key=lambda r: int(r.get("priority") or 0), reverse=True)
    return matched[:6]

  @classmethod
  def _resolve_disease(cls, system: BodySystem | None, keywords: list[str]) -> HubDisease | None:
    if not system or not keywords:
      return None
    for kw in keywords:
      like = f"%{kw}%"
      row = (
        HubDisease.query.filter_by(body_system_id=system.id, is_active=True)
        .filter(HubDisease.name.ilike(like))
        .first()
      )
      if row:
        return row
    return None
