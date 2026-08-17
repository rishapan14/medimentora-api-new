"""X-ray analysis persistence model for AI-Assisted X-Ray Analysis.

Educational / decision-support only — never stores definitive diagnoses.
Patient clinical fields are supporting context only (never sole basis for diagnosis).
"""

from __future__ import annotations

import os

from app.extensions import db
from app.utils import utc_now

# Educational safety disclaimers — always returned with analysis payloads.
# Phase 20 short form is the banner contract; long form adds clinical detail.
XRAY_SHORT_DISCLAIMER = (
  "For educational purposes only. This is not a diagnosis. "
  "Please consult a qualified healthcare professional."
)
XRAY_MEDICAL_DISCLAIMER = (
  f"{XRAY_SHORT_DISCLAIMER} "
  "This AI analysis is intended for educational and decision-support purposes only. "
  "It should not replace evaluation by a qualified radiologist or physician. "
  "Findings are possible observations only and are not definitive diagnoses. "
  "Patient clinical information is supporting context only."
)

# Lifecycle statuses
XRAY_STATUS_UPLOADED = "uploaded"
XRAY_STATUS_PREPROCESSING = "preprocessing"
XRAY_STATUS_ANALYZING = "analyzing"
XRAY_STATUS_COMPLETED = "completed"
XRAY_STATUS_FAILED = "failed"

# Patient clinical enums (Module: Patient Clinical Information)
XRAY_GENDERS = (
  "Male",
  "Female",
  "Other",
  "Prefer not to say",
)

XRAY_SMOKING_HISTORY = (
  "Never Smoked",
  "Former Smoker",
  "Current Smoker",
  "Unknown",
)

XRAY_BODY_PARTS = (
  "Chest",
  "Hand",
  "Finger",
  "Wrist",
  "Elbow",
  "Shoulder",
  "Clavicle",
  "Spine",
  "Pelvis",
  "Hip",
  "Femur",
  "Knee",
  "Leg",
  "Ankle",
  "Foot",
  "Dental",
  "Skull",
  "Other",
)

# Healthy reference library dimensions (Educational Comparison feature)
XRAY_AGE_GROUPS = (
  "Infant",
  "Child",
  "Teen",
  "Adult",
  "Older Adult",
)

XRAY_PROJECTIONS = (
  "AP",
  "PA",
  "Lateral",
  "Oblique",
  "Axial",
  "Skyline",
  "Other",
)

XRAY_ORIENTATIONS = (
  "Left",
  "Right",
  "Bilateral",
  "Unknown",
)

XRAY_REFERENCE_DIFFICULTIES = (
  "Beginner",
  "Intermediate",
  "Advanced",
)

# Body parts where gender matching is clinically more relevant for teaching refs
XRAY_GENDER_RELEVANT_BODY_PARTS = (
  "Chest",
  "Pelvis",
  "Hip",
  "Spine",
  "Skull",
)

XRAY_REFERENCE_GENDERS = (
  "Male",
  "Female",
  "Unisex",
  "Unknown",
)

# Keys reserved for clinical_extras JSON (architecture-ready)
XRAY_FUTURE_CLINICAL_EXTRA_KEYS = (
  "projection",
  "height",
  "weight",
  "pregnancy_status",
  "medical_history",
  "family_history",
  "current_medications",
  "known_allergies",
  "previous_surgeries",
  "blood_pressure",
  "diabetes",
  "heart_disease",
)


