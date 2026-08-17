"""Module 11 — X-ray API integration tests (upload → analyze → history → download → recs)."""

from __future__ import annotations

import io
import os

import pytest

from tests.conftest import make_png_bytes


def _clinical_form(**overrides):
  data = {
    "patient_age": "58",
    "gender": "Male",
    "body_part": "Chest",
    "projection": "PA",
    "symptoms": "Persistent cough and fever",
    "reason_for_exam": "Chronic cough for two weeks",
    "smoking_history": "Former Smoker",
  }
  data.update(overrides)
  return data


@pytest.fixture
def uploaded_xray_id(client, auth_headers):
  """Upload one X-ray and return its id (cleanup in teardown)."""
  raw = make_png_bytes()
  data = {
    "body_part": "Chest",
    "files": (io.BytesIO(raw), "pytest_chest.png"),
  }
  response = client.post(
    "/api/xray/upload",
    data=data,
    headers=auth_headers,
  )
  assert response.status_code in (200, 201), response.get_data(as_text=True)
  body = response.get_json()
  payload = body.get("data") or {}
  files = payload.get("files") or payload.get("uploads") or []
  if not files and payload.get("xray_ids"):
    xray_id = payload["xray_ids"][0]
  else:
    assert files, body
    xray_id = files[0].get("xray_id") or files[0].get("id")
  assert xray_id
  yield int(xray_id)
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_upload_api(client, auth_headers):
  raw = make_png_bytes()
  response = client.post(
    "/api/xray/upload",
    data={"body_part": "Chest", "files": (io.BytesIO(raw), "api_upload.png")},
    headers=auth_headers,
  )
  assert response.status_code in (200, 201), response.get_data(as_text=True)
  body = response.get_json()
  assert body.get("status") == "success"
  payload = body["data"]
  files = payload.get("files") or []
  assert files
  xray_id = files[0].get("xray_id") or files[0].get("id")
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_preprocess_api(client, auth_headers, uploaded_xray_id):
  response = client.post(
    f"/api/xray/{uploaded_xray_id}/preprocess",
    headers=auth_headers,
  )
  assert response.status_code == 200, response.get_data(as_text=True)
  body = response.get_json()
  assert body["status"] == "success"
  xray = (body.get("data") or {}).get("xray") or {}
  assert xray.get("preprocessed_path") or xray.get("status")


def test_analyze_and_reanalyze_api(client, auth_headers):
  raw = make_png_bytes(asymmetric=True)
  data = _clinical_form()
  data["files"] = (io.BytesIO(raw), "analyze_me.png")
  response = client.post(
    "/api/xray/analyze",
    data=data,
    headers=auth_headers,
  )
  assert response.status_code in (200, 422), response.get_data(as_text=True)
  body = response.get_json()
  assert body.get("status") == "success"
  analyses = (body.get("data") or {}).get("analyses") or []
  assert analyses
  assert analyses[0].get("success") is True
  xray = analyses[0].get("xray") or {}
  xray_id = xray.get("id") or analyses[0].get("xray_id")
  assert xray_id
  assert xray.get("patient_age") == 58
  assert xray.get("gender") == "Male"
  assert xray.get("smoking_history") == "Former Smoker"
  assert xray.get("possible_findings")
  assert xray.get("ai_summary")
  structured = xray.get("structured_explanation") or {}
  assert structured.get("source_patient_clinical", {}).get("patient_age") == 58
  assert xray.get("learning_recommendations") is not None
  assert (body.get("data") or {}).get("patient_clinical", {}).get("patient_age") == 58

  re_resp = client.post(f"/api/xray/{xray_id}/reanalyze", headers=auth_headers)
  assert re_resp.status_code == 200, re_resp.get_data(as_text=True)
  re_body = re_resp.get_json()
  assert re_body["status"] == "success"

  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_analyze_requires_patient_clinical(client, auth_headers):
  raw = make_png_bytes()
  response = client.post(
    "/api/xray/analyze",
    data={"body_part": "Chest", "files": (io.BytesIO(raw), "no_clinical.png")},
    headers=auth_headers,
  )
  assert response.status_code == 400
  body = response.get_json()
  assert body.get("status") == "error"
  field_errors = (body.get("data") or {}).get("field_errors") or []
  assert any(e.get("field") == "patient_age" for e in field_errors)


def test_clinical_options_api(client, auth_headers):
  response = client.get("/api/xray/clinical-options", headers=auth_headers)
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert "Male" in data["genders"]
  assert "Wrist" in data["body_parts"]
  assert "Former Smoker" in data["smoking_history"]


def test_history_api(client, auth_headers, uploaded_xray_id):
  response = client.get("/api/xray/history", headers=auth_headers)
  assert response.status_code == 200
  body = response.get_json()
  data = body.get("data") or {}
  history = data.get("history") or []
  ids = {item.get("id") for item in history}
  assert uploaded_xray_id in ids
  assert "form_options" in data
  assert "Male" in (data.get("form_options") or {}).get("genders", [])


