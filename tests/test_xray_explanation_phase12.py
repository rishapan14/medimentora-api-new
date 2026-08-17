"""Phase 12 — LLM educational explanation tests."""

from __future__ import annotations

from app.services.xray.ai_explainer import AIExplainerService, EXPLANATION_VERSION


def test_explanation_persists_provider_and_fallback_meta(app_ctx):
  result = AIExplainerService.explain_from_findings(
    possible_findings=[
      {"label": "Possible Lung Opacity", "probability": 0.72, "certainty": "possible"}
    ],
    confidence=0.72,
    body_part="Chest",
    model_name="test-model",
  )
  assert result.success
  structured = result.structured_explanation
  assert structured.get("image_sent_to_llm") is False
  assert "provider" in structured
  assert structured.get("used_fallback") is True or structured.get("provider") != "none"
  assert structured.get("explanation_version") == EXPLANATION_VERSION
  assert structured.get("patient_friendly_explanation")
  assert structured.get("medical_explanation")
  assert structured.get("educational_notes")
  assert structured.get("lifestyle_advice")
  assert structured.get("questions_for_healthcare_professional")
  assert structured.get("disclaimer")
  assert structured.get("safety", {}).get("educational_only") is True


def test_clinical_whitelist_includes_projection(app_ctx):
  clinical = AIExplainerService._normalize_clinical_context(
    {
      "patient_age": 42,
      "gender": "Female",
      "body_part": "Chest",
      "projection": "PA",
      "symptoms": "Cough",
      "file_path": "/should/be/stripped",
      "heatmap_path": "/also/stripped",
    }
  )
  assert clinical is not None
  assert clinical["projection"] == "PA"
  assert "file_path" not in clinical
  assert "heatmap_path" not in clinical
  assert clinical["safety"]["supporting_context_only"] is True


def test_stamp_meta_sets_flags(app_ctx):
  stamped = AIExplainerService._stamp_meta(
    {
      "patient_friendly_explanation": "Possible finding for learning.",
      "ai_summary": "Educational summary.",
    },
    provider="fallback",
    used_fallback=True,
  )
  assert stamped["provider"] == "fallback"
  assert stamped["used_fallback"] is True
  assert stamped["image_sent_to_llm"] is False
  assert stamped["explanation_version"] == EXPLANATION_VERSION