class XrayAnalysis(db.Model):
  """One uploaded X-ray image and its AI-assisted analysis record."""

  __tablename__ = "xray_analysis"

  id = db.Column(db.Integer, primary_key=True, autoincrement=True)
  user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)

  # File metadata
  filename = db.Column(db.String(255), nullable=False)  # original filename
  stored_filename = db.Column(db.String(255), nullable=True)
  file_path = db.Column(db.String(500), nullable=False)
  file_type = db.Column(db.String(20), nullable=True)  # jpg | jpeg | png | dcm
  file_size = db.Column(db.Integer, nullable=True)
  content_hash = db.Column(db.String(64), nullable=True, index=True)  # duplicate detection
  batch_id = db.Column(db.String(64), nullable=True, index=True)

  # Patient clinical information (supporting context only — not a diagnosis)
  patient_age = db.Column(db.Integer, nullable=True, index=True)  # 0–120
  gender = db.Column(db.String(40), nullable=True, index=True)
  body_part = db.Column(db.String(50), nullable=True, index=True)
  symptoms = db.Column(db.Text, nullable=True)  # max 1000 enforced in validation layer
  reason_for_exam = db.Column(db.Text, nullable=True)  # max 1000 enforced in validation layer
  smoking_history = db.Column(db.String(40), nullable=True, index=True)
  # Future-safe bag for Height, Weight, Pregnancy Status, etc. without schema churn
  clinical_extras = db.Column(db.JSON, nullable=True)

  # Preprocessing / visualization artifacts
  preprocessed_path = db.Column(db.String(500), nullable=True)
  heatmap_path = db.Column(db.String(500), nullable=True)
  # Phase 11 — Grad-CAM / attention map metadata (method, regions, version)
  heatmap_meta = db.Column(db.JSON, nullable=True)
  # Phase 2 — image quality assessment JSON (score, issues, suggestions)
  image_quality = db.Column(db.JSON, nullable=True)
  # Phase 3 — preprocessing step metadata (sizes, rotation, normalization)
  preprocess_meta = db.Column(db.JSON, nullable=True)
  # Phase 4 — automatic body-part detection + confidence
  body_detection = db.Column(db.JSON, nullable=True)
  # Phase 5 — automatic projection detection + confidence
  projection_detection = db.Column(db.JSON, nullable=True)
  # Phase 6 — smart model router decision
  model_routing = db.Column(db.JSON, nullable=True)
  # Phase 7 — multi-model ensemble fusion envelope
  ensemble_result = db.Column(db.JSON, nullable=True)
  # Phase 8 — canonical structured findings schema
  structured_findings = db.Column(db.JSON, nullable=True)

  # Educational healthy X-ray comparison (supporting context only — never a diagnosis)
  reference_image_path = db.Column(db.String(500), nullable=True)
  comparison_summary = db.Column(db.Text, nullable=True)
  comparison_generated_at = db.Column(db.DateTime, nullable=True)

  # Analysis results (educational — never definitive diagnoses)
  possible_findings = db.Column(db.JSON, nullable=True)
  confidence = db.Column(db.Float, nullable=True)  # overall 0.0–1.0
  ai_summary = db.Column(db.Text, nullable=True)
  structured_explanation = db.Column(db.JSON, nullable=True)
  learning_recommendations = db.Column(db.JSON, nullable=True)
  disclaimer = db.Column(db.Text, nullable=True, default=XRAY_MEDICAL_DISCLAIMER)

  # Model provenance
  model_name = db.Column(db.String(100), nullable=True)
  analysis_version = db.Column(db.String(40), nullable=True)

  # Lifecycle
  status = db.Column(db.String(30), default=XRAY_STATUS_UPLOADED, index=True)
  processing_time = db.Column(db.Integer, nullable=True)  # milliseconds
  error_message = db.Column(db.Text, nullable=True)

  upload_date = db.Column(db.DateTime, default=utc_now, index=True)
  analysis_date = db.Column(db.DateTime, nullable=True)
  created_at = db.Column(db.DateTime, default=utc_now)
  updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now)

  user = db.relationship("User", back_populates="xray_analyses")

  def patient_clinical_dict(self) -> dict:
    """Structured patient clinical context for APIs / AI (supporting only)."""
    extras = self.clinical_extras if isinstance(self.clinical_extras, dict) else {}
    projection = extras.get("projection")
    return {
      "patient_age": self.patient_age,
      "gender": self.gender,
      "body_part": self.body_part,
      "projection": projection,
      "symptoms": self.symptoms,
      "reason_for_exam": self.reason_for_exam,
      "smoking_history": self.smoking_history,
      "clinical_extras": extras or {},
      "safety": {
        "supporting_context_only": True,
        "not_a_diagnosis": True,
        "note": (
          "Patient clinical information is supporting context only and must not be "
          "treated as a confirmed diagnosis."
        ),
      },
    }

  def _hub_recommendations_payload(self) -> list:
    """Phase 11 — Body Systems Hub study links for this X-ray (if any)."""
    try:
      from app.models.body_system_model import HubRecommendation

      rows = (
        HubRecommendation.query.filter_by(source_type="xray", source_id=self.id)
        .order_by(HubRecommendation.priority.desc(), HubRecommendation.created_at.desc())
        .limit(12)
        .all()
      )
      return [r.to_dict() for r in rows]
    except Exception:
      return []

  def to_dict(self, include_explanation: bool = False) -> dict:
    """Serialize for API responses."""
    payload = {
      "id": self.id,
      "user_id": self.user_id,
      "filename": self.filename,
      "stored_filename": self.stored_filename or os.path.basename(self.file_path or ""),
      "file_path": self.file_path,
      "file_type": self.file_type,
      "file_size": self.file_size,
      "content_hash": self.content_hash,
      "batch_id": self.batch_id,
      # Patient clinical information
      "patient_age": self.patient_age,
      "gender": self.gender,
      "body_part": self.body_part,
      "symptoms": self.symptoms,
      "reason_for_exam": self.reason_for_exam,
      "smoking_history": self.smoking_history,
      "clinical_extras": self.clinical_extras or {},
      "patient_clinical": self.patient_clinical_dict(),
      "preprocessed_path": self.preprocessed_path,
      "heatmap_path": self.heatmap_path,
      "heatmap_meta": getattr(self, "heatmap_meta", None),
      "image_quality": getattr(self, "image_quality", None),
      "preprocess_meta": getattr(self, "preprocess_meta", None),
      "body_detection": getattr(self, "body_detection", None),
      "projection_detection": getattr(self, "projection_detection", None),
      "model_routing": getattr(self, "model_routing", None),
      "ensemble_result": getattr(self, "ensemble_result", None),
      "structured_findings": getattr(self, "structured_findings", None),
      # Educational healthy reference comparison
      "reference_image_path": getattr(self, "reference_image_path", None),
      "comparison_summary": getattr(self, "comparison_summary", None),
      "comparison_generated_at": (
        getattr(self, "comparison_generated_at", None).isoformat()
        if getattr(self, "comparison_generated_at", None)
        else None
      ),
      "has_comparison": bool(
        getattr(self, "reference_image_path", None) or getattr(self, "comparison_summary", None)
      ),
      "possible_findings": self.possible_findings or [],
      "confidence": self.confidence,
      "ai_summary": self.ai_summary,
      "learning_recommendations": self.learning_recommendations or [],
      "hub_recommendations": self._hub_recommendations_payload(),
      "disclaimer": self.disclaimer or XRAY_MEDICAL_DISCLAIMER,
      "model_name": self.model_name,
      "analysis_version": self.analysis_version,
      "status": self.status,
      "processing_time": self.processing_time,
      "error_message": self.error_message,
      "upload_date": self.upload_date.isoformat() if self.upload_date else None,
      "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
      "updated_at": self.updated_at.isoformat() if self.updated_at else None,
    }
    if include_explanation:
      payload["structured_explanation"] = self.structured_explanation
    return payload

  def to_history_card(self) -> dict:
    """Compact payload for X-ray history list (includes patient summary fields)."""
    findings = self.possible_findings or []
    top_finding = None
    if isinstance(findings, list) and findings:
      first = findings[0]
      if isinstance(first, dict):
        top_finding = first.get("label") or first.get("finding") or first.get("name")
      else:
        top_finding = str(first)

    patient_bits = []
    if self.body_part:
      patient_bits.append(self.body_part)
    extras = self.clinical_extras if isinstance(self.clinical_extras, dict) else {}
    projection = extras.get("projection")
    if projection:
      patient_bits.append(str(projection))
    if self.patient_age is not None:
      patient_bits.append(f"{self.patient_age}y")
    if self.gender:
      patient_bits.append(self.gender)
    if self.smoking_history:
      patient_bits.append(self.smoking_history)

    return {
      "id": self.id,
      "filename": self.filename,
      "file_type": self.file_type,
      "file_size": self.file_size,
      "patient_age": self.patient_age,
      "gender": self.gender,
      "body_part": self.body_part,
      "projection": projection,
      "smoking_history": self.smoking_history,
      "patient_summary": " · ".join(patient_bits) if patient_bits else None,
      "batch_id": self.batch_id,
      "thumbnail_path": self.file_path,
      "heatmap_path": self.heatmap_path,
      "has_heatmap": bool(self.heatmap_path),
      "reference_image_path": getattr(self, "reference_image_path", None),
      "has_comparison": bool(
        getattr(self, "reference_image_path", None) or getattr(self, "comparison_summary", None)
      ),
      "comparison_summary": (
        (getattr(self, "comparison_summary", None)[:220] + "…")
        if getattr(self, "comparison_summary", None)
        and len(getattr(self, "comparison_summary", None) or "") > 220
        else getattr(self, "comparison_summary", None)
      ),
      "comparison_generated_at": (
        getattr(self, "comparison_generated_at", None).isoformat()
        if getattr(self, "comparison_generated_at", None)
        else None
      ),
      "confidence": self.confidence,
      "top_finding": top_finding,
      "model_name": self.model_name,
      "status": self.status,
      "image_quality_score": (
        (self.image_quality or {}).get("quality_score")
        if isinstance(getattr(self, "image_quality", None), dict)
        else None
      ),
      "image_quality_grade": (
        (self.image_quality or {}).get("grade")
        if isinstance(getattr(self, "image_quality", None), dict)
        else None
      ),
      "image_quality_is_poor": (
        bool((self.image_quality or {}).get("is_poor"))
        if isinstance(getattr(self, "image_quality", None), dict)
        else None
      ),
      "processing_time": self.processing_time,
      "upload_date": self.upload_date.isoformat() if self.upload_date else None,
      "analysis_date": self.analysis_date.isoformat() if self.analysis_date else None,
      "created_at": self.created_at.isoformat() if self.created_at else None,
    }
