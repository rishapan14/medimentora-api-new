"""AI Explanation Engine for X-ray findings (Module 5 / Phase 12).

CRITICAL SAFETY RULES:
  - Never send raw X-ray images to Gemini (or any LLM).
  - Only send structured finding JSON produced by the vision model.
  - Never prescribe medication, recommend treatment, or claim a diagnosis.
  - Educational / decision-support wording only.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from flask import current_app

from app.models.xray_analysis_model import XRAY_MEDICAL_DISCLAIMER
from app.services.medical_teacher.ai_client import TeacherAIClient
from app.services.xray.safety_wording import (
  ensure_short_disclaimer,
  hedge_finding_label,
  sanitize_educational_text,
)

logger = logging.getLogger(__name__)

EXPLANATION_VERSION = "1.2.0"

SYSTEM_PROMPT = """You are MediMentora's educational radiology teaching assistant.

Your job is to explain STRUCTURED possible X-ray findings for learning and decision-support only.

HARD RULES (never violate):
1. Never claim a definitive diagnosis (never say "you have", "this is", "diagnosed with").
2. Always frame findings as possible / may be consistent with / educational observations.
3. Never prescribe medication or dosages.
4. Never recommend specific treatments, procedures, or care plans.
5. Never invent findings that are not in the input JSON.
6. Never ask for or claim to have seen the image — you only receive structured JSON.
7. Always include a clear medical disclaimer.
8. When patient_clinical is provided, treat it as supporting context only — never as a confirmed diagnosis.
9. You may briefly relate possible findings to age, symptoms, reason for exam, smoking history, or projection for educational discussion, using cautious language only.

