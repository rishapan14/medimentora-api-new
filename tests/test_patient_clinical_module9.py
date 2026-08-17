"""Module 9 — Patient Clinical Information end-to-end tests.

Covers the full clinical form pipeline:
  options → analyze (require clinical) → persist → explain → recommendations
  → history filters → export → reanalyze preserves clinical
"""

from __future__ import annotations

import io
import json

import pytest

from tests.conftest import make_png_bytes


def _clinical(**overrides):
  data = {
    "patient_age": "58",
    "gender": "Male",
    "body_part": "Chest",
    "symptoms": "Persistent cough and fever",
    "reason_for_exam": "Chronic cough for two weeks",
    "smoking_history": "Former Smoker",
  }
  data.update(overrides)
  return data


@pytest.fixture
def analyzed_clinical_xray(client, auth_headers):
  """Upload+analyze one X-ray with full clinical context; cleanup after."""
  raw = make_png_bytes(asymmetric=True)
  data = _clinical()
  data["files"] = (io.BytesIO(raw), "module9_clinical.png")
  response = client.post("/api/xray/analyze", data=data, headers=auth_headers)
  assert response.status_code in (200, 422), response.get_data(as_text=True)
  body = response.get_json()
  assert body.get("status") == "success"
  analyses = (body.get("data") or {}).get("analyses") or []
  assert analyses and analyses[0].get("success") is True
  xray = analyses[0].get("xray") or {}
  xray_id = xray.get("id") or analyses[0].get("xray_id")
  assert xray_id
  yield {
    "id": int(xray_id),
    "xray": xray,
    "patient_clinical": (body.get("data") or {}).get("patient_clinical"),
    "response": body,
  }
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_clinical_options_contract(client, auth_headers):
  response = client.get("/api/xray/clinical-options", headers=auth_headers)
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert set(data["required"]) >= {"patient_age", "gender", "body_part"}
  assert "Wrist" in data["body_parts"]
  assert "Prefer not to say" in data["genders"]
  assert "Former Smoker" in data["smoking_history"]
  assert data["limits"]["patient_age_max"] == 120
  assert data["disclaimer"]


def test_analyze_persists_full_clinical(analyzed_clinical_xray, client, auth_headers):
  xray = analyzed_clinical_xray["xray"]
  assert xray.get("patient_age") == 58
  assert xray.get("gender") == "Male"
  assert xray.get("body_part") == "Chest"
  assert xray.get("smoking_history") == "Former Smoker"
  assert "cough" in (xray.get("symptoms") or "").lower()
  assert analyzed_clinical_xray["patient_clinical"]["patient_age"] == 58

  detail = client.get(
    f"/api/xray/{analyzed_clinical_xray['id']}?include_explanation=true",
    headers=auth_headers,
  )
  assert detail.status_code == 200
  payload = detail.get_json()["data"]["xray"]
  assert payload["patient_clinical"]["patient_age"] == 58
  assert payload["patient_clinical"]["safety"]["not_a_diagnosis"] is True
  assert payload["structured_explanation"]["source_patient_clinical"]["patient_age"] == 58
  assert payload["structured_explanation"]["image_sent_to_llm"] is False


def test_analyze_rejects_incomplete_clinical(client, auth_headers):
  raw = make_png_bytes()
  response = client.post(
    "/api/xray/analyze",
    data={"body_part": "Chest", "gender": "Male", "files": (io.BytesIO(raw), "bad.png")},
    headers=auth_headers,
  )
  assert response.status_code == 400
  field_errors = (response.get_json().get("data") or {}).get("field_errors") or []
  assert any(e.get("field") == "patient_age" for e in field_errors)


def test_upload_without_clinical_still_allowed(client, auth_headers):
  raw = make_png_bytes()
  response = client.post(
    "/api/xray/upload",
    data={"body_part": "Chest", "files": (io.BytesIO(raw), "upload_only.png")},
    headers=auth_headers,
  )
  assert response.status_code in (200, 201), response.get_data(as_text=True)
  files = (response.get_json().get("data") or {}).get("files") or []
  assert files
  xray_id = files[0].get("xray_id") or files[0].get("id")
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_explain_and_recommendations_use_clinical(analyzed_clinical_xray, client, auth_headers):
  xray_id = analyzed_clinical_xray["id"]

  explain = client.post(f"/api/xray/{xray_id}/explain", headers=auth_headers)
  assert explain.status_code == 200
  explanation = explain.get_json()["data"]["explanation"]
  assert explanation.get("success") is True
  structured = explain.get_json()["data"]["xray"]["structured_explanation"]
  assert structured["source_patient_clinical"]["smoking_history"] == "Former Smoker"
  assert structured["image_sent_to_llm"] is False

  refresh = client.post(f"/api/xray/{xray_id}/recommendations", headers=auth_headers)
  assert refresh.status_code == 200
  data = refresh.get_json()["data"]
  recs = data.get("recommendations") or []
  assert recs
  assert any(r.get("clinical_aware") for r in recs)
  meta = data.get("meta") or {}
  assert meta.get("clinical_context_used") is True
  assert meta.get("safety", {}).get("not_a_diagnosis") is True


