"""Phase 8 — canonical structured findings schema.

Models must not return free-form diagnostic prose as the primary result.
All vision / ensemble outputs are normalized into this JSON contract:

{
  "body_part": "",
  "projection": "",
  "findings": [],
  "confidence": [],
  "abnormality_score": 0,
  "recommendation": ""
}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.services.xray.analysis.ensemble import EnsembleFusionResult


ALLOWED_FINDING_KEYS = frozenset(
  {
    "label",
    "probability",
    "region",
    "rationale",
    "certainty",
    "ensemble_sources",
    "ensemble_agreement",
  }
)


@dataclass
class StructuredFindings:
  """Strict educational findings payload (Phase 8)."""

  body_part: str = ""
  projection: str = ""
  findings: list[dict[str, Any]] = field(default_factory=list)
  confidence: list[float] = field(default_factory=list)
  abnormality_score: float = 0.0
  recommendation: str = ""
  version: str = "phase8-v1"

  def to_dict(self) -> dict[str, Any]:
    return {
      "body_part": self.body_part or "",
      "projection": self.projection or "",
      "findings": self.findings,
      "confidence": [round(float(c), 4) for c in self.confidence],
      "abnormality_score": round(float(self.abnormality_score), 4),
      "recommendation": self.recommendation or "",
      "version": self.version,
      "safety": {
        "definitive_diagnosis": False,
        "free_form_model_text": False,
        "note": (
          "Structured educational findings only. This is not a diagnosis. "
          "Please consult a qualified healthcare professional."
        ),
      },
    }


class StructuredFindingsBuilder:
  """Normalize ensemble / vision outputs into the Phase 8 JSON schema."""

  @classmethod
  def from_ensemble(
    cls,
    ensemble: EnsembleFusionResult | dict[str, Any] | None,
    *,
    body_part: str | None = None,
    projection: str | None = None,
  ) -> StructuredFindings:
    if isinstance(ensemble, EnsembleFusionResult):
      data = ensemble.to_dict()
    elif isinstance(ensemble, dict):
      data = ensemble
    else:
      data = {}

    anatomy = data.get("anatomy") if isinstance(data.get("anatomy"), dict) else {}
    findings_raw = data.get("fused_findings") or data.get("findings") or []
    findings = [cls._normalize_finding(f) for f in findings_raw if isinstance(f, dict)]
    findings = [f for f in findings if f.get("label")]

    confidence = []
    for f in findings:
      try:
        confidence.append(float(f.get("probability") or 0.0))
      except (TypeError, ValueError):
        confidence.append(0.0)

    body = (
      body_part
      or anatomy.get("body_part")
      or data.get("body_part")
      or ""
    )
    proj = (
      projection
      or anatomy.get("projection")
      or data.get("projection")
      or ""
    )
    if str(proj).strip().lower() == "unknown":
      # Keep explicit Unknown for schema completeness
      proj = "Unknown"

    try:
      abnormality = float(data.get("abnormality_score") or 0.0)
    except (TypeError, ValueError):
      abnormality = 0.0

    recommendation = str(data.get("recommendation") or "").strip()
    if not recommendation:
      recommendation = (
        "For educational purposes only. This is not a diagnosis. "
        "Please consult a qualified healthcare professional."
      )

    return StructuredFindings(
      body_part=str(body or ""),
      projection=str(proj or ""),
      findings=findings,
      confidence=confidence,
      abnormality_score=max(0.0, min(1.0, abnormality)),
      recommendation=recommendation,
    )

  @classmethod
  def from_legacy_findings(
    cls,
    findings: list[dict[str, Any]] | None,
    *,
    body_part: str | None = None,
    projection: str | None = None,
    abnormality_score: float = 0.0,
    recommendation: str | None = None,
  ) -> StructuredFindings:
    """Fallback builder when ensemble is unavailable."""
    fake = {
      "fused_findings": findings or [],
      "anatomy": {"body_part": body_part, "projection": projection},
      "abnormality_score": abnormality_score,
      "recommendation": recommendation or "",
    }
    return cls.from_ensemble(fake, body_part=body_part, projection=projection)

  @staticmethod
  def _normalize_finding(item: dict[str, Any]) -> dict[str, Any]:
    label = str(item.get("label") or item.get("finding") or item.get("name") or "").strip()
    try:
      probability = float(item.get("probability") or item.get("confidence") or 0.0)
    except (TypeError, ValueError):
      probability = 0.0
    probability = max(0.0, min(1.0, probability))

    out: dict[str, Any] = {
      "label": label,
      "probability": round(probability, 4),
      "region": item.get("region"),
      "rationale": item.get("rationale"),
      "certainty": "possible",  # hard safety — never "confirmed"
    }
    if item.get("ensemble_sources"):
      out["ensemble_sources"] = list(item.get("ensemble_sources") or [])
    if "ensemble_agreement" in item:
      out["ensemble_agreement"] = bool(item.get("ensemble_agreement"))

    # Drop unexpected free-form blobs
    cleaned: dict[str, Any] = {}
    for k, v in out.items():
      if k not in ALLOWED_FINDING_KEYS:
        continue
      if k in ("label", "probability", "certainty") or v is not None:
        cleaned[k] = v
    return cleaned
