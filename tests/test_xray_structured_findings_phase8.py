"""Phase 8 — structured findings schema tests."""

from __future__ import annotations

from app.services.xray.analysis import MultiModelEnsemble, StructuredFindingsBuilder
from app.services.xray.vision_model import FindingCandidate
from types import SimpleNamespace


def test_structured_schema_shape():
  primary = SimpleNamespace(
    possible_findings=[
      FindingCandidate(label="Possible Lung Opacity", probability=0.66, region="lung"),
      FindingCandidate(label="No obvious abnormality detected", probability=0.4),
    ],
    confidence=0.66,
    model_name="chest",
  )
  ensemble = MultiModelEnsemble.fuse(
    findings_result=primary,
    body_detection={"body_part": "Chest", "confidence": 0.9},
    projection_detection={"projection": "PA", "confidence": 0.7},
    image_quality={"quality_score": 80, "grade": "good", "is_poor": False},
  )
  structured = StructuredFindingsBuilder.from_ensemble(ensemble)
  payload = structured.to_dict()

  assert set(payload.keys()) >= {
    "body_part",
    "projection",
    "findings",
    "confidence",
    "abnormality_score",
    "recommendation",
  }
  assert payload["body_part"] == "Chest"
  assert payload["projection"] == "PA"
  assert isinstance(payload["findings"], list)
  assert isinstance(payload["confidence"], list)
  assert len(payload["findings"]) == len(payload["confidence"])
  assert payload["safety"]["definitive_diagnosis"] is False
  assert payload["safety"]["free_form_model_text"] is False
  for f in payload["findings"]:
    assert f.get("certainty") == "possible"
    assert "label" in f
    assert "probability" in f


def test_structured_strips_unknown_keys():
  structured = StructuredFindingsBuilder.from_legacy_findings(
    [
      {
        "label": "Possible Fracture",
        "probability": 0.5,
        "diagnosis": "YOU HAVE A FRACTURE",  # must not leak
        "raw_model_text": "free form",
      }
    ],
    body_part="Hand",
    projection="AP",
  )
  payload = structured.to_dict()
  assert "diagnosis" not in payload["findings"][0]
  assert "raw_model_text" not in payload["findings"][0]
  assert payload["findings"][0]["certainty"] == "possible"


def test_confidence_array_aligned():
  structured = StructuredFindingsBuilder.from_legacy_findings(
    [
      {"label": "A", "probability": 0.2},
      {"label": "B", "probability": 0.8},
    ],
    body_part="Knee",
  )
  assert structured.confidence == [0.2, 0.8]