Return ONLY valid JSON with this exact schema:
{
  "patient_friendly_explanation": "string — plain language for a learner/patient",
  "medical_explanation": "string — slightly more clinical educational wording",
  "educational_notes": ["string", "..."],
  "lifestyle_advice": ["string — general wellness only, not treatment"],
  "questions_for_healthcare_professional": ["string", "..."],
  "ai_summary": "string — 2-4 sentence overview using possible-findings language",
  "disclaimer": "string — educational / not a diagnosis disclaimer"
}
"""


@dataclass
class ExplanationResult:
  """Structured educational explanation for one X-ray analysis."""

  success: bool
  provider: str = "none"
  ai_summary: str = ""
  structured_explanation: dict[str, Any] = field(default_factory=dict)
  processing_time_ms: int = 0
  message: str = ""
  error_code: str | None = None
  used_fallback: bool = False

  def to_dict(self) -> dict:
    return {
      "success": self.success,
      "provider": self.provider,
      "ai_summary": self.ai_summary,
      "structured_explanation": self.structured_explanation,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "error_code": self.error_code,
      "used_fallback": self.used_fallback,
      "explanation_version": EXPLANATION_VERSION,
      "safety": {
        "image_sent_to_llm": False,
        "definitive_diagnosis": False,
        "prescribes_medication": False,
        "recommends_treatment": False,
      },
    }


class AIExplainerService:
  """Generate patient/medical educational explanations from vision findings only."""

  # Phrases that must never appear as definitive claims in output
  _FORBIDDEN_PATTERNS = (
    re.compile(r"\byou have\b", re.I),
    re.compile(r"\byou are diagnosed\b", re.I),
    re.compile(r"\bthis (is|confirms)\b.{0,40}\b(pneumonia|fracture|cancer|effusion)\b", re.I),
    re.compile(r"\bdefinitive diagnosis\b", re.I),
    re.compile(r"\bprescribe[sd]?\b", re.I),
    re.compile(r"\btake\s+\d+\s*mg\b", re.I),
    re.compile(r"\bstart\s+(antibiotics|steroids|chemotherapy)\b", re.I),
  )

  @classmethod
  def explain_from_findings(
    cls,
    *,
    possible_findings: list[Any] | None,
    confidence: float | None = None,
    body_part: str | None = None,
    model_name: str | None = None,
    patient_clinical: dict[str, Any] | None = None,
  ) -> ExplanationResult:
    """
    Explain structured vision findings.

    NEVER accepts or reads image bytes/paths — findings JSON only.
    Optional patient_clinical is structured text/context only (never images).
    """
    started = time.perf_counter()
    payload = cls._build_llm_payload(
      possible_findings=possible_findings,
      confidence=confidence,
      body_part=body_part,
      model_name=model_name,
      patient_clinical=patient_clinical,
    )

    # Refuse if caller accidentally passed image-like keys
    if cls._payload_looks_like_image_request(payload):
      return ExplanationResult(
        success=False,
        message="Refused: explainer accepts structured findings only (no images).",
        error_code="image_forbidden",
        processing_time_ms=int((time.perf_counter() - started) * 1000),
      )

    user_prompt = (
      "Explain these educational X-ray vision findings as JSON.\n"
      "Input (structured findings and optional patient_clinical context only — no image):\n"
      f"{cls._json_dumps(payload)}\n\n"
      "If patient_clinical is present, briefly relate possible findings to that supporting "
      "context for educational discussion only. Never treat clinical fields as a diagnosis."
    )

    data, provider = TeacherAIClient.complete_json(SYSTEM_PROMPT, user_prompt)
    if data:
      cleaned = cls._stamp_meta(
        cls._normalize_and_sanitize(data, payload),
        provider=provider or "llm",
        used_fallback=False,
      )
      elapsed = int((time.perf_counter() - started) * 1000)
      logger.info(
        "X-ray AI explanation OK provider=%s findings=%s ms=%s",
        provider,
        len(payload.get("possible_findings") or []),
        elapsed,
      )
      return ExplanationResult(
        success=True,
        provider=provider,
        ai_summary=cleaned["ai_summary"],
        structured_explanation=cleaned,
        processing_time_ms=elapsed,
        message="Educational explanation generated.",
        used_fallback=False,
      )

    # Deterministic educational fallback (works offline / without API keys)
    fallback = cls._stamp_meta(
      cls._fallback_explanation(payload),
      provider="fallback",
      used_fallback=True,
    )
    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info(
      "X-ray AI explanation fallback (no LLM) findings=%s ms=%s",
      len(payload.get("possible_findings") or []),
      elapsed,
    )
    return ExplanationResult(
      success=True,
      provider="fallback",
      ai_summary=fallback["ai_summary"],
      structured_explanation=fallback,
      processing_time_ms=elapsed,
      message="Educational explanation generated with local fallback (LLM unavailable).",
      used_fallback=True,
    )

  @classmethod
  def explain_xray_row(cls, row) -> ExplanationResult:
    """Explain an existing XrayAnalysis row using stored findings + patient clinical context."""
    clinical = cls._clinical_from_row(row)
    return cls.explain_from_findings(
      possible_findings=row.possible_findings,
      confidence=row.confidence,
      body_part=row.body_part,
      model_name=row.model_name,
      patient_clinical=clinical,
    )

  # ------------------------------------------------------------------ helpers

  @staticmethod
  def _json_dumps(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)

  @classmethod
  def _build_llm_payload(
    cls,
    *,
    possible_findings: list[Any] | None,
    confidence: float | None,
    body_part: str | None,
    model_name: str | None,
    patient_clinical: dict[str, Any] | None = None,
  ) -> dict[str, Any]:
    labels: list[dict[str, Any]] = []
    for item in possible_findings or []:
      if isinstance(item, dict):
        labels.append(
          {
            "label": item.get("label") or item.get("finding") or item.get("name"),
            "probability": item.get("probability") or item.get("score"),
            "region": item.get("region"),
            "certainty": item.get("certainty") or "possible",
          }
        )
      elif item is not None:
        labels.append({"label": str(item), "certainty": "possible"})

    payload: dict[str, Any] = {
      "possible_findings": labels,
      "confidence": None if confidence is None else round(float(confidence), 4),
      "body_part": body_part or "Unknown",
      "model_name": model_name,
      "context": "educational_decision_support_only",
    }

    clinical = cls._normalize_clinical_context(patient_clinical)
    if clinical:
      payload["patient_clinical"] = clinical

    return payload

  @classmethod
  def _clinical_from_row(cls, row) -> dict[str, Any] | None:
    """Extract safe patient clinical context from an XrayAnalysis row."""
    if hasattr(row, "patient_clinical_dict"):
      return cls._normalize_clinical_context(row.patient_clinical_dict())
    return cls._normalize_clinical_context(
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
  def _normalize_clinical_context(cls, raw: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep only whitelisted clinical fields for LLM input (text/context only)."""
    if not raw or not isinstance(raw, dict):
      return None

    allowed = (
      "patient_age",
      "gender",
      "body_part",
      "projection",
      "symptoms",
      "reason_for_exam",
      "smoking_history",
    )
    cleaned: dict[str, Any] = {}
    for key in allowed:
      value = raw.get(key)
      if value is None or value == "":
        continue
      if key == "patient_age":
        try:
          cleaned[key] = int(value)
        except (TypeError, ValueError):
          continue
      else:
        cleaned[key] = cls._as_text(value)

    if not cleaned:
      return None

    return {
      **cleaned,
      "safety": {
        "supporting_context_only": True,
        "not_a_diagnosis": True,
      },
    }

  @staticmethod
  def _payload_looks_like_image_request(payload: dict) -> bool:
    """Defense-in-depth: reject accidental image/base64 fields."""
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
    }
    return any(k in banned for k in payload.keys())

  @classmethod
  def _normalize_and_sanitize(cls, data: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """Coerce schema + scrub unsafe medical wording."""
    patient = cls._as_text(data.get("patient_friendly_explanation"))
    medical = cls._as_text(data.get("medical_explanation"))
    notes = cls._as_str_list(data.get("educational_notes"))
    lifestyle = cls._as_str_list(data.get("lifestyle_advice"))
    questions = cls._as_str_list(data.get("questions_for_healthcare_professional"))
    summary = cls._as_text(data.get("ai_summary"))
    disclaimer = cls._as_text(data.get("disclaimer")) or XRAY_MEDICAL_DISCLAIMER
    disclaimer = ensure_short_disclaimer(disclaimer)
    if "educational" not in disclaimer.lower() and "not a diagnosis" not in disclaimer.lower():
      disclaimer = XRAY_MEDICAL_DISCLAIMER
    disclaimer = ensure_short_disclaimer(disclaimer)

    patient = cls._sanitize_text(patient)
    medical = cls._sanitize_text(medical)
    summary = cls._sanitize_text(summary)
    notes = [cls._sanitize_text(n) for n in notes if n]
    lifestyle = [cls._sanitize_text(n) for n in lifestyle if n]
    questions = [cls._sanitize_text(n) for n in questions if n]

    if not summary:
      labels = [
        hedge_finding_label(str(f.get("label"))).rstrip(".")
        for f in (source.get("possible_findings") or [])
        if isinstance(f, dict) and f.get("label")
      ]
      if labels:
        summary = (
          f"Educational analysis of this {source.get('body_part') or 'X-ray'} image: "
          f"{'; '.join(labels[:4])}. "
          "These are not definitive diagnoses and require clinical interpretation."
        )
      else:
        summary = (
          "Educational analysis did not highlight a specific abnormal pattern. "
          "This is not a diagnosis and clinical review is still required when indicated."
        )

    if not patient:
      patient = summary
    if not medical:
      medical = summary
    if not notes:
      notes = [
        "Possible findings are educational observations, not confirmed diagnoses.",
        "Image quality, technique, and clinical history strongly affect interpretation.",
      ]
    if not lifestyle:
      lifestyle = [
        "Maintain general wellness habits recommended by your clinician.",
        "Seek timely professional care if symptoms worsen or new symptoms appear.",
      ]
    if not questions:
      questions = [
        "Do these possible findings match my symptoms and exam?",
        "Do I need additional imaging or clinical tests?",
        "What follow-up timeline do you recommend?",
      ]

    return {
      "patient_friendly_explanation": patient,
      "medical_explanation": medical,
      "educational_notes": notes[:8],
      "lifestyle_advice": lifestyle[:6],
      "questions_for_healthcare_professional": questions[:8],
      "ai_summary": summary,
      "disclaimer": disclaimer if "educational" in disclaimer.lower() or "not a diagnosis" in disclaimer.lower() else XRAY_MEDICAL_DISCLAIMER,
      "explanation_version": EXPLANATION_VERSION,
      "source_findings": source.get("possible_findings") or [],
      "source_confidence": source.get("confidence"),
      "source_body_part": source.get("body_part"),
      "source_patient_clinical": source.get("patient_clinical"),
      "image_sent_to_llm": False,
    }

  @staticmethod
  def _stamp_meta(
    explanation: dict[str, Any],
    *,
    provider: str,
    used_fallback: bool,
  ) -> dict[str, Any]:
    """Phase 12 — persist provider / fallback flags on stored structured JSON."""
    out = dict(explanation)
    out["provider"] = provider
    out["used_fallback"] = bool(used_fallback)
    out["explanation_version"] = EXPLANATION_VERSION
    out["image_sent_to_llm"] = False
    out.setdefault(
      "safety",
      {
        "educational_only": True,
        "not_a_diagnosis": True,
        "image_sent_to_llm": False,
      },
    )
    return out

  @classmethod
  def _fallback_explanation(cls, source: dict[str, Any]) -> dict[str, Any]:
    findings = source.get("possible_findings") or []
    labels_raw = [
      f.get("label")
      for f in findings
      if isinstance(f, dict) and f.get("label")
    ]
    labels = [hedge_finding_label(str(l)).rstrip(".") for l in labels_raw]
    body = source.get("body_part") or "Unknown"
    conf = source.get("confidence")
    conf_txt = f" Overall model confidence was approximately {conf:.0%}." if isinstance(conf, (int, float)) else ""
    clinical = source.get("patient_clinical") or {}
    clinical_note = cls._clinical_context_note(clinical)

    if labels:
      joined = "; ".join(labels[:4])
      patient = (
        f"Based on an educational computer-vision review of this {body} X-ray, "
        f"{joined}. "
        "This does not mean a diagnosis has been made."
      )
      medical = (
        f"Structured vision output for body part '{body}' listed possible observations. "
        f"{joined}. These labels are probabilistic teaching signals only and must be "
        "correlated with history, exam, and specialist review."
      )
      summary = (
        f"Educational vision analysis: {joined}.{conf_txt} This is not a diagnosis."
      )
    else:
      patient = (
        f"The educational review of this {body} X-ray did not highlight a specific "
        "abnormal pattern. Absence of flagged findings is not a medical clearance."
      )
      medical = (
        "No high-priority possible findings were returned by the vision pipeline. "
        "Clinical correlation remains essential."
      )
      summary = (
        "Educational analysis did not surface a specific abnormal pattern. "
        "This is not a diagnosis and does not replace clinician evaluation."
      )

    if clinical_note:
      patient = f"{patient} {clinical_note}"
      medical = f"{medical} {clinical_note}"
      summary = f"{summary} {clinical_note}"

    return cls._normalize_and_sanitize(
      {
        "patient_friendly_explanation": patient,
        "medical_explanation": medical,
        "educational_notes": [
          "Labels use 'Possible …' wording because AI cannot confirm disease from one image.",
          "Compare findings with clinical symptoms and prior imaging when available.",
          "Ask a qualified clinician before making any health decisions.",
        ],
        "lifestyle_advice": [
          "Follow general clinician guidance for rest, hydration, and symptom monitoring.",
          "Contact emergency services for severe breathing difficulty, chest pain, or trauma.",
        ],
        "questions_for_healthcare_professional": [
          "How should I interpret these possible findings in my clinical context?",
          "Is further imaging or lab testing warranted?",
          "When should I return for follow-up?",
        ],
        "ai_summary": summary,
        "disclaimer": XRAY_MEDICAL_DISCLAIMER,
      },
      source,
    )

  @classmethod
  def _clinical_context_note(cls, clinical: dict[str, Any]) -> str:
    """Short educational note tying fallback text to submitted clinical context."""
    if not clinical:
      return ""

    parts: list[str] = []
    age = clinical.get("patient_age")
    gender = clinical.get("gender")
    if age is not None and gender:
      parts.append(f"a {age}-year-old {gender} patient")
    elif age is not None:
      parts.append(f"a {age}-year-old patient")

    symptoms = cls._as_text(clinical.get("symptoms"))
    reason = cls._as_text(clinical.get("reason_for_exam"))
    smoking = cls._as_text(clinical.get("smoking_history"))

    detail_bits: list[str] = []
    if symptoms:
      detail_bits.append(f"reported symptoms ({symptoms})")
    if reason:
      detail_bits.append(f"reason for exam ({reason})")
    if smoking:
      detail_bits.append(f"smoking history ({smoking})")

    if not parts and not detail_bits:
      return ""

    opener = f"Supporting clinical context for {parts[0]}" if parts else "Supporting clinical context"
    if detail_bits:
      opener = f"{opener} includes {', '.join(detail_bits)}"
    return (
      f"{opener}. This context is for educational discussion only and is not a diagnosis."
    )

  @classmethod
  def _sanitize_text(cls, text: str) -> str:
    return sanitize_educational_text(text)

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
