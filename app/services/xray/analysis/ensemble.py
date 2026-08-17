"""Multi-model ensemble fusion (Phase 7).

Combines independent educational backends before LLM explanation:

  Model A — Findings (body-part specialist vision)
  Model B — Anatomy (body-part + projection detectors)
  Model C — Image quality assessment

Outputs are fused into a single structured envelope. Never returns free-form
model text as a diagnosis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class EnsembleFusionResult:
  success: bool
  fused_findings: list[dict[str, Any]] = field(default_factory=list)
  fused_confidence: float = 0.0
  abnormality_score: float = 0.0
  anatomy: dict[str, Any] = field(default_factory=dict)
  quality: dict[str, Any] = field(default_factory=dict)
  models_used: list[dict[str, Any]] = field(default_factory=list)
  agreement: dict[str, Any] = field(default_factory=dict)
  recommendation: str = ""
  processing_time_ms: int = 0
  message: str = ""
  version: str = "phase7-v1"

  def to_dict(self) -> dict[str, Any]:
    return {
      "success": self.success,
      "fused_findings": self.fused_findings,
      "fused_confidence": round(float(self.fused_confidence), 4),
      "abnormality_score": round(float(self.abnormality_score), 4),
      "anatomy": self.anatomy,
      "quality": self.quality,
      "models_used": self.models_used,
      "agreement": self.agreement,
      "recommendation": self.recommendation,
      "processing_time_ms": self.processing_time_ms,
      "message": self.message,
      "version": self.version,
      "disclaimer": (
        "Ensemble fusion combines educational model outputs only. "
        "This is not a diagnosis."
      ),
    }


class MultiModelEnsemble:
  """Fuse findings + anatomy + quality into one educational analysis envelope."""

  @classmethod
  def fuse(
    cls,
    *,
    findings_result: Any,
    body_detection: dict[str, Any] | None = None,
    projection_detection: dict[str, Any] | None = None,
    image_quality: dict[str, Any] | None = None,
    model_routing: dict[str, Any] | None = None,
    secondary_findings: list[dict[str, Any]] | None = None,
  ) -> EnsembleFusionResult:
    started = time.perf_counter()
    models_used: list[dict[str, Any]] = []

    # ---- Model A: Findings ----
    primary_findings: list[dict[str, Any]] = []
    primary_conf = 0.0
    primary_name = "findings_model"
    if findings_result is not None:
      primary_name = getattr(findings_result, "model_name", None) or primary_name
      primary_conf = float(getattr(findings_result, "confidence", 0.0) or 0.0)
      raw = getattr(findings_result, "possible_findings", None) or []
      for f in raw:
        if hasattr(f, "to_dict"):
          primary_findings.append(f.to_dict())
        elif isinstance(f, dict):
          primary_findings.append(f)
      models_used.append(
        {
          "role": "findings",
          "model_name": primary_name,
          "specialist_key": (model_routing or {}).get("specialist_key"),
          "finding_count": len(primary_findings),
          "confidence": round(primary_conf, 4),
        }
      )

    # ---- Model B: Anatomy ----
    body = body_detection if isinstance(body_detection, dict) else {}
    proj = projection_detection if isinstance(projection_detection, dict) else {}
    anatomy = {
      "body_part": body.get("body_part"),
      "body_part_confidence": body.get("confidence"),
      "projection": proj.get("projection"),
      "projection_confidence": proj.get("confidence"),
      "body_candidates": (body.get("candidates") or [])[:3],
      "projection_candidates": (proj.get("candidates") or [])[:3],
      "agrees_body_declared": body.get("agrees_with_declared"),
      "agrees_projection_declared": proj.get("agrees_with_declared"),
    }
    models_used.append(
      {
        "role": "anatomy",
        "model_name": body.get("model_name") or "heuristic_body_part_v1",
        "projection_model": proj.get("model_name") or "heuristic_projection_v1",
        "body_part": anatomy["body_part"],
        "projection": anatomy["projection"],
      }
    )

    # ---- Model C: Quality ----
    quality_src = image_quality if isinstance(image_quality, dict) else {}
    quality = {
      "quality_score": quality_src.get("quality_score"),
      "grade": quality_src.get("grade"),
      "is_poor": quality_src.get("is_poor"),
      "issue_codes": [i.get("code") for i in (quality_src.get("issues") or []) if isinstance(i, dict)],
      "suggestions": (quality_src.get("suggestions") or [])[:5],
    }
    models_used.append(
      {
        "role": "image_quality",
        "model_name": quality_src.get("version") or "phase2-quality",
        "quality_score": quality.get("quality_score"),
        "grade": quality.get("grade"),
      }
    )

    # ---- Optional secondary findings for agreement ----
    secondary = [f for f in (secondary_findings or []) if isinstance(f, dict)]
    if secondary:
      models_used.append(
        {
          "role": "findings_secondary",
          "model_name": "medimentora-generic-heuristic-v1",
          "finding_count": len(secondary),
        }
      )

    fused = cls._merge_findings(primary_findings, secondary)
    abnormality_score = cls._abnormality_score(fused)
    fused_confidence = cls._fuse_confidence(
      primary_conf=primary_conf,
      findings=fused,
      quality_score=quality.get("quality_score"),
      body_conf=anatomy.get("body_part_confidence"),
      projection_conf=anatomy.get("projection_confidence"),
    )
    agreement = cls._agreement(primary_findings, secondary, anatomy, quality)
    recommendation = cls._recommendation(fused, anatomy, quality, abnormality_score)

    return EnsembleFusionResult(
      success=True,
      fused_findings=fused,
      fused_confidence=fused_confidence,
      abnormality_score=abnormality_score,
      anatomy=anatomy,
      quality=quality,
      models_used=models_used,
      agreement=agreement,
      recommendation=recommendation,
      processing_time_ms=int((time.perf_counter() - started) * 1000),
      message="Multi-model ensemble fusion completed.",
    )

  @staticmethod
  def _merge_findings(
    primary: list[dict[str, Any]], secondary: list[dict[str, Any]]
  ) -> list[dict[str, Any]]:
    by_label: dict[str, dict[str, Any]] = {}
    for src_name, bucket in (("primary", primary), ("secondary", secondary)):
      for item in bucket:
        label = str(item.get("label") or "").strip()
        if not label:
          continue
        key = label.lower()
        prob = float(item.get("probability") or 0.0)
        if key not in by_label:
          merged = dict(item)
          merged["ensemble_sources"] = [src_name]
          merged["probability"] = round(prob, 4)
          merged["certainty"] = "possible"
          by_label[key] = merged
        else:
          existing = by_label[key]
          existing["probability"] = round(
            max(float(existing.get("probability") or 0.0), prob) * 0.35
            + ((float(existing.get("probability") or 0.0) + prob) / 2.0) * 0.65,
            4,
          )
          sources = list(existing.get("ensemble_sources") or [])
          if src_name not in sources:
            sources.append(src_name)
          existing["ensemble_sources"] = sources
          existing["ensemble_agreement"] = len(sources) > 1

    fused = list(by_label.values())
    fused.sort(key=lambda x: float(x.get("probability") or 0.0), reverse=True)
    return fused[:8]

  @staticmethod
  def _abnormality_score(findings: list[dict[str, Any]]) -> float:
    if not findings:
      return 0.0
    scores = []
    for f in findings:
      label = str(f.get("label") or "").lower()
      prob = float(f.get("probability") or 0.0)
      if "no obvious abnormality" in label:
        scores.append(max(0.0, 1.0 - prob) * 0.2)
      else:
        scores.append(prob)
    return float(min(0.95, max(scores) if scores else 0.0))

  @staticmethod
  def _fuse_confidence(
    *,
    primary_conf: float,
    findings: list[dict[str, Any]],
    quality_score: Any,
    body_conf: Any,
    projection_conf: Any,
  ) -> float:
    find_conf = primary_conf
    if findings:
      find_conf = max(find_conf, max(float(f.get("probability") or 0.0) for f in findings))

    q = None
    try:
      if quality_score is not None:
        q = float(quality_score) / 100.0
    except (TypeError, ValueError):
      q = None

    anatomy_bits = []
    for v in (body_conf, projection_conf):
      try:
        if v is not None:
          anatomy_bits.append(float(v))
      except (TypeError, ValueError):
        pass
    anatomy_conf = sum(anatomy_bits) / len(anatomy_bits) if anatomy_bits else 0.5

    # Weight findings highest; down-weight if image quality is poor
    quality_factor = 1.0
    if q is not None:
      quality_factor = 0.75 + 0.25 * max(0.0, min(1.0, q))

    fused = (0.55 * find_conf + 0.25 * anatomy_conf + 0.20 * (q if q is not None else find_conf))
    fused *= quality_factor
    return float(min(0.9, max(0.05, fused)))

  @staticmethod
  def _agreement(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    anatomy: dict[str, Any],
    quality: dict[str, Any],
  ) -> dict[str, Any]:
    primary_labels = {str(f.get("label") or "").lower() for f in primary}
    secondary_labels = {str(f.get("label") or "").lower() for f in secondary}
    overlap = primary_labels & secondary_labels
    return {
      "findings_overlap_count": len(overlap),
      "findings_overlap_labels": sorted(overlap)[:5],
      "anatomy_body_declared_match": anatomy.get("agrees_body_declared"),
      "anatomy_projection_declared_match": anatomy.get("agrees_projection_declared"),
      "quality_is_poor": bool(quality.get("is_poor")),
    }

  @staticmethod
  def _recommendation(
    findings: list[dict[str, Any]],
    anatomy: dict[str, Any],
    quality: dict[str, Any],
    abnormality_score: float,
  ) -> str:
    tips: list[str] = []
    if quality.get("is_poor"):
      tips.append(
        "Image quality is below the recommended threshold — review improvement suggestions before relying on educational AI findings."
      )
    body = anatomy.get("body_part") or "the imaged region"
    proj = anatomy.get("projection")
    view = f"{body}" + (f" {proj}" if proj and proj != "Unknown" else "")
    if abnormality_score >= 0.45:
      tips.append(
        f"Educational ensemble signals on this {view} radiograph may warrant guided study of related anatomy and differential patterns with a qualified educator."
      )
    else:
      tips.append(
        f"No strong educational abnormality signal on this {view} image — still review anatomy landmarks and compare with a healthy reference when available."
      )
    tips.append(
      "For educational purposes only. This is not a diagnosis. Please consult a qualified healthcare professional."
    )
    return " ".join(tips)
