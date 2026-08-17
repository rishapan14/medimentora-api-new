"""Phase 7 — multi-model ensemble fusion tests."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.xray.analysis import MultiModelEnsemble
from app.services.xray.vision_model import FindingCandidate


def _findings_result(findings, confidence=0.6, model_name="specialist"):
  return SimpleNamespace(
    possible_findings=findings,
    confidence=confidence,
    model_name=model_name,
  )


def test_ensemble_fuses_findings_anatomy_quality():
  primary = _findings_result(
    [
      FindingCandidate(label="Possible Lung Opacity", probability=0.7, region="lung"),
      FindingCandidate(label="No obvious abnormality detected", probability=0.4),
    ],
    confidence=0.7,
    model_name="chest-specialist",
  )
  body = {
    "success": True,
    "body_part": "Chest",
    "confidence": 0.8,
    "model_name": "heuristic_body_part_v1",
    "candidates": [{"label": "Chest", "confidence": 0.8}],
    "agrees_with_declared": True,
  }
  proj = {
    "success": True,
    "projection": "PA",
    "confidence": 0.6,
    "model_name": "heuristic_projection_v1",
    "candidates": [{"label": "PA", "confidence": 0.6}],
  }
  quality = {
    "success": True,
    "quality_score": 78,
    "grade": "good",
    "is_poor": False,
    "issues": [],
    "suggestions": [],
    "version": "phase2-v1",
  }

  fused = MultiModelEnsemble.fuse(
    findings_result=primary,
    body_detection=body,
    projection_detection=proj,
    image_quality=quality,
    model_routing={"specialist_key": "chest"},
    secondary_findings=[{"label": "Possible Lung Opacity", "probability": 0.55}],
  )

  assert fused.success
  payload = fused.to_dict()
  assert payload["anatomy"]["body_part"] == "Chest"
  assert payload["anatomy"]["projection"] == "PA"
  assert payload["quality"]["grade"] == "good"
  assert len(payload["models_used"]) >= 3
  assert any(f["label"] == "Possible Lung Opacity" for f in payload["fused_findings"])
  assert 0 < payload["fused_confidence"] <= 0.9
  assert "not a diagnosis" in payload["recommendation"].lower()
  assert payload["agreement"]["findings_overlap_count"] >= 1


def test_ensemble_poor_quality_lowers_confidence_hint():
  primary = _findings_result(
    [FindingCandidate(label="Possible Fracture", probability=0.8)],
    confidence=0.8,
  )
  fused = MultiModelEnsemble.fuse(
    findings_result=primary,
    body_detection={"body_part": "Hand", "confidence": 0.7},
    projection_detection={"projection": "AP", "confidence": 0.5},
    image_quality={"quality_score": 30, "grade": "poor", "is_poor": True, "issues": [{"code": "blur"}], "suggestions": ["Retake"]},
  )
  assert fused.success
  assert fused.quality["is_poor"] is True
  assert "quality" in fused.recommendation.lower()


def test_ensemble_handles_empty_secondary():
  primary = _findings_result([])
  fused = MultiModelEnsemble.fuse(findings_result=primary)
  assert fused.success
  assert isinstance(fused.fused_findings, list)
