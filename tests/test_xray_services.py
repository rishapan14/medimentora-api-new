"""Module 11 — preprocessing, vision, explanation, heatmap, recommendations."""

from __future__ import annotations

import os
import tempfile

import pytest

from tests.conftest import make_png_bytes


@pytest.fixture
def temp_png_path():
  raw = make_png_bytes(asymmetric=True)
  fd, path = tempfile.mkstemp(suffix=".png")
  os.close(fd)
  with open(path, "wb") as f:
    f.write(raw)
  yield path
  try:
    os.remove(path)
  except OSError:
    pass


def test_image_preprocessor(temp_png_path, tmp_path):
  from app.services.xray.image_preprocessor import ImagePreprocessor

  out_path = str(tmp_path / "preprocessed.png")
  result = ImagePreprocessor().enhance(temp_png_path, output_path=out_path)
  assert result.success
  assert result.path and os.path.isfile(result.path)
  assert result.final_size[0] > 0
  assert result.applied_steps
  assert "clahe" in result.applied_steps
  assert "normalization" in result.applied_steps
  assert result.normalization is not None


def test_heuristic_vision_model(temp_png_path):
  from app.services.xray.vision_model import HeuristicRadiographModel

  model = HeuristicRadiographModel()
  assert model.is_available()
  result = model.analyze(temp_png_path, body_part="Chest")
  assert result.success
  assert result.possible_findings
  assert all("Possible" in f.label or "No obvious" in f.label for f in result.possible_findings)
  assert all(f.to_dict().get("certainty") == "possible" for f in result.possible_findings)
  assert 0 <= result.confidence <= 1


def test_ai_explainer_fallback_no_image(app_ctx):
  from app.services.xray.ai_explainer import AIExplainerService

  result = AIExplainerService.explain_from_findings(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.7, "certainty": "possible"}],
    confidence=0.7,
    body_part="Chest",
    model_name="test-model",
  )
  assert result.success
  assert result.ai_summary
  assert result.structured_explanation.get("image_sent_to_llm") is False
  assert result.to_dict()["safety"]["image_sent_to_llm"] is False
  assert result.structured_explanation.get("patient_friendly_explanation")
  assert result.structured_explanation.get("questions_for_healthcare_professional")
  # Must not claim definitive diagnosis
  blob = (result.ai_summary + " " + str(result.structured_explanation)).lower()
  assert "you have pneumonia" not in blob


def test_ai_explainer_includes_patient_clinical_context(app_ctx):
  from app.services.xray.ai_explainer import AIExplainerService

  clinical = {
    "patient_age": 58,
    "gender": "Male",
    "body_part": "Chest",
    "symptoms": "Persistent cough and fever",
    "reason_for_exam": "Chronic cough for two weeks",
    "smoking_history": "Former Smoker",
  }
  payload = AIExplainerService._build_llm_payload(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.7, "certainty": "possible"}],
    confidence=0.7,
    body_part="Chest",
    model_name="test-model",
    patient_clinical=clinical,
  )
  assert payload["patient_clinical"]["patient_age"] == 58
  assert payload["patient_clinical"]["symptoms"] == "Persistent cough and fever"
  assert payload["patient_clinical"]["safety"]["supporting_context_only"] is True

  result = AIExplainerService.explain_from_findings(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.7, "certainty": "possible"}],
    confidence=0.7,
    body_part="Chest",
    model_name="test-model",
    patient_clinical=clinical,
  )
  assert result.success
  assert result.structured_explanation.get("source_patient_clinical") is not None
  assert result.structured_explanation["source_patient_clinical"]["patient_age"] == 58
  blob = (
    result.ai_summary
    + " "
    + str(result.structured_explanation.get("patient_friendly_explanation", ""))
  ).lower()
  assert "58" in blob or "cough" in blob or "former smoker" in blob


def test_ai_explainer_clinical_from_row(app_ctx):
  from types import SimpleNamespace

  from app.services.xray.ai_explainer import AIExplainerService

  row = SimpleNamespace(
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.6, "certainty": "possible"}],
    confidence=0.6,
    body_part="Chest",
    model_name="test-model",
    patient_age=45,
    gender="Female",
    symptoms="Shortness of breath",
    reason_for_exam="Follow-up imaging",
    smoking_history="Never Smoked",
    patient_clinical_dict=lambda: {
      "patient_age": 45,
      "gender": "Female",
      "body_part": "Chest",
      "symptoms": "Shortness of breath",
      "reason_for_exam": "Follow-up imaging",
      "smoking_history": "Never Smoked",
      "clinical_extras": {},
      "safety": {"supporting_context_only": True, "not_a_diagnosis": True},
    },
  )
  result = AIExplainerService.explain_xray_row(row)
  assert result.success
  assert result.structured_explanation.get("source_patient_clinical", {}).get("patient_age") == 45


def test_ai_explainer_rejects_image_payload_keys(app_ctx):
  from app.services.xray.ai_explainer import AIExplainerService

  assert AIExplainerService._payload_looks_like_image_request({"image_base64": "abc"}) is True
  assert AIExplainerService._payload_looks_like_image_request({"possible_findings": []}) is False


