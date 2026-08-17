"""Educational healthy X-ray comparison engine (Comparison Module 3).

CRITICAL SAFETY RULES:
  - Never send raw X-ray images (patient or reference) to Gemini.
  - Only structured JSON: findings, clinical context, reference metadata.
  - Never claim a confirmed diagnosis.
  - Use educational comparison wording only.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from app.extensions import db
from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER, XrayAnalysis
from app.services.medical_teacher.ai_client import TeacherAIClient
from app.services.xray.reference_library import ReferenceLibraryService, ReferenceSelectionResult
from app.utils import utc_now

logger = logging.getLogger(__name__)

COMPARISON_VERSION = "1.0.0"

SYSTEM_PROMPT = """You are MediMentora's educational radiology teaching assistant.

Your job is to write an EDUCATIONAL COMPARISON between:
1) structured possible findings from an uploaded X-ray analysis, and
2) metadata describing a selected healthy educational reference image.

HARD RULES (never violate):
1. Never claim a definitive diagnosis (never say "you have", "this is", "diagnosed with").
2. Always use wording like:
   - "Compared with the educational reference image..."
   - "The uploaded image appears different in..."
   - "These findings may warrant professional evaluation."
3. Never prescribe medication or recommend specific treatments.
4. Never invent findings that are not in the input JSON.
5. Never claim you saw either image — you only receive structured JSON.
6. Treat patient_clinical and reference metadata as supporting context only.
7. Always include a clear medical disclaimer.