def test_history_filters_by_clinical(analyzed_clinical_xray, client, auth_headers):
  xray_id = analyzed_clinical_xray["id"]

  hit = client.get(
    "/api/xray/history",
    query_string={
      "gender": "Male",
      "smoking_history": "Former Smoker",
      "age_min": 50,
      "age_max": 60,
      "body_part": "Chest",
    },
    headers=auth_headers,
  )
  assert hit.status_code == 200
  items = (hit.get_json().get("data") or {}).get("history") or []
  assert xray_id in {i.get("id") for i in items}
  card = next(i for i in items if i.get("id") == xray_id)
  assert card.get("patient_summary")
  assert card.get("patient_age") == 58

  miss = client.get(
    "/api/xray/history",
    query_string={"gender": "Female", "age_min": 50, "age_max": 60},
    headers=auth_headers,
  )
  assert xray_id not in {i.get("id") for i in ((miss.get_json().get("data") or {}).get("history") or [])}


def test_export_json_and_txt_include_clinical(analyzed_clinical_xray, client, auth_headers):
  xray_id = analyzed_clinical_xray["id"]

  json_resp = client.get(f"/api/xray/{xray_id}/export?format=json", headers=auth_headers)
  assert json_resp.status_code == 200
  payload = json_resp.get_json()
  assert payload["patient_clinical"]["patient_age"] == 58
  assert payload["patient_clinical"]["symptoms"]
  assert payload["safety"]["raw_image_included"] is False
  assert "file_path" not in (payload.get("xray") or {})

  txt_resp = client.get(f"/api/xray/{xray_id}/export?format=txt", headers=auth_headers)
  assert txt_resp.status_code == 200
  text = txt_resp.get_data(as_text=True)
  assert "Patient Clinical Information" in text
  assert "Former Smoker" in text
  assert "Persistent cough" in text
  assert "not a diagnosis" in text.lower()


def test_reanalyze_preserves_clinical(analyzed_clinical_xray, client, auth_headers):
  xray_id = analyzed_clinical_xray["id"]
  response = client.post(f"/api/xray/{xray_id}/reanalyze", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  xray = response.get_json()["data"]["xray"]
  assert xray.get("patient_age") == 58
  assert xray.get("gender") == "Male"
  assert xray.get("smoking_history") == "Former Smoker"
  assert xray.get("patient_clinical", {}).get("patient_age") == 58


def test_explainer_payload_whitelists_clinical_only(app_ctx):
  from app.services.xray.ai_explainer import AIExplainerService

  payload = AIExplainerService._build_llm_payload(
    possible_findings=[{"label": "Possible Pneumonia", "probability": 0.8}],
    confidence=0.8,
    body_part="Chest",
    model_name="test",
    patient_clinical={
      "patient_age": 58,
      "gender": "Male",
      "symptoms": "Cough",
      "smoking_history": "Former Smoker",
      "image_base64": "SHOULD_NOT_APPEAR",
      "file_path": "/tmp/secret.png",
    },
  )
  clinical = payload["patient_clinical"]
  assert clinical["patient_age"] == 58
  assert "image_base64" not in clinical
  assert "file_path" not in clinical
  assert "image_base64" not in payload
  assert AIExplainerService._payload_looks_like_image_request(payload) is False


def test_recommendation_topics_from_pediatric_clinical(app_ctx):
  from app.services.xray.recommendation_service import XrayRecommendationService

  result = XrayRecommendationService.build_recommendations(
    possible_findings=[{"label": "No obvious abnormality", "probability": 0.4}],
    body_part="Chest",
    patient_clinical={"patient_age": 12, "gender": "Female", "symptoms": "Fever"},
    sync_user_recommendations=False,
  )
  assert result.clinical_context_used is True
  topics = " ".join(result.topics).lower()
  assert "pediatric" in topics
  assert "infectious" in topics or "pneumonia" in topics or "fever" in topics or "clinical" in topics