def test_heatmap_generation(temp_png_path, app_ctx):
  from app.services.xray.heatmap import HeatmapService

  result = HeatmapService.generate(
    temp_png_path,
    xray_id=999001,
    findings=[{"label": "Possible Lung Opacity", "probability": 0.8, "region": "asymmetric_lung_zone"}],
    body_part="Chest",
    prefer_gradcam=False,
  )
  assert result.success
  assert result.heatmap_path and os.path.isfile(result.heatmap_path)
  assert result.method == "heuristic_attention"
  assert result.to_dict()["ui_hints"]["supports_opacity_slider"] is True
  assert result.to_dict()["ui_hints"]["supports_download"] is True
  # cleanup
  for p in (result.heatmap_path, result.overlay_path):
    if p and os.path.isfile(p):
      os.remove(p)


def test_learning_recommendations(app_ctx):
  from app.services.xray.recommendation_service import XrayRecommendationService

  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.72}],
    body_part="Chest",
    sync_user_recommendations=False,
  )
  assert result.success
  assert any("Pneumonia" in t or "Respiratory" in t for t in result.topics)
  assert result.recommendations
  assert any(r.get("href") for r in result.recommendations)
  assert result.clinical_context_used is False


def test_learning_recommendations_with_clinical_context(app_ctx):
  from app.services.xray.recommendation_service import XrayRecommendationService

  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.65}],
    body_part="Chest",
    patient_clinical={
      "patient_age": 68,
      "gender": "Male",
      "symptoms": "Persistent cough and fever",
      "reason_for_exam": "Chronic cough",
      "smoking_history": "Former Smoker",
    },
    sync_user_recommendations=False,
  )
  assert result.success
  assert result.clinical_context_used is True
  topic_blob = " ".join(result.topics).lower()
  assert "copd" in topic_blob or "smoking" in topic_blob
  assert "geriatric" in topic_blob or "age-related" in topic_blob
  assert any("infection" in t.lower() or "pneumonia" in t.lower() for t in result.topics)
  assert all(r.get("clinical_aware") is True for r in result.recommendations)


def test_learning_recommendations_comparison_aware(app_ctx):
  from app.services.xray.recommendation_service import XrayRecommendationService

  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "Possible Lung Opacity", "probability": 0.61}],
    body_part="Chest",
    patient_clinical={
      "patient_age": 45,
      "gender": "Female",
      "smoking_history": "Never Smoked",
    },
    comparison_context={
      "body_part": "Chest",
      "reference_body_part": "Chest",
      "age_group": "Adult",
      "gender": "Female",
      "learning_focus": [
        "Normal Radiograph Anatomy",
        "Compare lung markings with a healthy adult chest reference",
      ],
      "comparison_summary": "Compared with the educational reference image for learning.",
    },
    sync_user_recommendations=False,
  )
  assert result.success
  assert result.comparison_aware is True
  assert any("Normal Radiograph" in t or "Systematic" in t for t in result.topics)
  assert result.recommendations
  assert all(r.get("comparison_aware") is True for r in result.recommendations)
  assert any("healthy reference" in (r.get("reason") or "").lower() for r in result.recommendations)
  assert any(r.get("source") == "comparison" for r in result.recommendations)
  assert any("clinical context" in (r.get("reason") or "").lower() for r in result.recommendations)
  assert any("not a diagnosis" in (r.get("reason") or "").lower() for r in result.recommendations)


def test_export_service_payload_shape(app_ctx):
  from types import SimpleNamespace

  from app.services.xray.export_service import XrayExportService

  row = SimpleNamespace(
    id=42,
    filename="demo.png",
    body_part="Chest",
    status="completed",
    confidence=0.7,
    model_name="test-model",
    analysis_date=None,
    possible_findings=[{"label": "Possible Opacity", "probability": 0.7}],
    ai_summary="Educational summary.",
    disclaimer="Educational only. Not a diagnosis.",
    reference_image_path="Chest/Adult/Male/healthy.png",
    comparison_summary="Compared with the educational reference image.",
    comparison_generated_at=None,
    patient_clinical_dict=lambda: {
      "patient_age": 40,
      "gender": "Other",
      "body_part": "Chest",
      "symptoms": "Cough",
      "reason_for_exam": "Follow-up",
      "smoking_history": "Never Smoked",
      "clinical_extras": {},
      "safety": {"supporting_context_only": True, "not_a_diagnosis": True},
    },
    to_dict=lambda include_explanation=False: {
      "id": 42,
      "filename": "demo.png",
      "file_path": "/secret/path.png",
      "preprocessed_path": "/secret/prep.png",
      "body_part": "Chest",
      "patient_age": 40,
    },
  )
  payload = XrayExportService.build_json_payload(row)
  assert payload["patient_clinical"]["patient_age"] == 40
  assert "file_path" not in payload["xray"]
  assert payload["comparison"]["has_comparison"] is True
  assert payload["comparison"]["reference_image_path"]
  text = XrayExportService.build_text_summary(row)
  assert "Patient Clinical Information" in text
  assert "Never Smoked" in text
  assert "Educational healthy comparison" in text
  assert "Compared with the educational reference image" in text

def test_dashboard_service_shape(app_ctx):
  from app.models.user_model import User
  from app.services.xray.dashboard_service import XrayDashboardService

  user = User.query.filter_by(email="student@clinical.com").first() or User.query.first()
  if not user:
    pytest.skip("No user available")
  data = XrayDashboardService.build_for_user(user.id)
  assert set(data.keys()) >= {"stats", "recent_xrays", "recent_analyses", "learning_recommendations"}
  assert "total_uploads" in data["stats"]
  assert "completed_analyses" in data["stats"]