def test_history_clinical_filters(client, auth_headers):
  raw = make_png_bytes()
  data = _clinical_form(patient_age="62", gender="Female", smoking_history="Never Smoked")
  data["files"] = (io.BytesIO(raw), "history_filter.png")
  analyze = client.post("/api/xray/analyze", data=data, headers=auth_headers)
  assert analyze.status_code in (200, 422), analyze.get_data(as_text=True)
  body = analyze.get_json()
  analyses = (body.get("data") or {}).get("analyses") or []
  assert analyses
  xray_id = (analyses[0].get("xray") or {}).get("id") or analyses[0].get("xray_id")
  assert xray_id

  match = client.get(
    "/api/xray/history",
    query_string={
      "gender": "Female",
      "smoking_history": "Never Smoked",
      "age_min": 60,
      "age_max": 65,
      "body_part": "Chest",
    },
    headers=auth_headers,
  )
  assert match.status_code == 200
  items = (match.get_json().get("data") or {}).get("history") or []
  ids = {item.get("id") for item in items}
  assert xray_id in ids
  card = next(item for item in items if item.get("id") == xray_id)
  assert card.get("patient_age") == 62
  assert card.get("gender") == "Female"
  assert card.get("smoking_history") == "Never Smoked"
  assert card.get("patient_summary")

  miss = client.get(
    "/api/xray/history",
    query_string={"gender": "Male", "age_min": 60, "age_max": 65},
    headers=auth_headers,
  )
  assert miss.status_code == 200
  miss_ids = {item.get("id") for item in ((miss.get_json().get("data") or {}).get("history") or [])}
  assert xray_id not in miss_ids

  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_download_original_api(client, auth_headers, uploaded_xray_id, app):
  # Ensure stored path is absolute relative to process CWD used by the app
  with app.app_context():
    from app.extensions import db
    from app.models.xray_analysis_model import XrayAnalysis

    row = db.session.get(XrayAnalysis, uploaded_xray_id)
    assert row is not None
    path = row.file_path
    if path and not os.path.isabs(path):
      path = os.path.abspath(path)
    if not path or not os.path.isfile(path):
      pytest.skip(f"Uploaded file not on disk at {row.file_path!r} (environment path issue)")

  response = client.get(f"/api/xray/{uploaded_xray_id}/file", headers=auth_headers)
  assert response.status_code == 200
  assert response.mimetype.startswith("image/")
  assert len(response.data) > 100


def test_explain_api(client, auth_headers):
  raw = make_png_bytes()
  data = _clinical_form()
  data["files"] = (io.BytesIO(raw), "explain_me.png")
  analyze = client.post(
    "/api/xray/analyze",
    data=data,
    headers=auth_headers,
  )
  analyses = (analyze.get_json().get("data") or {}).get("analyses") or []
  xray_id = analyses[0]["xray"]["id"]
  response = client.post(f"/api/xray/{xray_id}/explain", headers=auth_headers)
  assert response.status_code == 200, response.get_data(as_text=True)
  data = response.get_json()["data"]
  assert data.get("explanation", {}).get("success") is True
  assert data.get("xray", {}).get("structured_explanation")
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_recommendations_api(client, auth_headers):
  raw = make_png_bytes()
  data = _clinical_form()
  data["files"] = (io.BytesIO(raw), "recs_me.png")
  analyze = client.post(
    "/api/xray/analyze",
    data=data,
    headers=auth_headers,
  )
  analyses = (analyze.get_json().get("data") or {}).get("analyses") or []
  xray_id = analyses[0]["xray"]["id"]
  response = client.get(f"/api/xray/{xray_id}/recommendations", headers=auth_headers)
  assert response.status_code == 200
  recs = (response.get_json().get("data") or {}).get("recommendations") or []
  assert isinstance(recs, list)
  assert recs
  assert any(r.get("clinical_aware") for r in recs)
  refresh = client.post(f"/api/xray/{xray_id}/recommendations", headers=auth_headers)
  assert refresh.status_code == 200
  meta = (refresh.get_json().get("data") or {}).get("meta") or {}
  assert meta.get("clinical_context_used") is True
  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_dashboard_api(client, auth_headers):
  response = client.get("/api/xray/dashboard", headers=auth_headers)
  assert response.status_code == 200
  data = response.get_json()["data"]
  assert "stats" in data
  assert "recent_xrays" in data
  assert "learning_recommendations" in data


def test_export_includes_patient_clinical(client, auth_headers):
  raw = make_png_bytes()
  data = _clinical_form(
    patient_age="55",
    gender="Female",
    smoking_history="Current Smoker",
    symptoms="Chest pain and cough",
    reason_for_exam="Rule out pneumonia",
  )
  data["files"] = (io.BytesIO(raw), "export_me.png")
  analyze = client.post("/api/xray/analyze", data=data, headers=auth_headers)
  assert analyze.status_code in (200, 422), analyze.get_data(as_text=True)
  analyses = (analyze.get_json().get("data") or {}).get("analyses") or []
  xray_id = analyses[0]["xray"]["id"]

  json_resp = client.get(f"/api/xray/{xray_id}/export?format=json", headers=auth_headers)
  assert json_resp.status_code == 200
  assert "application/json" in (json_resp.mimetype or "")
  payload = json_resp.get_json()
  assert payload["patient_clinical"]["patient_age"] == 55
  assert payload["patient_clinical"]["gender"] == "Female"
  assert payload["patient_clinical"]["smoking_history"] == "Current Smoker"
  assert payload["patient_clinical"]["symptoms"] == "Chest pain and cough"
  assert payload["safety"]["not_a_diagnosis"] is True
  assert payload["safety"]["raw_image_included"] is False
  assert "file_path" not in (payload.get("xray") or {})

  txt_resp = client.get(f"/api/xray/{xray_id}/export?format=txt", headers=auth_headers)
  assert txt_resp.status_code == 200
  text = txt_resp.get_data(as_text=True)
  assert "Patient Clinical Information" in text
  assert "55" in text
  assert "Female" in text
  assert "Current Smoker" in text
  assert "Chest pain and cough" in text
  assert "not a diagnosis" in text.lower()

  client.delete(f"/api/xray/{xray_id}", headers=auth_headers)


def test_ownership_enforced(client, auth_headers):
  response = client.get("/api/xray/99999999", headers=auth_headers)
  assert response.status_code == 404


def test_unauthenticated_blocked(client):
  response = client.get("/api/xray/history")
  assert response.status_code in (401, 422)
