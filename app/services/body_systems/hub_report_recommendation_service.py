"""Map AI medical report findings → Body Systems Hub recommendations (Phase 10).

Educational only — never a diagnosis. Example:
Low Hemoglobin → Circulatory → Anemia themes → quiz / flashcards / cases.
"""

from __future__ import annotations

import logging
from typing import Any

from app.extensions import db
from app.models.body_system_model import BodySystem, HubDisease, HubRecommendation, Organ
from app.models.report_analysis_model import ReportAnalysis

logger = logging.getLogger(__name__)

REPORT_REC_VERSION = "phase10-3d-v1"

# Signal substring → hub learning target (educational mapping)
FINDING_HUB_MAP: list[dict[str, Any]] = [
  {
    "signals": ["hemoglobin", "hb", "hgb", "anemia", "haemoglobin", "rbc", "hematocrit", "pcv"],
    "system_slug": "circulatory",
    "organ_slug": None,
    "disease_keywords": ["anemia", "anaemia"],
    "title": "Study circulatory themes for anemia / hemoglobin learning",
    "topics": ["Anemia", "Iron metabolism", "Blood", "Circulatory system"],
    "priority": 90,
  },
  {
    "signals": ["wbc", "leukocyte", "white blood", "neutrophil", "infection"],
    "system_slug": "immune",
    "organ_slug": "spleen",
    "disease_keywords": [],
    "title": "Study immune system themes from white-cell findings",
    "topics": ["Immune system", "Infection response"],
    "priority": 75,
  },
  {
    "signals": ["creatinine", "urea", "bun", "egfr", "kidney", "renal"],
    "system_slug": "urinary",
    "organ_slug": "kidneys",
    "disease_keywords": ["kidney", "aki", "ckd"],
    "title": "Study urinary / kidney learning path",
    "topics": ["Kidney function", "Urinary system"],
    "priority": 85,
  },
  {
    "signals": ["glucose", "sugar", "hba1c", "diabetes"],
    "system_slug": "digestive",
    "organ_slug": "pancreas",
    "disease_keywords": ["diabetes"],
    "title": "Study pancreas / glucose regulation themes",
    "topics": ["Pancreas", "Glucose metabolism"],
    "priority": 80,
  },
  {
    "signals": ["alt", "ast", "bilirubin", "liver", "alp", "ggt"],
    "system_slug": "digestive",
    "organ_slug": "liver",
    "disease_keywords": ["hepatitis", "cirrhosis", "liver"],
    "title": "Study liver educational themes",
    "topics": ["Liver", "Digestive system"],
    "priority": 80,
  },
  {
    "signals": ["ldl", "hdl", "cholesterol", "triglyceride", "lipid"],
    "system_slug": "circulatory",
    "organ_slug": "heart",
    "disease_keywords": ["coronary"],
    "title": "Study heart / circulatory lipid-related themes",
    "topics": ["Heart", "Circulatory system"],
    "priority": 70,
  },
  {
    "signals": ["troponin", "bnp", "ck-mb", "cardiac"],
    "system_slug": "circulatory",
    "organ_slug": "heart",
    "disease_keywords": ["heart failure", "coronary"],
    "title": "Study heart educational assessment themes",
    "topics": ["Heart", "Cardiac markers (educational)"],
    "priority": 88,
  },
  {
    "signals": ["platelets", "pt", "inr", "aptt", "coagulation"],
    "system_slug": "circulatory",
    "organ_slug": None,
    "disease_keywords": [],
    "title": "Study circulatory coagulation learning themes",
    "topics": ["Circulatory system", "Coagulation (educational)"],
    "priority": 65,
  },
]


class HubReportRecommendationService:
  """Build HubRecommendation rows from ReportAnalysis findings."""

  @classmethod
  def recommend_for_analysis(
    cls, analysis: ReportAnalysis, *, user_id: int | None = None
  ) -> list[dict[str, Any]]:
    uid = int(user_id or analysis.user_id)
    # Replace prior report recommendations for this analysis
    HubRecommendation.query.filter_by(
      user_id=uid, source_type="report", source_id=analysis.id
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

      system_href = f"/learning/body-systems/{match['system_slug']}" if match.get("system_slug") else "/learning/body-systems"
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
        f"Educational suggestion based on report findings related to "
        f"{', '.join(match.get('matched_signals') or match.get('topics') or ['lab themes'])}. "
        "Not a diagnosis — use the Body Systems Hub to study related anatomy and nursing themes."
      )
      row = HubRecommendation(
        user_id=uid,
        body_system_id=system.id if system else None,
        organ_id=organ.id if organ else None,
        disease_id=disease.id if disease else None,
        source_type="report",
        source_id=analysis.id,
        title=match["title"],
        reason=reason,
        href=organ_href if organ else system_href,
        priority=int(match.get("priority") or 50),
        is_read=False,
        meta_json={
          "version": REPORT_REC_VERSION,
          "analysis_id": analysis.id,
          "report_id": analysis.report_id,
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
  def list_for_user(
    cls,
    user_id: int,
    *,
    source_type: str | None = "report",
    source_id: int | None = None,
    limit: int = 20,
  ) -> dict[str, Any]:
    limit = min(50, max(1, int(limit or 20)))
    query = HubRecommendation.query.filter_by(user_id=user_id)
    if source_type:
      query = query.filter_by(source_type=source_type)
    if source_id is not None:
      query = query.filter_by(source_id=int(source_id))
    rows = query.order_by(HubRecommendation.priority.desc(), HubRecommendation.created_at.desc()).limit(limit).all()
    return {
      "items": [r.to_dict() for r in rows],
      "total": len(rows),
      "source_type": source_type,
      "safety": {
        "educational_only": True,
        "not_a_diagnosis": True,
        "note": "Report-linked recommendations are educational study suggestions only.",
      },
    }

  @classmethod
  def _explorer_3d_href(
    cls,
    *,
    organ_slug: str | None,
    system_slug: str | None,
    analysis_id: int,
  ) -> str:
    """Deep-link into the 3D Human Body Explorer for report-driven study."""
    params: list[str] = [f"from=report", f"source_id={int(analysis_id)}"]
    if organ_slug:
      params.insert(0, f"part={organ_slug}")
    elif system_slug:
      params.insert(0, f"mode={system_slug}")
    return "/learning/body-systems/explorer-3d?" + "&".join(params)

  @classmethod
  def _match_findings(cls, analysis: ReportAnalysis) -> list[dict[str, Any]]:
    blobs: list[str] = []
    for item in analysis.abnormal_values or []:
      if isinstance(item, dict):
        blobs.append(" ".join(str(item.get(k) or "") for k in ("name", "significance", "status", "value")))
      else:
        blobs.append(str(item))
    for item in analysis.possible_diseases or []:
      if isinstance(item, dict):
        blobs.append(" ".join(str(item.get(k) or "") for k in ("disease", "reasoning", "likelihood")))
      else:
        blobs.append(str(item))
    for topic in analysis.learning_topics or []:
      blobs.append(str(topic))

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
      # Prefer first/highest priority match per system
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