Return ONLY valid JSON with this exact schema:
{
  "comparison_summary": "string — 3-6 sentences using educational comparison language",
  "key_visual_differences": ["string", "..."],
  "normal_anatomical_landmarks": ["string", "..."],
  "possible_findings_discussion": "string — discuss possible findings vs healthy reference educationally",
  "learning_focus": ["string — study topics", "..."],
  "questions_for_healthcare_professional": ["string", "..."],
  "disclaimer": "string — educational / not a diagnosis disclaimer"
}
"""


@dataclass
class ComparisonResult:
  success: bool
  provider: str = "none"
  comparison_summary: str = ""
  structured_comparison: dict[str, Any] = field(default_factory=dict)
  reference: dict[str, Any] | None = None
  learning_recommendations: list[dict[str, Any]] = field(default_factory=list)
  processing_time_ms: int = 0
  message: str = ""
  error_code: str | None = None
  used_fallback: bool = False

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "provider": self.provider,
      "comparison_summary": self.comparison_summary,
      "structured_comparison": self.structured_comparison,
      "reference": self.reference,
      "learning_recommendations": self.learning_recommendations,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "error_code": self.error_code,
      "used_fallback": self.used_fallback,
      "comparison_version": COMPARISON_VERSION,
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      "safety": {
        "image_sent_to_llm": False,
        "definitive_diagnosis": False,
        "educational_comparison_only": True,
        "healthy_reference_supporting_context_only": True,
      },
    }


class XrayComparisonService:
  """Select healthy reference + generate educational comparison (no images to LLM)."""

  _FORBIDDEN_PATTERNS = (
    re.compile(r"\byou have\b", re.I),
    re.compile(r"\byou are diagnosed\b", re.I),
    re.compile(r"\bthis (is|confirms)\b.{0,40}\b(pneumonia|fracture|cancer|effusion)\b", re.I),
    re.compile(r"\bdefinitive diagnosis\b", re.I),
    re.compile(r"\bprescribe[sd]?\b", re.I),
    re.compile(r"\btake\s+\d+\s*mg\b", re.I),
  )

  @classmethod
  def compare_for_user(
    cls,
    xray_id: int,
    user_id: int,
    *,
    persist: bool = True,
    force_reselect: bool = False,
  ) -> tuple[XrayAnalysis | None, ComparisonResult]:
    started = time.perf_counter()
    row = XrayAnalysis.query.filter_by(id=xray_id, user_id=user_id).first()
    if not row:
      return None, ComparisonResult(
        success=False,
        message="X-ray analysis not found.",
        error_code="not_found",
        processing_time_ms=cls._ms(started),
      )

    # Select / reuse reference
    selection: ReferenceSelectionResult
    if row.reference_image_path and not force_reselect:
      # Rebuild selection metadata from stored path when possible
      selection = ReferenceLibraryService.select_for_xray_row(row)
      # Prefer keeping the already-stored path if it still resolves
      resolved = ReferenceLibraryService.resolve_file(row.reference_image_path)
      if resolved and selection.primary:
        selection.primary.absolute_path = resolved
        selection.primary.relative_path = row.reference_image_path.replace("\\", "/")
    else:
      selection = ReferenceLibraryService.select_for_xray_row(row)

    if not selection.success or not selection.primary:
      # Soft empty — never crash; analysis remains viewable without a healthy reference
      logger.info(
        "Healthy reference unavailable for comparison id=%s code=%s",
        xray_id,
        selection.error_code,
      )
      from app.services.xray.reference_library import EMPTY_LIBRARY_MESSAGE

      empty_message = selection.message or EMPTY_LIBRARY_MESSAGE
      structured = {
        "comparison_summary": empty_message,
        "key_visual_differences": [],
        "normal_anatomical_landmarks": [],
        "possible_findings_discussion": (
          "A healthy reference radiograph is not available for side-by-side comparison yet. "
          "Review the AI educational findings on the result page. "
          "These findings may warrant professional evaluation."
        ),
        "learning_focus": [
          "Systematic X-ray Reading",
          "Normal Radiograph Anatomy",
          f"{row.body_part or 'X-ray'} Interpretation",
        ],
        "questions_for_healthcare_professional": [
          "How should I interpret this study without a healthy teaching reference?",
          "Do these possible findings require additional imaging or specialist review?",
        ],
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
        "library_empty": True,
        "image_sent_to_llm": False,
      }
      result = ComparisonResult(
        success=True,
        provider="library_empty",
        comparison_summary=empty_message,
        structured_comparison=structured,
        reference=None,
        learning_recommendations=row.learning_recommendations or [],
        message=empty_message,
        error_code="empty_library",
        used_fallback=True,
        processing_time_ms=cls._ms(started),
      )
      if persist:
        explanation = (
          dict(row.structured_explanation)
          if isinstance(row.structured_explanation, dict)
          else {}
        )
        explanation["educational_comparison"] = structured
        explanation["comparison_reference"] = None
        explanation["library_empty"] = True
        row.structured_explanation = explanation
        row.reference_image_path = None
        row.comparison_summary = empty_message
        row.comparison_generated_at = utc_now()
        row.disclaimer = XRAY_MEDICAL_DISCLAIMER
        row.updated_at = utc_now()
        db.session.commit()
        logger.info(
          "X-ray comparison soft-empty persisted id=%s (no healthy reference)",
          xray_id,
        )
      return row, result

    payload = cls._build_llm_payload(row, selection)
    if cls._payload_looks_like_image_request(payload):
      return row, ComparisonResult(
        success=False,
        message="Refused: comparison accepts structured context only (no images).",
        error_code="image_forbidden",
        processing_time_ms=cls._ms(started),
      )

    user_prompt = (
      "Create an educational comparison as JSON.\n"
      "Input (structured findings + healthy reference metadata only — no images):\n"
      f"{cls._json_dumps(payload)}\n\n"
      "Remember: Compared with the educational reference image… "
      "These findings may warrant professional evaluation. Never diagnose."
    )

    data, provider = TeacherAIClient.complete_json(SYSTEM_PROMPT, user_prompt)
    if data:
      structured = cls._normalize_and_sanitize(data, payload)
      used_fallback = False
      message = "Educational comparison generated."
    else:
      structured = cls._fallback_comparison(payload)
      provider = "fallback"
      used_fallback = True
      message = "Educational comparison generated with local fallback (LLM unavailable)."

    # Learning recommendations — regenerate with comparison context and persist
    learning: list[dict[str, Any]] = []
    try:
      from app.services.xray.recommendation_service import XrayRecommendationService

      primary = selection.primary
      comparison_context = {
        "body_part": row.body_part or selection.matched_body_part,
        "reference_body_part": primary.body_part if primary else None,
        "age_group": primary.age_group if primary else selection.matched_age_group,
        "gender": primary.gender if primary else None,
        "learning_focus": structured.get("learning_focus") or [],
        "comparison_summary": structured.get("comparison_summary") or "",
      }
      rec = XrayRecommendationService.build_recommendations(
        possible_findings=row.possible_findings,
        body_part=row.body_part,
        patient_clinical=row.patient_clinical_dict(),
        comparison_context=comparison_context,
        user_id=user_id,
        sync_user_recommendations=True,
      )
      if rec.success:
        learning = rec.recommendations
    except Exception:
      logger.exception("Comparison learning recommendations failed id=%s", xray_id)
      learning = row.learning_recommendations or []

    summary = structured.get("comparison_summary") or ""
    result = ComparisonResult(
      success=True,
      provider=provider,
      comparison_summary=summary,
      structured_comparison=structured,
      reference=selection.primary.to_dict(),
      learning_recommendations=learning,
      processing_time_ms=cls._ms(started),
      message=message,
      used_fallback=used_fallback,
    )

    if persist:
      row.reference_image_path = selection.primary.relative_path or selection.primary.absolute_path
      row.comparison_summary = summary
      row.comparison_generated_at = utc_now()
      if learning:
        row.learning_recommendations = learning
      # Attach structured comparison into explanation payload without schema churn
      explanation = (
        dict(row.structured_explanation)
        if isinstance(row.structured_explanation, dict)
        else {}
      )
      explanation["educational_comparison"] = structured
      explanation["comparison_reference"] = {
        "id": selection.primary.id,
        "relative_path": selection.primary.relative_path,
        "body_part": selection.primary.body_part,
        "projection": selection.primary.projection,
        "age_group": selection.primary.age_group,
        "gender": selection.primary.gender,
        "gender_relevant": selection.primary.gender_relevant,
      }
      row.structured_explanation = explanation
      row.disclaimer = XRAY_MEDICAL_DISCLAIMER
      row.updated_at = utc_now()
      db.session.commit()
      logger.info(
        "X-ray educational comparison OK id=%s ref=%s provider=%s ms=%s",
        xray_id,
        selection.primary.id,
        provider,
        result.processing_time_ms,
      )

    return row, result

  @classmethod
  def get_stored_comparison(cls, row: XrayAnalysis) -> ComparisonResult | None:
    if not (row.reference_image_path or row.comparison_summary):
      return None
    explanation = row.structured_explanation if isinstance(row.structured_explanation, dict) else {}
    structured = explanation.get("educational_comparison") or {
      "comparison_summary": row.comparison_summary or "",
      "key_visual_differences": [],
      "normal_anatomical_landmarks": [],
      "possible_findings_discussion": row.comparison_summary or "",
      "learning_focus": [],
      "questions_for_healthcare_professional": [],
      "disclaimer": XRAY_MEDICAL_DISCLAIMER,
    }
    ref_meta = explanation.get("comparison_reference") or {}
    if not isinstance(structured, dict):
      structured = {
        "comparison_summary": row.comparison_summary or "",
        "key_visual_differences": [],
        "normal_anatomical_landmarks": [],
        "possible_findings_discussion": row.comparison_summary or "",
        "learning_focus": [],
        "questions_for_healthcare_professional": [],
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      }
    if not isinstance(ref_meta, dict):
      ref_meta = {}
    reference = None
    if row.reference_image_path:
      # Enrich from library when possible
      for item in ReferenceLibraryService.list_references():
        if item.relative_path.replace("\\", "/") == str(row.reference_image_path).replace("\\", "/"):
          reference = item.to_dict()
          break
      if reference is None:
        reference = {
          "id": ref_meta.get("id") or "stored",
          "relative_path": row.reference_image_path,
          "body_part": ref_meta.get("body_part") or row.body_part,
          "age_group": ref_meta.get("age_group"),
          "gender": ref_meta.get("gender"),
          "label": "Stored educational healthy reference",
          "exists": bool(ReferenceLibraryService.resolve_file(row.reference_image_path)),
        }

    library_empty = bool(
      structured.get("library_empty") or explanation.get("library_empty")
    )
    if library_empty and not structured.get("library_empty"):
      structured = dict(structured)
      structured["library_empty"] = True

    return ComparisonResult(
      success=True,
      provider="library_empty" if library_empty else "stored",
      comparison_summary=row.comparison_summary or structured.get("comparison_summary") or "",
      structured_comparison=structured,
      reference=None if library_empty else reference,
      learning_recommendations=row.learning_recommendations or [],
      message=(
        structured.get("comparison_summary")
        if library_empty
        else "Stored educational comparison retrieved."
      ),
      error_code="empty_library" if library_empty else None,
      used_fallback=library_empty,
    )

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)

  @classmethod
  def _build_llm_payload(cls, row: XrayAnalysis, selection: ReferenceSelectionResult) -> dict[str, Any]:
    findings = []
    for item in row.possible_findings or []:
      if isinstance(item, dict):
        findings.append(
          {
            "label": item.get("label") or item.get("finding"),
            "probability": item.get("probability"),
            "region": item.get("region"),
            "certainty": item.get("certainty") or "possible",
          }
        )
      elif item is not None:
        findings.append({"label": str(item), "certainty": "possible"})

    primary = selection.primary
    extras = getattr(row, "clinical_extras", None)
    if not isinstance(extras, dict):
      extras = {}
    patient_projection = ReferenceLibraryService.detect_projection(
      explicit=extras.get("projection"),
      clinical_extras=extras,
      reason_for_exam=getattr(row, "reason_for_exam", None),
      symptoms=getattr(row, "symptoms", None),
      filename=getattr(row, "filename", None),
    )
    return {
      "context": "educational_healthy_reference_comparison_only",
      "possible_findings": findings,
      "confidence": None if row.confidence is None else round(float(row.confidence), 4),
      "body_part": row.body_part or selection.matched_body_part,
      "projection": patient_projection or selection.matched_projection,
      "patient_clinical": {
        "patient_age": row.patient_age,
        "gender": row.gender,
        "body_part": row.body_part,
        "projection": patient_projection,
        "symptoms": row.symptoms or "",
        "reason_for_exam": row.reason_for_exam or "",
        "smoking_history": row.smoking_history or "",
        "safety": {"supporting_context_only": True, "not_a_diagnosis": True},
      },
      "healthy_reference": {
        "id": primary.id if primary else None,
        "body_part": primary.body_part if primary else None,
        "projection": primary.projection if primary else None,
        "age_group": primary.age_group if primary else None,
        "gender": primary.gender if primary else None,
        "gender_relevant": primary.gender_relevant if primary else False,
        "label": primary.label if primary else None,
        "notes": primary.notes if primary else None,
        "license": primary.license if primary else None,
        "source": primary.source if primary else None,
        # Never include file bytes / absolute paths for LLM
        "relative_path": primary.relative_path if primary else None,
      },
      "matched_age_group": selection.matched_age_group,
      "matched_projection": selection.matched_projection,
      "gender_used_in_match": selection.gender_used,
    }

  @staticmethod
  def _payload_looks_like_image_request(payload: dict) -> bool:
    banned = {
      "image",
      "image_b64",
      "image_base64",
      "base64",
      "file_path",
      "preprocessed_path",
      "heatmap_path",
      "bytes",
      "pixels",
      "absolute_path",
    }
    return any(k in banned for k in payload.keys())

  @classmethod
  def _normalize_and_sanitize(cls, data: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    summary = cls._sanitize_text(cls._as_text(data.get("comparison_summary")))
    differences = [cls._sanitize_text(x) for x in cls._as_str_list(data.get("key_visual_differences")) if x]
    landmarks = [cls._sanitize_text(x) for x in cls._as_str_list(data.get("normal_anatomical_landmarks")) if x]
    discussion = cls._sanitize_text(cls._as_text(data.get("possible_findings_discussion")))
    learning_focus = [cls._sanitize_text(x) for x in cls._as_str_list(data.get("learning_focus")) if x]
    questions = [
      cls._sanitize_text(x)
      for x in cls._as_str_list(data.get("questions_for_healthcare_professional"))
      if x
    ]
    disclaimer = cls._as_text(data.get("disclaimer")) or XRAY_MEDICAL_DISCLAIMER

    body = source.get("body_part") or "X-ray"
    ref = source.get("healthy_reference") or {}
    labels = [
      f.get("label")
      for f in (source.get("possible_findings") or [])
      if isinstance(f, dict) and f.get("label")
    ]

    if not summary:
      summary = cls._default_summary(body, ref, labels)
    if not differences:
      differences = [
        (
          f"Compared with the educational reference image, the uploaded {body} study "
          "may show differences in soft-tissue or bony contour that require clinician review."
        ),
        "Any asymmetry or unexpected opacity relative to a healthy teaching example is educational only.",
      ]
    if not landmarks:
      landmarks = [
        f"Typical {body} educational landmarks for orientation (side markers, expected contours).",
        "Healthy reference anatomy is used for teaching comparison, not as a diagnostic standard.",
      ]
    if not discussion:
      if labels:
        discussion = (
          f"Possible findings from the vision model ({', '.join(labels[:3])}) are discussed "
          "relative to the educational healthy reference. These may warrant professional evaluation."
        )
      else:
        discussion = (
          "No high-priority possible findings were listed. Absence of flagged findings is not "
          "medical clearance and may still warrant professional evaluation when clinically indicated."
        )
    if not learning_focus:
      learning_focus = [
        f"{body} X-ray Interpretation",
        "Systematic X-ray Reading",
        "Normal Radiograph Anatomy",
      ]
    if not questions:
      questions = [
        "How should I interpret differences from the educational healthy reference in my clinical context?",
        "Do these possible findings require additional imaging or specialist review?",
        "What follow-up timeline do you recommend?",
      ]

    if "not a diagnosis" not in disclaimer.lower() and "educational" not in disclaimer.lower():
      disclaimer = XRAY_MEDICAL_DISCLAIMER

    return {
      "comparison_summary": summary,
      "key_visual_differences": differences[:8],
      "normal_anatomical_landmarks": landmarks[:8],
      "possible_findings_discussion": discussion,
      "learning_focus": learning_focus[:8],
      "questions_for_healthcare_professional": questions[:8],
      "disclaimer": disclaimer,
      "comparison_version": COMPARISON_VERSION,
      "image_sent_to_llm": False,
      "source_findings": source.get("possible_findings") or [],
      "source_reference": source.get("healthy_reference") or {},
    }

  @classmethod
  def _fallback_comparison(cls, source: dict[str, Any]) -> dict[str, Any]:
    body = source.get("body_part") or "X-ray"
    ref = source.get("healthy_reference") or {}
    labels = [
      f.get("label")
      for f in (source.get("possible_findings") or [])
      if isinstance(f, dict) and f.get("label")
    ]
    summary = cls._default_summary(body, ref, labels)
    return cls._normalize_and_sanitize(
      {
        "comparison_summary": summary,
        "key_visual_differences": [
          (
            f"Compared with the educational reference image ({ref.get('age_group')}, "
            f"{ref.get('gender')}), the uploaded study may appear different in overall "
            "density pattern or contour."
          ),
          "The uploaded image appears different in regions highlighted by possible findings, if any.",
        ],
        "normal_anatomical_landmarks": [
          f"Educational healthy {body} landmarks for orientation and side comparison.",
          "Reference anatomy supports learning and is not a patient-matched diagnostic standard.",
        ],
        "possible_findings_discussion": (
          f"Possible findings ({', '.join(labels[:3])}) are teaching signals only. "
          "These findings may warrant professional evaluation."
          if labels
          else (
            "No structured possible findings were listed. This is not a clearance and may still "
            "warrant professional evaluation."
          )
        ),
        "learning_focus": [
          f"{body} X-ray Interpretation",
          "Normal Radiograph Anatomy",
          "Systematic X-ray Reading",
        ],
        "questions_for_healthcare_professional": [
          "How should differences from the educational healthy reference be interpreted clinically?",
          "Is further imaging warranted?",
        ],
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
      source,
    )

  @staticmethod
  def _default_summary(body: str, ref: dict[str, Any], labels: list[str]) -> str:
    ref_bits = ", ".join(
      filter(None, [ref.get("body_part"), ref.get("age_group"), ref.get("gender")])
    )
    finding_txt = (
      f" Possible findings discussed educationally include: {', '.join(labels[:3])}."
      if labels
      else ""
    )
    return (
      f"Compared with the educational reference image ({ref_bits or 'healthy teaching example'}), "
      f"the uploaded {body} radiograph is reviewed for learning purposes only.{finding_txt} "
      "The uploaded image appears different in ways that may warrant professional evaluation. "
      "This comparison is not a diagnosis."
    )

  @classmethod
  def _sanitize_text(cls, text: str) -> str:
    if not text:
      return ""
    out = text.strip()
    for pat in cls._FORBIDDEN_PATTERNS:
      if pat.search(out):
        out = pat.sub("may be consistent with findings that require clinical review", out)
    out = re.sub(r"\bYou have\b", "Possible findings may relate to", out, flags=re.I)
    out = re.sub(r"\bdiagnosed with\b", "evaluated for possible", out, flags=re.I)
    return out

  @staticmethod
  def _as_text(value: Any) -> str:
    if value is None:
      return ""
    if isinstance(value, list):
      return " ".join(str(v).strip() for v in value if v).strip()
    return str(value).strip()

  @staticmethod
  def _as_str_list(value: Any) -> list[str]:
    if value is None:
      return []
    if isinstance(value, str):
      return [value.strip()] if value.strip() else []
    if isinstance(value, list):
      return [str(v).strip() for v in value if str(v).strip()]
    return [str(value).strip()]

  @staticmethod
  def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
