"""Educational model-evaluation metrics for X-ray analysis (Phase 17).

These aggregates are **ops / monitoring proxies only**. They are not clinical
accuracy, precision, recall, or diagnostic performance. True clinical evaluation
requires labeled gold-standard datasets reviewed by qualified clinicians.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from app.models.xray_analysis_model import XrayAnalysis

EVALUATION_VERSION = "1.0.0"

SAFETY = {
  "educational_monitoring_only": True,
  "not_clinical_performance": True,
  "not_accuracy_precision_recall": True,
  "gold_standard_required_for_clinical_claims": True,
  "note": (
    "These metrics summarize model provenance, confidence distributions, finding "
    "rates, and detection agreement for educational monitoring. They must not be "
    "interpreted as clinical accuracy or diagnostic performance. True evaluation "
    "requires a labeled gold-standard validation set."
  ),
}


class XrayModelEvaluationService:
  """Aggregate educational proxy metrics from stored X-ray analyses."""

  @classmethod
  def build_report(
    cls,
    *,
    body_part: str | None = None,
    model_name: str | None = None,
    analysis_version: str | None = None,
    specialist_key: str | None = None,
    status: str | None = "completed",
    limit_rows: int = 2000,
  ) -> dict[str, Any]:
    query = XrayAnalysis.query
    st = (status or "").strip().lower()
    if st and st not in ("all", "*"):
      query = query.filter(XrayAnalysis.status == st)

    part = (body_part or "").strip()
    if part:
      query = query.filter(XrayAnalysis.body_part.ilike(part))

    model = (model_name or "").strip()
    if model:
      query = query.filter(XrayAnalysis.model_name.ilike(model))

    version = (analysis_version or "").strip()
    if version:
      query = query.filter(XrayAnalysis.analysis_version == version)

    rows = (
      query.order_by(XrayAnalysis.created_at.desc())
      .limit(max(1, min(int(limit_rows), 5000)))
      .all()
    )

    # Specialist filter applied in Python (JSON field)
    specialist = (specialist_key or "").strip().lower()
    if specialist:
      filtered = []
      for row in rows:
        routing = row.model_routing if isinstance(row.model_routing, dict) else {}
        key = str(routing.get("specialist_key") or "").strip().lower()
        if key == specialist:
          filtered.append(row)
      rows = filtered

    return cls._aggregate(rows)

  @classmethod
  def _aggregate(cls, rows: list[XrayAnalysis]) -> dict[str, Any]:
    confidences: list[float] = []
    quality_scores: list[float] = []
    poor_quality = 0
    fallback_used = 0
    routing_present = 0
    body_agree = 0
    body_disagree = 0
    proj_agree = 0
    proj_disagree = 0
    findings_overlap_vals: list[float] = []

    by_model: Counter[str] = Counter()
    by_version: Counter[str] = Counter()
    by_specialist: Counter[str] = Counter()
    by_body_part: Counter[str] = Counter()
    finding_labels: Counter[str] = Counter()
    confidence_bins = {"low_<0.4": 0, "mid_0.4_0.7": 0, "high_>0.7": 0}

    for row in rows:
      model = row.model_name or "unknown"
      version = row.analysis_version or "unknown"
      part = row.body_part or "unspecified"
      by_model[model] += 1
      by_version[version] += 1
      by_body_part[part] += 1

      if isinstance(row.confidence, (int, float)):
        c = float(row.confidence)
        confidences.append(c)
        if c < 0.4:
          confidence_bins["low_<0.4"] += 1
        elif c <= 0.7:
          confidence_bins["mid_0.4_0.7"] += 1
        else:
          confidence_bins["high_>0.7"] += 1

      quality = row.image_quality if isinstance(row.image_quality, dict) else {}
      score = quality.get("quality_score")
      if isinstance(score, (int, float)):
        quality_scores.append(float(score))
      if quality.get("is_poor"):
        poor_quality += 1

      routing = row.model_routing if isinstance(row.model_routing, dict) else {}
      if routing:
        routing_present += 1
        specialist = str(routing.get("specialist_key") or "unknown")
        by_specialist[specialist] += 1
        if routing.get("fallback_used"):
          fallback_used += 1

      body_det = row.body_detection if isinstance(row.body_detection, dict) else {}
      if "agrees_with_declared" in body_det and body_det.get("agrees_with_declared") is not None:
        if body_det.get("agrees_with_declared"):
          body_agree += 1
        else:
          body_disagree += 1

      proj_det = row.projection_detection if isinstance(row.projection_detection, dict) else {}
      if "agrees_with_declared" in proj_det and proj_det.get("agrees_with_declared") is not None:
        if proj_det.get("agrees_with_declared"):
          proj_agree += 1
        else:
          proj_disagree += 1

      ensemble = row.ensemble_result if isinstance(row.ensemble_result, dict) else {}
      agreement = ensemble.get("agreement") if isinstance(ensemble.get("agreement"), dict) else {}
      overlap = agreement.get("findings_overlap_ratio")
      if isinstance(overlap, (int, float)):
        findings_overlap_vals.append(float(overlap))
      # Also accept boolean anatomy match keys
      if agreement.get("anatomy_body_declared_match") is True:
        body_agree += 0  # already counted from body_detection when present
      elif agreement.get("anatomy_body_declared_match") is False:
        pass

      findings = row.possible_findings if isinstance(row.possible_findings, list) else []
      structured = row.structured_findings if isinstance(row.structured_findings, dict) else {}
      structured_findings = structured.get("findings") if isinstance(structured.get("findings"), list) else []
      use_findings = findings or structured_findings
      for item in use_findings:
        if isinstance(item, dict):
          label = str(item.get("label") or item.get("finding") or "").strip()
          if label:
            finding_labels[label] += 1

    n = len(rows)
    body_total = body_agree + body_disagree
    proj_total = proj_agree + proj_disagree

    return {
      "success": True,
      "evaluation_version": EVALUATION_VERSION,
      "generated_at": datetime.now(timezone.utc).isoformat(),
      "sample_size": n,
      "provenance": {
        "by_model_name": dict(by_model.most_common()),
        "by_analysis_version": dict(by_version.most_common()),
        "by_specialist_key": dict(by_specialist.most_common()),
        "routing_present": routing_present,
        "fallback_used": fallback_used,
        "fallback_rate": round(fallback_used / routing_present, 4) if routing_present else None,
      },
      "confidence": {
        "count": len(confidences),
        "mean": round(mean(confidences), 4) if confidences else None,
        "median": round(median(confidences), 4) if confidences else None,
        "bins": confidence_bins,
      },
      "coverage": {
        "by_body_part": dict(by_body_part.most_common()),
      },
      "findings": {
        "top_labels": [
          {"label": label, "count": count, "rate": round(count / n, 4) if n else 0.0}
          for label, count in finding_labels.most_common(15)
        ],
        "unique_labels": len(finding_labels),
      },
      "detection_agreement": {
        "body_part": {
          "agree": body_agree,
          "disagree": body_disagree,
          "rate": round(body_agree / body_total, 4) if body_total else None,
          "note": "Declared clinical body_part vs automatic detection (proxy only).",
        },
        "projection": {
          "agree": proj_agree,
          "disagree": proj_disagree,
          "rate": round(proj_agree / proj_total, 4) if proj_total else None,
          "note": "Declared projection vs automatic detection (proxy only).",
        },
        "ensemble_findings_overlap_mean": (
          round(mean(findings_overlap_vals), 4) if findings_overlap_vals else None
        ),
      },
      "image_quality": {
        "mean_score": round(mean(quality_scores), 2) if quality_scores else None,
        "poor_count": poor_quality,
        "poor_rate": round(poor_quality / n, 4) if n else None,
      },
      "safety": SAFETY,
      "message": (
        "Educational model-evaluation report generated from stored analyses."
        if n
        else "No analyses matched the evaluation filters."
      ),
    }
