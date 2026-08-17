"""Learning recommendations from X-ray findings + patient clinical context (Phase 13).

Maps educational possible findings (and supporting clinical fields) to MediMentora
Learning courses/lessons and curated topic suggestions.
Clinical fields are supporting context only — never treated as a diagnosis.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import or_

from app.extensions import db
from app.models.course_model import Course, CourseCategory, Lesson
from app.models.recommendation_model import Recommendation
from app.models.xray_analysis_model import XrayAnalysis
from app.utils import utc_now

logger = logging.getLogger(__name__)

RECOMMENDATION_VERSION = "1.3.0"

# Finding / body-part → learning topic seeds (educational only)
FINDING_TOPIC_MAP: dict[str, list[str]] = {
  "pneumonia": [
    "Respiratory System",
    "Pneumonia",
    "Chest X-ray Interpretation",
    "Lung Anatomy",
    "Nursing Care for Pneumonia",
    "Clinical Case Studies",
  ],
  "lung opacity": [
    "Respiratory System",
    "Chest X-ray Interpretation",
    "Lung Anatomy",
    "Pulmonary Pathology",
  ],
  "opacity": [
    "Chest X-ray Interpretation",
    "Lung Anatomy",
    "Respiratory System",
  ],
  "consolidation": [
    "Chest X-ray Interpretation",
    "Pneumonia",
    "Pulmonary Pathology",
    "Respiratory System",
  ],
  "atelectasis": [
    "Chest X-ray Interpretation",
    "Lung Anatomy",
    "Respiratory System",
  ],
  "nodule": [
    "Chest X-ray Interpretation",
    "Pulmonary Pathology",
    "Lung Anatomy",
  ],
  "mass": [
    "Chest X-ray Interpretation",
    "Pulmonary Pathology",
    "Clinical Case Studies",
  ],
  "pleural effusion": [
    "Pleural Effusion",
    "Respiratory System",
    "Chest X-ray Interpretation",
    "Thoracic Anatomy",
  ],
  "effusion": [
    "Pleural Effusion",
    "Chest X-ray Interpretation",
    "Respiratory System",
  ],
  "pneumothorax": [
    "Chest X-ray Interpretation",
    "Respiratory System",
    "Emergency Assessment",
    "Thoracic Anatomy",
  ],
  "cardiomegaly": [
    "Cardiology",
    "Heart Anatomy",
    "Chest X-ray Interpretation",
    "Heart Failure Basics",
    "Cardiac Assessment",
  ],
  "fracture": [
    "Musculoskeletal System",
    "Bone Anatomy",
    "Fracture Care",
    "Orthopedic Nursing",
    "Trauma Assessment",
  ],
  "dislocation": [
    "Musculoskeletal System",
    "Joint Assessment",
    "Trauma Assessment",
  ],
  "soft tissue": [
    "Musculoskeletal System",
    "Soft Tissue Injury Basics",
  ],
  "no obvious abnormality": [
    "Chest X-ray Interpretation",
    "Normal Radiograph Anatomy",
    "Systematic X-ray Reading",
  ],
  "abnormality": [
    "Chest X-ray Interpretation",
    "Systematic X-ray Reading",
  ],
}

BODY_PART_TOPICS: dict[str, list[str]] = {
  "chest": [
    "Respiratory System",
    "Chest X-ray Interpretation",
    "Lung Anatomy",
    "Cardiac Assessment",
  ],
  "hand": ["Musculoskeletal System", "Upper Limb Anatomy", "Fracture Care"],
  "wrist": ["Musculoskeletal System", "Upper Limb Anatomy", "Fracture Care"],
  "elbow": ["Musculoskeletal System", "Upper Limb Anatomy", "Fracture Care"],
  "shoulder": ["Musculoskeletal System", "Upper Limb Anatomy", "Joint Assessment"],
  "spine": ["Spine Anatomy", "Musculoskeletal System", "Neurological Assessment"],
  "pelvis": ["Musculoskeletal System", "Pelvic Anatomy", "Trauma Assessment"],
  "hip": ["Musculoskeletal System", "Lower Limb Anatomy", "Fracture Care"],
  "leg": ["Musculoskeletal System", "Lower Limb Anatomy", "Fracture Care"],
  "knee": ["Musculoskeletal System", "Lower Limb Anatomy", "Joint Assessment"],
  "foot": ["Musculoskeletal System", "Lower Limb Anatomy", "Fracture Care"],
  "ankle": ["Musculoskeletal System", "Lower Limb Anatomy", "Fracture Care"],
  "dental": ["Dental Anatomy", "Oral Health Basics"],
}

# Supporting clinical context → educational topics (never diagnostic)
SMOKING_TOPICS: dict[str, list[str]] = {
  "current smoker": [
    "COPD Basics",
    "Smoking-Related Lung Disease",
    "Respiratory System",
    "Chest X-ray Interpretation",
  ],
  "former smoker": [
    "COPD Basics",
    "Smoking-Related Lung Disease",
    "Respiratory System",
  ],
}

SYMPTOM_TOPIC_MAP: dict[str, list[str]] = {
  "cough": ["Respiratory Infection", "Pneumonia", "Chest X-ray Interpretation"],
  "fever": ["Infectious Disease Basics", "Pneumonia", "Clinical Case Studies"],
  "shortness of breath": ["Respiratory System", "Dyspnea Assessment", "Cardiac Assessment"],
  "dyspnea": ["Respiratory System", "Dyspnea Assessment", "Cardiac Assessment"],
  "chest pain": ["Cardiac Assessment", "Chest X-ray Interpretation", "Emergency Assessment"],
  "trauma": ["Trauma Assessment", "Fracture Care", "Musculoskeletal System"],
  "swelling": ["Musculoskeletal System", "Fracture Care", "Joint Assessment"],
  "pain": ["Clinical Assessment", "Pain Assessment Basics"],
}

# Educational healthy-reference comparison → study seeds (never diagnostic)
COMPARISON_BASE_TOPICS: list[str] = [
  "Normal Radiograph Anatomy",
  "Systematic X-ray Reading",
  "Chest X-ray Interpretation",
  "Clinical Case Studies",
]


@dataclass
class RecommendationResult:
  success: bool
  recommendations: list[dict[str, Any]] = field(default_factory=list)
  topics: list[str] = field(default_factory=list)
  clinical_context_used: bool = False
  comparison_aware: bool = False
  processing_time_ms: int = 0
  message: str = ""
  error_code: str | None = None

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "recommendations": self.recommendations,
      "topics": self.topics,
      "clinical_context_used": self.clinical_context_used,
      "comparison_aware": self.comparison_aware,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "error_code": self.error_code,
      "recommendation_version": RECOMMENDATION_VERSION,
      "safety": {
        "supporting_context_only": True,
        "not_a_diagnosis": True,
      },
    }


class XrayRecommendationService:
  """Build learning recommendations from findings + optional patient clinical context."""

  @classmethod
  def recommend_for_user(
    cls,
    xray_id: int,
    user_id: int,
    *,
    persist: bool = True,
    sync_user_recommendations: bool = True,
  ) -> tuple[XrayAnalysis | None, RecommendationResult]:
    started = time.perf_counter()
    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, RecommendationResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
        processing_time_ms=cls._ms(started),
      )

    comparison_context = None
    ref_path = getattr(row, "reference_image_path", None)
    comparison_summary = getattr(row, "comparison_summary", None)
    if ref_path or comparison_summary:
      explanation = getattr(row, "structured_explanation", None)
      explanation = explanation if isinstance(explanation, dict) else {}
      structured = explanation.get("educational_comparison") or {}
      ref_meta = explanation.get("comparison_reference") or {}
      if not isinstance(structured, dict):
        structured = {}
      if not isinstance(ref_meta, dict):
        ref_meta = {}
      comparison_context = {
        "body_part": row.body_part,
        "reference_body_part": ref_meta.get("body_part") or row.body_part,
        "age_group": ref_meta.get("age_group"),
        "gender": ref_meta.get("gender"),
        "learning_focus": structured.get("learning_focus") or [],
        "comparison_summary": comparison_summary,
      }

    result = cls.build_recommendations(
      possible_findings=cls.resolve_findings(row),
      body_part=row.body_part,
      patient_clinical=cls._clinical_from_row(row),
      comparison_context=comparison_context,
      user_id=user_id,
      sync_user_recommendations=sync_user_recommendations,
    )
    result.processing_time_ms = cls._ms(started)

    if persist and result.success:
      row.learning_recommendations = result.recommendations
      row.updated_at = utc_now()
      db.session.commit()
      logger.info(
        "X-ray learning recommendations id=%s count=%s topics=%s clinical=%s",
        xray_id,
        len(result.recommendations),
        len(result.topics),
        result.clinical_context_used,
      )

    return row, result

  @classmethod
  def build_recommendations(
    cls,
    *,
    possible_findings: list[Any] | None,
    body_part: str | None,
    patient_clinical: dict[str, Any] | None = None,
    comparison_context: dict[str, Any] | None = None,
    user_id: int | None = None,
    sync_user_recommendations: bool = False,
    limit: int = 12,
  ) -> RecommendationResult:
    clinical = cls._normalize_clinical(patient_clinical)
    comparison = cls._normalize_comparison(comparison_context)
    topics = cls._topics_from_findings(possible_findings, body_part, clinical, comparison)
    search_terms = cls._search_terms(topics, possible_findings, body_part, clinical, comparison)

    matched_courses = cls._match_courses(search_terms, limit=8)
    matched_lessons = cls._match_lessons(search_terms, limit=8)

    recommendations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    seen_titles: set[str] = set()

    def _add(rec: dict[str, Any], key: str) -> None:
      title_key = str(rec.get("title") or "").strip().lower()
      if key in seen_keys or (title_key and title_key in seen_titles):
        return
      seen_keys.add(key)
      if title_key:
        seen_titles.add(title_key)
      recommendations.append(rec)

    # Prefer courses first when comparison-aware so Learning hub gets actionable links
    course_items = []
    for course in matched_courses:
      course_items.append(
        {
          "type": "course",
          "title": course.title,
          "reason": cls._reason_for_course(body_part, clinical, comparison),
          "href": f"/learning/{course.id}",
          "course_id": course.id,
          "lesson_id": None,
          "category": course.category.name if course.category else course.speciality,
          "difficulty": course.difficulty,
          "priority": 1,
          "clinical_aware": bool(clinical),
          "comparison_aware": bool(comparison),
          "source": "comparison" if comparison else "analysis",
        }
      )

    lesson_items = []
    for lesson in matched_lessons:
      course_id = lesson.course_id
      lesson_items.append(
        {
          "type": "lesson",
          "title": lesson.title,
          "reason": cls._reason_for_lesson(clinical, comparison),
          "href": (
            f"/learning/{course_id}?lesson={lesson.id}" if course_id else "/learning"
          ),
          "course_id": course_id,
          "lesson_id": lesson.id,
          "priority": 1,
          "clinical_aware": bool(clinical),
          "comparison_aware": bool(comparison),
          "source": "comparison" if comparison else "analysis",
        }
      )

    topic_items = []
    for topic in topics[:8]:
      topic_items.append(
        {
          "type": "topic",
          "title": topic,
          "reason": cls._reason_for_topic(topic, possible_findings, body_part, clinical, comparison),
          "href": f"/learning?q={cls._url_quote(topic)}",
          "course_id": None,
          "lesson_id": None,
          "priority": 2,
          "clinical_aware": bool(clinical),
          "comparison_aware": bool(comparison),
          "source": "comparison" if comparison else "analysis",
        }
      )

    # Courses → lessons → topics (dedupe by id/title)
    for rec in course_items:
      _add(rec, f"course:{rec['course_id']}")
    for rec in lesson_items:
      _add(rec, f"lesson:{rec['lesson_id']}")
    for rec in topic_items:
      _add(rec, f"topic:{str(rec['title']).lower()}")

    recommendations.sort(
      key=lambda r: (
        r.get("priority", 99),
        0 if r.get("type") == "course" else 1 if r.get("type") == "lesson" else 2,
      )
    )
    recommendations = recommendations[:limit]

    if sync_user_recommendations and user_id:
      cls._sync_recommendation_rows(
        user_id, matched_courses, possible_findings, body_part, clinical, comparison
      )

    if comparison and clinical:
      message = (
        "Learning recommendations generated from healthy-reference comparison "
        "and supporting clinical context."
      )
    elif comparison:
      message = "Learning recommendations generated from healthy-reference comparison."
    elif clinical:
      message = "Learning recommendations generated with patient clinical context."
    else:
      message = "Learning recommendations generated."

    return RecommendationResult(
      success=True,
      recommendations=recommendations,
      topics=topics,
      clinical_context_used=bool(clinical),
      comparison_aware=bool(comparison),
      message=message,
    )

  @staticmethod
  def resolve_findings(row: Any) -> list[Any]:
    """
    Phase 13 — prefer stored possible_findings; fall back to structured_findings.findings.
    """
    findings = getattr(row, "possible_findings", None)
    if isinstance(findings, list) and findings:
      return findings
    structured = getattr(row, "structured_findings", None)
    if isinstance(structured, dict):
      nested = structured.get("findings")
      if isinstance(nested, list) and nested:
        return nested
    return findings if isinstance(findings, list) else []

  # ------------------------------------------------------------------ helpers

  @classmethod
  def _clinical_from_row(cls, row: XrayAnalysis) -> dict[str, Any] | None:
    if hasattr(row, "patient_clinical_dict"):
      return cls._normalize_clinical(row.patient_clinical_dict())
    return cls._normalize_clinical(
      {
        "patient_age": getattr(row, "patient_age", None),
        "gender": getattr(row, "gender", None),
        "body_part": getattr(row, "body_part", None),
        "symptoms": getattr(row, "symptoms", None),
        "reason_for_exam": getattr(row, "reason_for_exam", None),
        "smoking_history": getattr(row, "smoking_history", None),
      }
    )

  @classmethod
  def _normalize_clinical(cls, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw or not isinstance(raw, dict):
      return None
    cleaned: dict[str, Any] = {}
    age = raw.get("patient_age")
    if age is not None and age != "":
      try:
        cleaned["patient_age"] = int(age)
      except (TypeError, ValueError):
        pass
    for key in ("gender", "body_part", "symptoms", "reason_for_exam", "smoking_history"):
      value = raw.get(key)
      if value is None or value == "":
        continue
      text = str(value).strip()
      if text:
        cleaned[key] = text
    return cleaned or None

  @classmethod
  def _normalize_comparison(cls, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Sanitize educational comparison context used to seed learning topics."""
    if not raw or not isinstance(raw, dict):
      return None
    cleaned: dict[str, Any] = {}
    for key in ("body_part", "reference_body_part", "age_group", "gender"):
      value = raw.get(key)
      if value is None or value == "":
        continue
      text = str(value).strip()
      if text:
        cleaned[key] = text

    focus: list[str] = []
    for item in raw.get("learning_focus") or []:
      text = re.sub(r"\s+", " ", str(item or "")).strip()
      if not text or len(text) < 3:
        continue
      lower = text.lower()
      if any(bad in lower for bad in ("base64", "pixel", "file path", "upload bytes")):
        continue
      focus.append(text[:160])
    if focus:
      cleaned["learning_focus"] = focus[:8]

    summary = re.sub(r"\s+", " ", str(raw.get("comparison_summary") or "")).strip()
    if summary:
      cleaned["comparison_summary"] = summary[:280]

    return cleaned or None

  @classmethod
  def _topics_from_findings(
    cls,
    possible_findings: list[Any] | None,
    body_part: str | None,
    clinical: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
  ) -> list[str]:
    topics: list[str] = []
    seen: set[str] = set()

    def add_many(items: list[str]) -> None:
      for t in items:
        key = t.lower()
        if key in seen:
          continue
        seen.add(key)
        topics.append(t)

    for item in possible_findings or []:
      label = ""
      if isinstance(item, dict):
        label = str(item.get("label") or item.get("finding") or "")
      elif item is not None:
        label = str(item)
      label_l = label.lower()
      for key, mapped in FINDING_TOPIC_MAP.items():
        if key in label_l:
          add_many(mapped)

    part = (
      body_part
      or (clinical or {}).get("body_part")
      or (comparison or {}).get("body_part")
      or (comparison or {}).get("reference_body_part")
      or ""
    ).strip().lower()
    if part in BODY_PART_TOPICS:
      add_many(BODY_PART_TOPICS[part])
    elif part:
      add_many(["Systematic X-ray Reading", "Clinical Case Studies"])

    if clinical:
      add_many(cls._topics_from_clinical(clinical))

    if comparison:
      add_many(COMPARISON_BASE_TOPICS)
      for focus in comparison.get("learning_focus") or []:
        text = str(focus).strip()
        if not text:
          continue
        if len(text) <= 60:
          add_many([text])
        else:
          lower = text.lower()
          for known in COMPARISON_BASE_TOPICS + [
            "Lung Anatomy",
            "Bone Anatomy",
            "Heart Anatomy",
            "Pediatric Radiology",
            "Fracture Care",
          ]:
            if known.lower() in lower:
              add_many([known])

    if not topics:
      add_many(
        [
          "Chest X-ray Interpretation",
          "Systematic X-ray Reading",
          "Clinical Case Studies",
        ]
      )
    return topics

  @classmethod
  def _topics_from_clinical(cls, clinical: dict[str, Any]) -> list[str]:
    topics: list[str] = []
    age = clinical.get("patient_age")
    if isinstance(age, int):
      if age < 18:
        topics.extend(["Pediatric Radiology", "Growth and Development", "Clinical Case Studies"])
      elif age >= 65:
        topics.extend(
          ["Geriatric Assessment", "Age-Related Chest Findings", "Chest X-ray Interpretation"]
        )

    smoking = str(clinical.get("smoking_history") or "").strip().lower()
    if smoking in SMOKING_TOPICS:
      topics.extend(SMOKING_TOPICS[smoking])

    text_blob = " ".join(
      filter(
        None,
        [
          str(clinical.get("symptoms") or ""),
          str(clinical.get("reason_for_exam") or ""),
        ],
      )
    ).lower()
    for key, mapped in SYMPTOM_TOPIC_MAP.items():
      if key in text_blob:
        topics.extend(mapped)

    if clinical.get("gender"):
      topics.append("Clinical Case Studies")

    return topics

  @classmethod
  def _search_terms(
    cls,
    topics: list[str],
    possible_findings: list[Any] | None,
    body_part: str | None,
    clinical: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
  ) -> list[str]:
    terms: list[str] = []
    for t in topics:
      terms.append(t)
      for token in re.split(r"[\s,/|-]+", t):
        if len(token) >= 4:
          terms.append(token)

    for item in possible_findings or []:
      if isinstance(item, dict):
        label = str(item.get("label") or "")
        cleaned = re.sub(r"(?i)^possible\s+", "", label).strip()
        if cleaned:
          terms.append(cleaned)

    if body_part:
      terms.append(body_part)

    if clinical:
      smoking = clinical.get("smoking_history")
      if smoking:
        terms.extend(["COPD", "smoking", "respiratory"])
      for field_name in ("symptoms", "reason_for_exam"):
        value = clinical.get(field_name)
        if value:
          for token in re.split(r"[\s,/|;]+", str(value)):
            if len(token) >= 4:
              terms.append(token)

    if comparison:
      terms.extend(
        [
          "normal anatomy",
          "radiograph",
          "systematic reading",
          "healthy reference",
        ]
      )
      for key in ("body_part", "reference_body_part", "age_group"):
        value = comparison.get(key)
        if value:
          terms.append(str(value))
      for focus in comparison.get("learning_focus") or []:
        for token in re.split(r"[\s,/|;:]+", str(focus)):
          if len(token) >= 4:
            terms.append(token)

    out: list[str] = []
    seen: set[str] = set()
    for t in terms:
      k = t.lower().strip()
      if not k or k in seen:
        continue
      seen.add(k)
      out.append(t.strip())
    return out[:32]

  @classmethod
  def _match_courses(cls, search_terms: list[str], limit: int = 8) -> list[Course]:
    if not search_terms:
      return []
    query = Course.query.filter(
      or_(Course.is_published.is_(True), Course.is_published.is_(None))
    ).outerjoin(CourseCategory, Course.category_id == CourseCategory.id)

    filters = []
    for term in search_terms[:12]:
      like = f"%{term}%"
      filters.extend(
        [
          Course.title.ilike(like),
          Course.description.ilike(like),
          Course.speciality.ilike(like),
          CourseCategory.name.ilike(like),
        ]
      )
    if not filters:
      return []
    rows = (
      query.filter(or_(*filters))
      .order_by(Course.rating_avg.desc(), Course.created_at.desc())
      .limit(limit * 2)
      .all()
    )
    scored = []
    for c in rows:
      blob = " ".join(
        filter(
          None,
          [
            c.title or "",
            c.description or "",
            c.speciality or "",
            c.category.name if c.category else "",
          ],
        )
      ).lower()
      score = sum(1 for t in search_terms if t.lower() in blob)
      scored.append((score, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for s, c in scored if s > 0][:limit]

  @classmethod
  def _match_lessons(cls, search_terms: list[str], limit: int = 8) -> list[Lesson]:
    if not search_terms:
      return []
    filters = []
    for term in search_terms[:10]:
      like = f"%{term}%"
      filters.append(Lesson.title.ilike(like))
      filters.append(Lesson.summary.ilike(like))
    rows = (
      Lesson.query.filter(or_(Lesson.is_published.is_(True), Lesson.is_published.is_(None)))
      .filter(or_(*filters))
      .order_by(Lesson.order_index.asc())
      .limit(limit * 3)
      .all()
    )

    tagged: list[Lesson] = []
    term_l = [t.lower() for t in search_terms]
    for lesson in Lesson.query.limit(200).all():
      tags = lesson.topic_tags or []
      if not isinstance(tags, list):
        continue
      tag_blob = " ".join(str(t) for t in tags).lower()
      if any(t in tag_blob for t in term_l):
        tagged.append(lesson)

    merged: list[Lesson] = []
    seen: set[int] = set()
    for lesson in rows + tagged:
      if lesson.id in seen:
        continue
      seen.add(lesson.id)
      merged.append(lesson)
      if len(merged) >= limit:
        break
    return merged

  @classmethod
  def _sync_recommendation_rows(
    cls,
    user_id: int,
    courses: list[Course],
    possible_findings: list[Any] | None,
    body_part: str | None,
    clinical: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
  ) -> None:
    """Upsert lightweight Recommendation rows for the Learning dashboard."""
    labels = []
    for item in possible_findings or []:
      if isinstance(item, dict) and item.get("label"):
        labels.append(str(item["label"]))
    weak_topic = labels[0] if labels else (body_part or "X-ray interpretation")
    clinical_bits = []
    if clinical:
      if clinical.get("patient_age") is not None:
        clinical_bits.append(f"age {clinical['patient_age']}")
      if clinical.get("smoking_history"):
        clinical_bits.append(str(clinical["smoking_history"]))
    prefix = (
      "Suggested after educational healthy X-ray comparison"
      if comparison
      else "Suggested after educational X-ray analysis"
    )
    reason = (
      prefix
      + (f" ({', '.join(labels[:2])})" if labels else "")
      + (f"; clinical context: {', '.join(clinical_bits)}" if clinical_bits else "")
      + ". Not a diagnosis — for learning only."
    )

    created = 0
    for course in courses[:5]:
      existing = Recommendation.query.filter_by(
        user_id=user_id,
        course_id=course.id,
        weak_topic=weak_topic[:200],
      ).first()
      if existing:
        continue
      db.session.add(
        Recommendation(
          user_id=user_id,
          course_id=course.id,
          weak_topic=weak_topic[:200],
          reason=reason[:500],
          priority=1,
          is_read=False,
        )
      )
      created += 1
    if created:
      db.session.commit()

  @classmethod
  def _reason_for_topic(
    cls,
    topic: str,
    possible_findings: list[Any] | None,
    body_part: str | None,
    clinical: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
  ) -> str:
    labels = []
    for item in possible_findings or []:
      if isinstance(item, dict) and item.get("label"):
        labels.append(str(item["label"]))
    if comparison:
      if labels:
        base = (
          "Compared with the educational healthy reference — study focus related to "
          f"possible findings ({', '.join(labels[:2])}). Educational only."
        )
      elif body_part:
        base = (
          "Compared with the educational healthy reference — suggested topic for "
          f"{body_part} radiograph interpretation. Educational only."
        )
      else:
        base = (
          f"Compared with the educational healthy reference — suggested topic: {topic}. "
          "Educational only."
        )
    elif labels:
      base = (
        f"Suggested study topic related to possible findings "
        f"({', '.join(labels[:2])}). Educational only."
      )
    elif body_part:
      base = f"Suggested study topic for {body_part} radiograph interpretation. Educational only."
    else:
      base = f"Suggested educational topic: {topic}."

    return f"{base}{cls._clinical_reason_suffix(clinical)}"

  @classmethod
  def _reason_for_course(
    cls,
    body_part: str | None,
    clinical: dict[str, Any] | None,
    comparison: dict[str, Any] | None = None,
  ) -> str:
    if comparison:
      base = (
        "Related course after comparing with an educational healthy reference"
        f"{f' ({body_part})' if body_part else ''}."
      )
    else:
      base = (
        "Related course for educational follow-up"
        f"{f' after possible findings on {body_part}' if body_part else ''}."
      )
    return f"{base}{cls._clinical_reason_suffix(clinical)}"

  @classmethod
  def _reason_for_lesson(
    cls,
    clinical: dict[str, Any] | None,
    comparison: dict[str, Any] | None = None,
  ) -> str:
    if comparison:
      base = (
        "Matching lesson for deeper study after healthy-reference comparison. "
        "Educational only."
      )
    else:
      base = "Matching lesson topic for deeper educational study."
    return f"{base}{cls._clinical_reason_suffix(clinical)}"

  @staticmethod
  def _clinical_reason_suffix(clinical: dict[str, Any] | None) -> str:
    if not clinical:
      return ""
    bits = []
    if clinical.get("patient_age") is not None:
      bits.append(f"age {clinical['patient_age']}")
    if clinical.get("smoking_history"):
      bits.append(str(clinical["smoking_history"]))
    if clinical.get("symptoms"):
      bits.append("reported symptoms")
    if not bits:
      return " Informed by supporting clinical context (not a diagnosis)."
    return f" Informed by supporting clinical context ({', '.join(bits)}; not a diagnosis)."

  @staticmethod
  def _url_quote(value: str) -> str:
    from urllib.parse import quote_plus

    return quote_plus(value)

  @staticmethod
  def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
